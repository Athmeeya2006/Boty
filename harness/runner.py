"""Local match runner that mimics the official evaluator (evaluator/evaluate.py: Event.match).

Differences from the official runner, on purpose:
  * bots run as plain subprocesses (python3.12 -I -S -B harness/bot_worker.py bot.py)
    instead of Docker containers, so batches can run in parallel;
  * the response deadline is configurable (batches use a generous one so host load
    does not create fake forfeits, and timing is reported separately).
Everything else follows the official flow: both observations computed from the same
pre-turn state, request order alternates by turn, first call gets 10 s, faults forfeit.

Usage:
  .venv/bin/python harness/runner.py botA.py botB.py --seed 42 [--record out.jsonl] [--log-dir d]
"""
import argparse
import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("XLA_FLAGS", "--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1")
os.environ.setdefault("JAX_COMPILATION_CACHE_DIR", str(ROOT / ".jax_cache"))
os.environ.setdefault("JAX_PERSISTENT_CACHE_MIN_COMPILE_TIME_SECS", "0")
sys.path.insert(0, str(ROOT / "evaluator"))

BOT_PYTHON = os.environ.get("BOT_PYTHON", "/usr/bin/python3.12")
WORKER = ROOT / "harness" / "bot_worker.py"

_engine = None


def engine():
    global _engine
    if _engine is None:
        import engine as e
        _engine = e
    return _engine


class BotFault(Exception):
    pass


def validate_action(value):
    # Identical to evaluator/sandbox.py: validate_action.
    if not isinstance(value, (list, tuple)) or len(value) != 5:
        raise BotFault("act() must return five integers")
    if any(type(x) is not int or not -(2**31) <= x < 2**31 for x in value):
        raise BotFault("action fields must be signed 32-bit integers (not booleans)")
    kind, row, col, direction, split = value
    if kind not in (0, 1, 2) or direction not in range(4) or split not in (0, 1):
        raise BotFault("invalid kind, direction or split code")
    return list(value)


class LocalBot:
    def __init__(self, path, log_path=None, env=None):
        self.log = open(log_path, "wb") if log_path else subprocess.DEVNULL
        self.proc = subprocess.Popen([BOT_PYTHON, "-I", "-S", "-B", str(WORKER), str(Path(path).resolve())],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
                                     bufsize=0, env=env)
        os.set_blocking(self.proc.stdout.fileno(), False)
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.proc.stdout, selectors.EVENT_READ)
        self.buffer = b""
        if json.loads(self._readline(30)) != {"ready": True}:
            raise RuntimeError("worker did not start")

    def _readline(self, seconds):
        end = time.monotonic() + seconds
        while b"\n" not in self.buffer:
            remaining = end - time.monotonic()
            if remaining <= 0 or not self.sel.select(max(0, remaining)):
                raise BotFault("response deadline exceeded")
            try:
                chunk = os.read(self.proc.stdout.fileno(), 65536)
            except BlockingIOError:
                continue
            if not chunk:
                raise BotFault("bot process exited or closed output")
            self.buffer += chunk
            if len(self.buffer) > 4096:
                raise BotFault("protocol output exceeded 4096 bytes")
        line, self.buffer = self.buffer.split(b"\n", 1)
        return line

    def act(self, obs, budget_s):
        started = time.monotonic()
        request = json.dumps({"id": obs["turn"], "observation": obs}, separators=(",", ":")).encode() + b"\n"
        try:
            self.proc.stdin.write(request)
            self.proc.stdin.flush()
        except BrokenPipeError as exc:
            raise BotFault("bot process I/O failed") from exc
        line = self._readline(budget_s)
        elapsed = (time.monotonic() - started) * 1000
        if elapsed > budget_s * 1000:
            raise BotFault("response deadline exceeded")
        try:
            reply = json.loads(line)
        except ValueError as exc:
            raise BotFault("malformed adapter response") from exc
        if not isinstance(reply, dict) or reply.get("id") != obs["turn"]:
            raise BotFault("stale adapter response")
        if "error" in reply:
            raise BotFault("exception in participant code")
        return validate_action(reply.get("action")), elapsed

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.sel.close()
        if self.log is not subprocess.DEVNULL:
            self.log.close()


def play_game(bot_paths, seed, move_ms=150, first_ms=10000, max_turns=1200, record=None, log_dir=None,
              bot_env=None, truth_hook=None):
    """Play one game. Returns a result dict. bot_paths[0] plays slot 0.

    record: optional path; writes a JSONL replay (initial snapshot, then per turn actions + snapshot).
    log_dir: optional directory for bot stderr logs.
    truth_hook: optional callable(turn, state, obs_pair, actions) for inference tests.
    """
    e = engine()
    state = e.initial(seed)
    h, w = (int(x) for x in state.armies.shape)
    bots = []
    times = [[], []]
    result = None
    rec = open(record, "w") if record else None
    try:
        for i, p in enumerate(bot_paths):
            lp = Path(log_dir) / f"bot_{i}.stderr.log" if log_dir else None
            bots.append(LocalBot(p, lp, env=bot_env))
        if rec:
            rec.write(json.dumps({"initial": e.snapshot(state), "seed": seed, "bots": [str(p) for p in bot_paths]}) + "\n")
        for turn in range(max_turns):
            obs = [e.observation(state, i) for i in (0, 1)]
            actions = [[1, 0, 0, 0, 0], [1, 0, 0, 0, 0]]
            errors = [None, None]
            for i in ((0, 1) if turn % 2 == 0 else (1, 0)):
                try:
                    budget = (first_ms if turn == 0 else move_ms) / 1000
                    actions[i], ms = bots[i].act(obs[i], budget)
                    times[i].append(ms)
                except BotFault as exc:
                    errors[i] = str(exc)
            if any(errors):
                scores = [0, 0] if all(errors) else ([0, 1] if errors[0] else [1, 0])
                result = dict(scores=scores, reason="double_forfeit" if all(errors) else "forfeit",
                              faults=errors, turns=turn,
                              winner=None if all(errors) else (1 if errors[0] else 0))
                break
            if truth_hook:
                truth_hook(turn, state, obs, actions)
            state, info = e.step(state, actions)
            if rec:
                rec.write(json.dumps(dict(turn=turn, actions=actions, state=e.snapshot(state))) + "\n")
            if bool(info.is_done):
                winner = int(info.winner)
                result = dict(scores=[.5, .5] if winner < 0 else ([1, 0] if winner == 0 else [0, 1]),
                              winner=None if winner < 0 else winner, turns=turn + 1,
                              reason="mutual_draw" if winner < 0 else "capture")
                break
        if result is None:
            result = dict(scores=[.5, .5], winner=None, turns=max_turns, reason="turn_cap_draw")
    finally:
        for b in bots:
            b.close()
        if rec:
            rec.close()
    result.update(seed=seed, height=h, width=w, bots=[str(p) for p in bot_paths], times=times)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bot0")
    ap.add_argument("bot1")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--move-ms", type=int, default=150)
    ap.add_argument("--max-turns", type=int, default=1200)
    ap.add_argument("--record")
    ap.add_argument("--log-dir")
    ap.add_argument("--debug", action="store_true", help="set BOT_DEBUG=1 in the bot environment")
    a = ap.parse_args()
    env = None
    if a.debug:
        env = dict(os.environ, BOT_DEBUG="1")
    if a.log_dir:
        Path(a.log_dir).mkdir(parents=True, exist_ok=True)
    r = play_game([a.bot0, a.bot1], a.seed, a.move_ms, max_turns=a.max_turns, record=a.record,
                  log_dir=a.log_dir, bot_env=env)
    t = r.pop("times")
    for i in (0, 1):
        if t[i]:
            s = sorted(t[i][1:]) or [0]
            r[f"bot{i}_ms"] = dict(first=round(t[i][0], 1), p50=round(s[len(s) // 2], 1),
                                   p99=round(s[int(len(s) * .99)], 1), max=round(s[-1], 1))
    print(json.dumps(r, indent=1))


if __name__ == "__main__":
    main()
