#!/usr/bin/env python3
"""Code Bot evaluator: isolated matches, round robin, playoffs and audit logs."""
import argparse
import ast
import csv
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys

from sandbox import Bot, BotFault, Docker

ROOT = Path(__file__).resolve().parent
IMAGE = "codebot-python:1"
MAX_FILE = 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def validate_file(path):
    path = Path(path)
    if path.suffix != ".py" or not path.is_file() or path.is_symlink():
        raise ValueError(f"Submission must be a regular, non-symlink .py file: {path}")
    if not 0 < path.stat().st_size <= MAX_FILE:
        raise ValueError(f"Submission must be between 1 byte and 1 MiB: {path}")
    data = path.read_bytes()
    try:
        tree = ast.parse(data.decode("utf-8"), filename=path.name)
    except (SyntaxError, UnicodeError) as exc:
        raise ValueError(f"Submission is not syntactically valid UTF-8 Python: {path}") from exc
    if not any(isinstance(node, ast.FunctionDef) and node.name == "act" for node in tree.body):
        raise ValueError(f"Submission needs a top-level def act(observation): {path}")
    return data


def freeze(paths, out):
    entries = {}
    dest = out / "submissions"
    dest.mkdir()
    for path in paths:
        name = path.stem
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) or name in entries:
            raise ValueError("Use unique participant IDs as filenames: letters, digits, '-' or '_', up to 64 chars.")
        data = validate_file(path)
        target = dest / (name + ".py")
        target.write_bytes(data)
        target.chmod(0o444)
        entries[name] = {"path": str(target.resolve()), "sha256": digest(data)}
    return entries


def standings(ids, games, draw_seed):
    points = {i: 0 for i in ids}  # integer half-points prevent float ties
    wins = {i: 0 for i in ids}
    for g in games:
        for slot, i in enumerate(g["players"]):
            points[i] += int(g["scores"][slot] * 2)
            wins[i] += int(g["scores"][slot] == 1)
    groups = {}
    for i in ids:
        groups.setdefault(points[i], []).append(i)
    ordered = []
    for score in sorted(groups, reverse=True):
        tied = groups[score]
        h2h = {i: 0 for i in tied}
        for g in games:
            if all(i in tied for i in g["players"]):
                for slot, i in enumerate(g["players"]):
                    h2h[i] += int(g["scores"][slot] * 2)
        ordered.extend(sorted(tied, key=lambda i: (-h2h[i], -wins[i], digest(f"{draw_seed}:{i}".encode()), i)))
    result = []
    for rank, i in enumerate(ordered, 1):
        tied = groups[points[i]]
        head = sum(int(g["scores"][g["players"].index(i)] * 2) for g in games
                   if i in g["players"] and all(x in tied for x in g["players"]))
        result.append(dict(rank=rank, participant=i, points=points[i]/2, head_to_head=head/2,
                           wins=wins[i], draw_key=digest(f"{draw_seed}:{i}".encode())))
    return result


class Event:
    def __init__(self, args, entries, out):
        self.args, self.entries, self.out = args, entries, out
        self.docker = Docker()
        self.matches = []
        self.seeds = set()
        from engine import ENGINE_COMMIT
        image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image], text=True))[0]
        # Use the immutable image ID for every game, even if the tag changes.
        self.image = image["Id"]
        self.manifest = dict(version="2.0", engine_commit=ENGINE_COMMIT,
                             image_id=self.image, cpu=args.cpu, response_ms=args.move_ms,
                             first_response_seconds=10, memory_bytes=2*1024**3,
                             max_turns=args.max_turns, official_limits=args.max_turns == 1200 and args.move_ms == 150,
                             started_utc=datetime.now(timezone.utc).isoformat(), entries=entries,
                             draw_seed=args.draw_seed, engine_tree_sha256=engine_digest())
        write_json(out / "manifest.json", self.manifest)

    def seed(self):
        while True:
            seed = secrets.randbits(32)
            if seed not in self.seeds:
                self.seeds.add(seed)
                return seed

    def match(self, a, b, stage="match", seed=None):
        from engine import initial, observation, snapshot, step
        number = len(self.matches) + 1
        game_dir = self.out / f"game_{number:04d}"
        game_dir.mkdir()
        seed = self.seed() if seed is None else seed
        if not 0 <= seed < 2**32:
            raise ValueError("Map seed must be an unsigned 32-bit integer.")
        metadata = dict(game_id=number, stage=stage, players=[a, b], seed=seed)
        write_json(game_dir / "metadata.json", metadata)
        print(f"Game {number}: {a} vs {b} ({stage})", flush=True)
        state = initial(seed)
        bots = []
        result = None
        try:
            for i, name in enumerate((a, b)):
                entry = self.entries[name]
                if digest(Path(entry["path"]).read_bytes()) != entry["sha256"]:
                    raise RuntimeError("Frozen submission changed; aborting the run.")
                bots.append(Bot(self.docker, entry["path"], self.image, self.args.cpu,
                                game_dir / f"bot_{i}.stderr.log"))
            with (game_dir / "replay.jsonl").open("w") as replay:
                replay.write(json.dumps({"initial": snapshot(state)}) + "\n")
                for turn in range(self.args.max_turns):
                    # Compute BOTH observations before either bot chooses its move.
                    obs = [observation(state, i) for i in (0, 1)]
                    actions = [[1, 0, 0, 0, 0], [1, 0, 0, 0, 0]]
                    errors, times = [None, None], [None, None]
                    # Both containers use the same single logical CPU. Pause the
                    # inactive one and alternate request order to avoid bias.
                    for i in ((0, 1) if turn % 2 == 0 else (1, 0)):
                        try:
                            actions[i], times[i] = bots[i].act(obs[i], first=turn == 0,
                                                              move_ms=self.args.move_ms)
                        except BotFault as exc:
                            errors[i] = str(exc)
                    if any(errors):
                        scores = [0, 0] if all(errors) else ([0, 1] if errors[0] else [1, 0])
                        result = dict(scores=scores, reason="double_forfeit" if all(errors) else "forfeit",
                                      faults=errors, turns=turn, winner=None if all(errors) else (b if errors[0] else a))
                        replay.write(json.dumps(dict(turn=turn, actions=actions, response_ms=times, faults=errors))+"\n")
                        break
                    state, info = step(state, actions)
                    replay.write(json.dumps(dict(turn=turn, actions=actions, response_ms=times,
                                                 state=snapshot(state))) + "\n")
                    if bool(info.is_done):
                        winner = int(info.winner)
                        result = dict(scores=[.5, .5] if winner < 0 else ([1, 0] if winner == 0 else [0, 1]),
                                      winner=None if winner < 0 else (a, b)[winner], turns=turn+1,
                                      reason="mutual_capture_draw" if winner < 0 else "capture")
                        break
                if result is None:
                    result = dict(scores=[.5, .5], winner=None, turns=self.args.max_turns, reason="turn_cap_draw")
        finally:
            for bot in bots:
                bot.close()
        result = {**metadata, **result}
        self.matches.append(result)
        write_json(game_dir / "result.json", result)
        write_json(self.out / "games.json", self.matches)
        print(f"  {result['reason']}: {result['scores']}", flush=True)
        return result

    def series(self, a, b, games, stage, seeds):
        scores = {a: 0, b: 0}
        ids = []
        def play_pair():
            for left, right in ((a, b), (b, a)):
                g = self.match(left, right, stage)
                ids.append(g["game_id"])
                for i, name in enumerate(g["players"]):
                    scores[name] += g["scores"][i]
        for _ in range(games // 2):
            play_pair()
        extra = scores[a] == scores[b]
        if extra:
            play_pair()
        seeded = scores[a] == scores[b]
        winner = min((a, b), key=lambda i: seeds[i]) if seeded else max(scores, key=scores.get)
        return dict(stage=stage, winner=winner, loser=b if winner == a else a, scores=scores,
                    games=ids, extra_pair=extra, decided_by_league_seed=seeded)

    def tournament(self):
        ids = sorted(self.entries)
        league = []
        for a, b in itertools.combinations(ids, 2):
            for left, right in ((a, b), (b, a)):
                league.append(self.match(left, right, "league"))
                table = standings(ids, league, self.args.draw_seed)
                write_json(self.out / "standings.json", table)
                with (self.out / "standings.csv").open("w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(table[0]))
                    writer.writeheader()
                    writer.writerows(table)
        seeds = {x["participant"]: x["rank"] for x in table}
        ranked = [x["participant"] for x in table]
        bracket = []
        if len(ids) >= 4:
            s1 = self.series(ranked[0], ranked[3], 4, "semifinal_1", seeds)
            bracket.append(s1)
            write_json(self.out / "bracket.json", bracket)
            s2 = self.series(ranked[1], ranked[2], 4, "semifinal_2", seeds)
            bracket.append(s2)
            write_json(self.out / "bracket.json", bracket)
            bronze = self.series(s1["loser"], s2["loser"], 4, "third_place", seeds)
            bracket.append(bronze)
            write_json(self.out / "bracket.json", bracket)
            finalists, third = [s1["winner"], s2["winner"]], bronze["winner"]
        else:
            finalists, third = ranked[:2], ranked[2] if len(ranked) == 3 else None
        final = self.series(*finalists, 6, "final", seeds)
        bracket.append(final)
        write_json(self.out / "bracket.json", bracket)
        podium = [dict(place=1, participant=final["winner"], prize_usd=500),
                  dict(place=2, participant=final["loser"], prize_usd=300)]
        if third:
            podium.append(dict(place=3, participant=third, prize_usd=200))
        write_json(self.out / "podium.json", podium)
        return podium


def engine_digest():
    h = hashlib.sha256()
    base = ROOT / "vendor" / "generals-bots"
    for p in sorted(base.rglob("*.py")):
        h.update(p.relative_to(base).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="Build the bot image; internet needed only during setup")
    validate = sub.add_parser("validate", help="Static validation; never executes participant code")
    validate.add_argument("files", type=Path, nargs="+")
    sub.add_parser("doctor", help="Check Docker, CPU availability and game-engine imports")
    for cmd in ("match", "tournament"):
        q = sub.add_parser(cmd)
        if cmd == "match":
            q.add_argument("bot0", type=Path)
            q.add_argument("bot1", type=Path)
            q.add_argument("--seed", type=int, help="Optional map seed for reproducible practice")
        else:
            q.add_argument("submissions", type=Path, help="Directory of participant_id.py files")
        q.add_argument("--out", type=Path, required=True, help="New, non-existing output directory")
        q.add_argument("--cpu", type=int, default=min(os.sched_getaffinity(0)))
        q.add_argument("--image", default=IMAGE)
        q.add_argument("--move-ms", type=int, default=150, help="Practice override; official value 150")
        q.add_argument("--max-turns", type=int, default=1200, help="Practice override; official value 1200")
        q.add_argument("--draw-seed", default="CODE-BOT-2026-10-02", help="Publish before results; league final tiebreak")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "build":
        subprocess.run(["docker", "build", "-t", IMAGE, str(ROOT)], check=True)
        return 0
    if args.command == "validate":
        for f in args.files:
            data = validate_file(f)
            print(json.dumps(dict(file=str(f), bytes=len(data), sha256=digest(data), static_check="passed")))
        return 0
    if args.command == "doctor":
        d = Docker()
        from engine import ENGINE_COMMIT, initial, observation
        state = initial(7)
        print(json.dumps(dict(docker=d.api("GET", "/version")["Version"], engine_commit=ENGINE_COMMIT,
                              cpus=sorted(os.sched_getaffinity(0)), board=[observation(state, 0)["height"],
                                                                       observation(state, 0)["width"]]), indent=2))
        subprocess.run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], check=True)
        return 0
    if args.cpu not in os.sched_getaffinity(0):
        raise ValueError("Selected CPU is not available to the evaluator.")
    if args.move_ms <= 0 or not 1 <= args.max_turns <= 1200:
        raise ValueError("Require positive --move-ms and --max-turns between 1 and 1200.")
    paths = [args.bot0, args.bot1] if args.command == "match" else sorted(args.submissions.glob("*.py"))
    if len(paths) < 2:
        raise ValueError("Supply at least two participants (exactly two files for a match).")
    # Validate every file before producing the snapshot directory.
    for path in paths:
        validate_file(path)
    args.out.mkdir(parents=True, exist_ok=False)
    event = None
    try:
        entries = freeze(paths, args.out)
        event = Event(args, entries, args.out)
        if args.command == "match":
            result = event.match(*entries, seed=args.seed)
        else:
            result = event.tournament()
        write_json(args.out / "completed.json", dict(result=result, finished_utc=datetime.now(timezone.utc).isoformat()))
        print(json.dumps(result, indent=2))
        return 0
    except BaseException as exc:
        write_json(args.out / "ABORTED.json", dict(error=str(exc), type=type(exc).__name__,
                                                   completed_games=len(event.matches) if event else 0))
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
