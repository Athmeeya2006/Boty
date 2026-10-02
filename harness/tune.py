"""Self-play evolutionary tuner for the PARAMS dict (runs unattended).

Each generation:
  1. make K mutants of the champion (1 to 3 parameters changed each);
  2. champion and mutants all play the same fresh seeds against the pool (pool + the champion file);
  3. the best mutant is a candidate if its paired gain over the champion is positive by at least
     MIN_GAIN; it is then re-tested on fresh seeds against the champion and the pool, and promoted
     only if the confirmation is positive too (guards against lucky batches).
State: runs/tune/champion.py (best so far), runs/tune/log.jsonl (every generation).

Usage: .venv/bin/python harness/tune.py --base bots/current.py --pool a.py b.py ... [--hours 8]
"""
import argparse
import json
import multiprocessing as mp
import random
import re
import secrets
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import batch  # noqa: E402

# name: (low, high, is_int)
SPACE = {
    "OPEN_STACK": (4, 16, True), "OPEN_T": (40, 160, True), "RUN_STACK": (6, 30, True),
    "RUN_OPEN_MIN": (2, 20, True), "CASTLE_MOVE_COST": (0.5, 4.0, False), "CASTLE_DEPTH": (5, 12, True),
    "CASTLE_DANGER_R": (2, 8, True), "STACK_MIN": (20, 55, True), "GATHER_LAMBDA": (0.2, 1.5, False),
    "THREAT_R": (8, 20, True), "KILL_R": (3, 10, True), "INTERCEPT_R": (2, 7, True),
    "THREAT_MEM": (30, 300, True), "GARRISON_F": (0.0, 1.5, False), "DEF_MARGIN": (0, 10, True),
    "STRIKE_MARGIN": (0.9, 1.6, False), "STRIKE_EXTRA": (0, 20, True), "STRIKE_REINF": (0.0, 1.2, False),
    "STRIKE_T": (500, 760, True), "SCOUT_T": (60, 300, True), "HUNT_T": (30, 200, True),
    "HUNT_MIN": (8, 60, True), "HOARD_KEEP_F": (0.3, 1.2, False), "HOARD_LAND_RATIO": (0.5, 0.9, False), "CASTLE_MIN_SCORE": (40, 250, True), "HUNT_FILL": (0.0, 1.5, False), "EG_GROWTH": (0.15, 0.5, False), "HUNT_LIK": (0.3, 3.0, False), "SCOUT_W": (0.2, 1.5, False), "WALK_PEN": (0.2, 1.5, False), "FORT_T": (600, 790, True), "MOAT_MIN": (4, 40, True),
    "MOAT_R": (4, 12, True), "MOAT_CASTLE_T": (100, 600, True), "MOAT_CASTLE_BONUS": (0, 300, True),
    "STEALTH_COST": (0.0, 4.0, False), "STAGE_D": (2, 6, True), "RAID_MIN": (6, 30, True),
    "RAID_R": (4, 14, True), "KEEP_FREE_F": (0.0, 0.3, False), "CASTLE_LAST_T": (500, 780, True),
}


def read_params(src):
    out = {}
    for k in SPACE:
        m = re.search(r'\n\s*"%s":\s*([^,]+),' % k, src)
        if m:
            out[k] = float(m.group(1))
    return out


def write_variant(src, params, path):
    for k, v in params.items():
        lo, hi, is_int = SPACE[k]
        txt = str(int(round(v))) if is_int else ("%.3f" % v)
        src = re.sub(r'(\n\s*"%s":\s*)([^,]+)(,)' % k, lambda m: m.group(1) + txt + m.group(3), src, count=1)
    Path(path).write_text(src)


def mutate(params, rng):
    p = dict(params)
    changed = {}
    for k in rng.sample(sorted(p), rng.choice([1, 2, 3, 3, 4, 5])):
        lo, hi, is_int = SPACE[k]
        v = p[k]
        span = hi - lo
        nv = v + rng.gauss(0, 0.18) * span
        nv = min(hi, max(lo, nv))
        if is_int:
            nv = float(int(round(nv)))
            if nv == v:
                nv = min(hi, max(lo, v + rng.choice([-1, 1])))
        p[k] = nv
        changed[k] = (v, nv)
    return p, changed


def evaluate(pool, bots, opps, seeds, workers):
    jobs = [(b, o, s, slot, 1000, 1200) for s in seeds for o in opps for slot in (0, 1) for b in bots]
    res = pool.map(batch._job, jobs, chunksize=1)
    score = {}
    for r in res:
        if "error" in r:
            continue
        score[(r["bot"], r["opp"], r["seed"], r["slot"])] = (r["points"], r["forfeit"])
    return score


def paired(score, a, b):
    da = {k[1:]: v for k, v in score.items() if k[0] == a}
    db = {k[1:]: v for k, v in score.items() if k[0] == b}
    diffs = [da[k][0] - db[k][0] for k in da if k in db]
    ff = sum(v[1] for v in da.values())
    m, h = batch.ci95(diffs)
    return m, h, len(diffs), ff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--pool", nargs="+", required=True)
    ap.add_argument("--hours", type=float, default=8)
    ap.add_argument("--mutants", type=int, default=6)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--confirm-seeds", type=int, default=14)
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--min-gain", type=float, default=0.03)
    a = ap.parse_args()
    out = ROOT / "runs" / "tune"
    out.mkdir(parents=True, exist_ok=True)
    champ_path = out / "champion.py"
    if not champ_path.exists():
        shutil.copy(a.base, champ_path)
    rng = random.Random()
    end = time.time() + a.hours * 3600
    gen = 0
    ctx = mp.get_context("spawn")
    with ctx.Pool(a.workers, initializer=batch._init, maxtasksperchild=25) as pool:
        while time.time() < end:
            gen += 1
            src = champ_path.read_text()
            cp = read_params(src)
            muts = []
            for i in range(a.mutants):
                p, ch = mutate(cp, rng)
                path = out / f"mut_{i}.py"
                write_variant(src, p, path)
                muts.append((str(path), ch))
            frozen = out / "champ_frozen.py"
            shutil.copy(champ_path, frozen)
            opps = list(a.pool) + [str(frozen)]
            seeds = [secrets.randbits(32) for _ in range(a.seeds)]
            score = evaluate(pool, [str(champ_path)] + [m[0] for m in muts], opps, seeds, a.workers)
            results = []
            for path, ch in muts:
                m, h, n, ff = paired(score, path, str(champ_path))
                results.append((m, h, n, ff, path, ch))
            results.sort(key=lambda x: -x[0])
            m, h, n, ff, path, ch = results[0]
            rec = dict(gen=gen, time=time.strftime("%H:%M:%S"),
                       mutants=[dict(gain=round(r[0], 3), ci=round(r[1], 3), ff=r[3], change=r[5]) for r in results])
            promoted = False
            if m >= a.min_gain and ff == 0:
                seeds2 = [secrets.randbits(32) for _ in range(a.confirm_seeds)]
                score2 = evaluate(pool, [str(champ_path), path], opps, seeds2, a.workers)
                m2, h2, n2, ff2 = paired(score2, path, str(champ_path))
                rec["confirm"] = dict(gain=round(m2, 3), ci=round(h2, 3), n=n2, ff=ff2)
                if m2 > 0.01 and ff2 == 0 and (m * n + m2 * n2) / (n + n2) >= a.min_gain:
                    shutil.copy(path, champ_path)
                    shutil.copy(path, out / f"champion_gen{gen}.py")
                    promoted = True
            rec["promoted"] = promoted
            with open(out / "log.jsonl", "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(json.dumps(rec), flush=True)


if __name__ == "__main__":
    main()
