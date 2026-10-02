"""Parallel batches with paired seeds (each seed played in both slots), stats and timing report.

Examples:
  # one bot against a pool, 50 seeds x 2 slots per opponent
  .venv/bin/python harness/batch.py --bots bots/current.py --opps bots/opponents/starter.py --seeds 50
  # paired comparison: two bots play the same seeds/opponents/slots, CI on the difference
  .venv/bin/python harness/batch.py --bots bots/current.py bots/archive/v1.py --opps ... --seeds 100

Seeds are fresh random numbers each run unless --seed-file is given (held-out set).
"""
import argparse
import json
import math
import multiprocessing as mp
import os
import secrets
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))


def _init():
    import runner  # noqa: F401  (sets env, imports engine lazily)
    runner.engine()


def _job(args):
    import runner
    bot, opp, seed, slot, move_ms, max_turns = args
    paths = [bot, opp] if slot == 0 else [opp, bot]
    t0 = time.time()
    try:
        r = runner.play_game(paths, seed, move_ms=move_ms, max_turns=max_turns)
    except Exception as exc:  # infrastructure failure, not a bot fault
        return dict(bot=bot, opp=opp, seed=seed, slot=slot, error=repr(exc))
    me = slot
    return dict(bot=bot, opp=opp, seed=seed, slot=slot, points=r["scores"][me], reason=r["reason"],
                turns=r["turns"], won=r["winner"] == me, lost=r["winner"] == 1 - me,
                forfeit=(r["reason"] in ("forfeit", "double_forfeit") and r.get("faults", [None, None])[me] is not None),
                fault=r.get("faults", [None, None])[me], times=r["times"][me], wall=time.time() - t0,
                hw=(r["height"], r["width"]))


def ci95(xs):
    n = len(xs)
    if n < 2:
        return (sum(xs) / max(n, 1), float("nan"))
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, 1.96 * math.sqrt(var / n)


def pct(s, q):
    return s[min(len(s) - 1, int(len(s) * q))] if s else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bots", nargs="+", required=True)
    ap.add_argument("--opps", nargs="+", required=True)
    ap.add_argument("--seeds", type=int, default=20, help="seeds per opponent (each played in both slots)")
    ap.add_argument("--seed-file", help="JSON list of seeds (held-out set)")
    ap.add_argument("--workers", type=int, default=max(1, os.cpu_count() - 2))
    ap.add_argument("--move-ms", type=int, default=1000, help="deadline used for forfeits (timing reported anyway)")
    ap.add_argument("--max-turns", type=int, default=1200)
    ap.add_argument("--out", help="write all game results to this JSON file")
    a = ap.parse_args()

    if a.seed_file:
        seeds = json.loads(Path(a.seed_file).read_text())[: a.seeds]
    else:
        seeds = [secrets.randbits(32) for _ in range(a.seeds)]
    jobs = []
    for seed in seeds:
        for opp in a.opps:
            for slot in (0, 1):
                for bot in a.bots:
                    jobs.append((bot, opp, seed, slot, a.move_ms, a.max_turns))
    print(f"{len(jobs)} games on {a.workers} workers", flush=True)
    t0 = time.time()
    results = []
    ctx = mp.get_context("spawn")
    with ctx.Pool(a.workers, initializer=_init, maxtasksperchild=40) as pool:
        for i, r in enumerate(pool.imap_unordered(_job, jobs), 1):
            results.append(r)
            if i % max(1, len(jobs) // 20) == 0:
                print(f"  {i}/{len(jobs)} done, {time.time() - t0:.0f}s", flush=True)
    if a.out:
        slim = [{k: v for k, v in r.items() if k != "times"} for r in results]
        Path(a.out).write_text(json.dumps(dict(seeds=seeds, results=slim)))

    errs = [r for r in results if "error" in r]
    for r in errs:
        print("INFRA ERROR", r)
    results = [r for r in results if "error" not in r]

    print(f"\n=== {len(results)} games in {time.time() - t0:.0f}s ===")
    for bot in a.bots:
        rs = [r for r in results if r["bot"] == bot]
        print(f"\n## {bot}")
        print(f"{'opponent':40s} {'W':>4s} {'D':>4s} {'L':>4s} {'pts/g':>6s} {'+-95':>6s} {'winT':>6s} {'lossT':>6s} {'FF':>3s}")
        for opp in a.opps + ["ALL"]:
            sub = [r for r in rs if opp == "ALL" or r["opp"] == opp]
            if not sub:
                continue
            w = sum(r["won"] for r in sub)
            l = sum(r["lost"] for r in sub)
            d = len(sub) - w - l
            m, h = ci95([r["points"] for r in sub])
            wt = [r["turns"] for r in sub if r["won"]]
            lt = [r["turns"] for r in sub if r["lost"]]
            ff = sum(r["forfeit"] for r in sub)
            print(f"{Path(opp).stem if opp != 'ALL' else 'ALL':40s} {w:4d} {d:4d} {l:4d} {m:6.3f} {h:6.3f} "
                  f"{(sum(wt) / len(wt) if wt else 0):6.0f} {(sum(lt) / len(lt) if lt else 0):6.0f} {ff:3d}")
        reasons = defaultdict(int)
        for r in rs:
            reasons[r["reason"]] += 1
        print("reasons:", dict(reasons))
        for r in rs:
            if r["forfeit"]:
                print("  FORFEIT", r["opp"], r["seed"], r["slot"], r["fault"])
        allt = sorted(t for r in rs for t in r["times"][1:])
        firsts = sorted(r["times"][0] for r in rs if r["times"])
        if allt:
            print(f"timing ms: p50 {pct(allt, .5):.1f}  p99 {pct(allt, .99):.1f}  p99.9 {pct(allt, .999):.1f}  "
                  f"max {allt[-1]:.1f}  over150 {sum(t > 150 for t in allt)}  first-call max {firsts[-1]:.0f}")
        losses = [(Path(r["opp"]).stem, r["seed"], r["slot"], r["turns"]) for r in rs if r["lost"]]
        if losses:
            print("losses (opp, seed, slot, turn):", losses[:30])
        draws = [(Path(r["opp"]).stem, r["seed"], r["slot"]) for r in rs if not r["won"] and not r["lost"]]
        if draws:
            print("draws (opp, seed, slot):", draws[:20])

    if len(a.bots) == 2:
        key = lambda r: (r["opp"], r["seed"], r["slot"])
        pa = {key(r): r["points"] for r in results if r["bot"] == a.bots[0]}
        pb = {key(r): r["points"] for r in results if r["bot"] == a.bots[1]}
        diffs = [pa[k] - pb[k] for k in pa if k in pb]
        m, h = ci95(diffs)
        print(f"\nPAIRED {Path(a.bots[0]).stem} - {Path(a.bots[1]).stem}: {m:+.3f} +- {h:.3f} over {len(diffs)} pairs")


if __name__ == "__main__":
    main()
