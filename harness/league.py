"""Local league that mirrors the official format: full round robin, each pair plays two games on
fresh maps with swapped starting slots, win 1 / draw 0.5 / loss 0. Repeated for several rounds.

Usage: .venv/bin/python harness/league.py DIR_OF_BOTS --rounds 3 --me KashyapBot [--workers 6]
"""
import argparse
import itertools
import json
import multiprocessing as mp
import secrets
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import batch  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--me", default="KashyapBot")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out")
    a = ap.parse_args()
    bots = sorted(str(p) for p in Path(a.dir).glob("*.py"))
    jobs = []
    for _ in range(a.rounds):
        for x, y in itertools.combinations(bots, 2):
            jobs.append((x, y, secrets.randbits(32), 0, 1000, 1200))   # x in slot 0
            jobs.append((x, y, secrets.randbits(32), 1, 1000, 1200))   # x in slot 1
    print(f"{len(bots)} bots, {len(jobs)} games", flush=True)
    with mp.get_context("spawn").Pool(a.workers, initializer=batch._init, maxtasksperchild=25) as pool:
        res = pool.map(batch._job, jobs, chunksize=1)
    pts = defaultdict(float)
    wdl = defaultdict(lambda: [0, 0, 0])
    games = defaultdict(int)
    h2h = defaultdict(lambda: [0, 0, 0])
    ff = defaultdict(int)
    for r in res:
        if "error" in r:
            print("INFRA", r)
            continue
        x, y = r["bot"], r["opp"]
        px = r["points"]
        py = 0.0 if r["reason"] == "double_forfeit" else 1.0 - px
        for b, p in ((x, px), (y, py)):
            pts[b] += p
            games[b] += 1
            wdl[b][0 if p == 1 else (1 if p == 0.5 else 2)] += 1
        ff[x] += r["forfeit"]
        me = [b for b in (x, y) if Path(b).stem == a.me]
        if me:
            other = y if me[0] == x else x
            p = px if me[0] == x else py
            h2h[Path(other).stem][0 if p == 1 else (1 if p == 0.5 else 2)] += 1
    print(f"\n{'rank':>4s} {'bot':24s} {'pts':>6s} {'games':>5s} {'pts/g':>6s} {'W':>4s} {'D':>4s} {'L':>4s}")
    for i, b in enumerate(sorted(bots, key=lambda b: -pts[b]), 1):
        w, d, l = wdl[b]
        mark = " <== us" if Path(b).stem == a.me else ""
        print(f"{i:4d} {Path(b).stem:24s} {pts[b]:6.1f} {games[b]:5d} {pts[b] / max(1, games[b]):6.3f} {w:4d} {d:4d} {l:4d}{mark}")
    print(f"\n{a.me} head to head (W-D-L):")
    for o, (w, d, l) in sorted(h2h.items(), key=lambda kv: (kv[1][0] - kv[1][2])):
        print(f"   vs {o:22s} {w}-{d}-{l}")
    if a.out:
        Path(a.out).write_text(json.dumps([{k: v for k, v in r.items() if k != "times"} for r in res]))


if __name__ == "__main__":
    main()
