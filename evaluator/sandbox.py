"""Linux Docker isolation, bounded I/O and externally measured response deadlines."""
import http.client
import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import threading
import time
import uuid


class BotFault(Exception):
    """An entry forfeits this game. Infrastructure errors use RuntimeError."""


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=10)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


class Docker:
    def __init__(self):
        context = subprocess.check_output(["docker", "context", "inspect"], text=True)
        host = os.environ.get("DOCKER_HOST") or json.loads(context)[0]["Endpoints"]["docker"]["Host"]
        if not host.startswith("unix://"):
            raise RuntimeError("Use a local Linux Docker daemon via a unix:// socket.")
        self.path = host[7:]

    def api(self, method, path):
        c = UnixConnection(self.path)
        try:
            c.request(method, path)
            r = c.getresponse()
            body = r.read()
            if r.status >= 400:
                raise RuntimeError(f"Docker {path}: {r.status} {body.decode(errors='replace')[:300]}")
            return json.loads(body) if body else None
        finally:
            c.close()


def validate_action(value):
    if not isinstance(value, (list, tuple)) or len(value) != 5:
        raise BotFault("act() must return five integers")
    if any(type(x) is not int or not -(2**31) <= x < 2**31 for x in value):
        raise BotFault("action fields must be signed 32-bit integers (not booleans)")
    kind, row, col, direction, split = value
    if kind not in (0, 1, 2) or direction not in range(4) or split not in (0, 1):
        raise BotFault("invalid kind, direction or split code")
    return list(value)


class Bot:
    def __init__(self, docker, path, image, cpu, log_path):
        self.docker = docker
        self.name = "codebot-" + uuid.uuid4().hex
        self.process = None
        self.selector = selectors.DefaultSelector()
        self.buffer = b""
        self.paused = False
        self.log = open(log_path, "wb")
        self.thread = None
        cmd = ["docker", "run", "--pull=never", "--name", self.name, "--label", "codebot=true",
               "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
               "--pids-limit=32", "--memory=2g", "--memory-swap=2g", "--cpus=1",
               f"--cpuset-cpus={cpu}", "--user=65534:65534", "--ipc=none",
               "--ulimit", "nofile=64:64", "--log-driver=none",
               "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m,mode=1777",
               "--mount", f"type=bind,src={Path(path).resolve()},dst=/submission/bot.py,readonly",
               "-i", image]
        try:
            self.process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, bufsize=0)
            self.thread = threading.Thread(target=self._drain_log, daemon=True)
            self.thread.start()
            os.set_blocking(self.process.stdout.fileno(), False)
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            # No participant code executes before this readiness response.
            ready = self._readline(30)
            if json.loads(ready) != {"ready": True}:
                raise RuntimeError("The sandbox image did not emit the expected readiness frame.")
            self._pause()
        except BaseException as exc:
            self.close()
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise RuntimeError(f"Sandbox startup failed (infrastructure): {exc}") from exc

    def _drain_log(self):
        remaining = 65536
        while True:
            chunk = self.process.stderr.read(8192)
            if not chunk:
                break
            if remaining:
                self.log.write(chunk[:remaining])
                self.log.flush()
                remaining = max(0, remaining - len(chunk))

    def _pause(self):
        try:
            self.docker.api("POST", f"/containers/{self.name}/pause")
            self.paused = True
        except RuntimeError:
            state = self.docker.api("GET", f"/containers/{self.name}/json")["State"]
            if not state["Running"]:
                raise BotFault("bot process exited")
            raise

    def _readline(self, seconds):
        end = time.monotonic() + seconds
        while b"\n" not in self.buffer:
            remaining = end - time.monotonic()
            if remaining <= 0 or not self.selector.select(max(0, remaining)):
                raise BotFault("response deadline exceeded")
            try:
                chunk = os.read(self.process.stdout.fileno(), 4096)
            except BlockingIOError:
                continue
            if not chunk:
                raise BotFault("bot process exited or closed output")
            self.buffer += chunk
            if len(self.buffer) > 4096:
                raise BotFault("protocol output exceeded 4096 bytes")
        line, self.buffer = self.buffer.split(b"\n", 1)
        if time.monotonic() > end:
            raise BotFault("response deadline exceeded")
        return line

    def act(self, obs, first=False, move_ms=150):
        if self.buffer:
            raise BotFault("unsolicited protocol output")
        self.docker.api("POST", f"/containers/{self.name}/unpause")
        self.paused = False
        started = time.monotonic()
        budget = 10 if first else move_ms / 1000
        request = json.dumps({"id": obs["turn"], "observation": obs}, separators=(",", ":")).encode()+b"\n"
        # Board frames are bounded (< 64 KiB). A selector handles blocked input
        # as part of the deadline rather than hanging the tournament.
        fd = self.process.stdin.fileno()
        os.set_blocking(fd, False)
        try:
            with selectors.DefaultSelector() as writer:
                writer.register(fd, selectors.EVENT_WRITE)
                offset = 0
                while offset < len(request):
                    left = budget - (time.monotonic() - started)
                    if left <= 0 or not writer.select(max(0, left)):
                        raise BotFault("input/response deadline exceeded")
                    try:
                        offset += os.write(fd, request[offset:])
                    except BlockingIOError:
                        continue
            line = self._readline(max(0, budget - (time.monotonic() - started)))
            elapsed = (time.monotonic() - started) * 1000
            self._pause()
            try:
                reply = json.loads(line)
            except (ValueError, UnicodeError) as exc:
                raise BotFault("malformed adapter response") from exc
            if not isinstance(reply, dict) or reply.get("id") != obs["turn"]:
                raise BotFault("unsolicited or stale adapter response")
            if "error" in reply:
                raise BotFault("exception in participant code; see stderr log")
            return validate_action(reply.get("action")), elapsed
        except BrokenPipeError as exc:
            raise BotFault("bot process I/O failed") from exc
        finally:
            if not self.paused:
                self.close()

    def close(self):
        # Force removal kills every process in the cgroup, including descendants.
        subprocess.run(["docker", "rm", "-f", self.name], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=15)
        if self.process:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            if self.thread:
                self.thread.join(timeout=5)
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                stream.close()
        self.selector.close()
        self.log.close()
