"""Why do first strikes fail? Mirror games in-process with the true state: for each side's first real
march on a known general, record the stack at launch, the bot's estimate of the enemy general, the
true general army at launch and when the stack first gets within 2 cells, the stack size then, and
whether the game was won within 45 turns.

Usage: .venv/bin/python harness/strike_stats.py BOT_A BOT_B GAMES [workers]
"""
import importlib.util
import multiprocessing as mp
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def job(args):
    import runner
    e = runner.engine()
    a_path, b_path, seed = args
    bots = [load(a_path, "ma"), load(b_path, "mb")]
    st = e.initial(seed)
    H, W = (int(x) for x in st.armies.shape)
    gens = [tuple(int(x) for x in st.general_positions[p]) for p in (0, 1)]
    rec = [None, None]
    prev_phase = [None, None]
    winner, turns = -1, 1200
    for t in range(1200):
        obs = [e.observation(st, i) for i in (0, 1)]
        arm = st.armies.tolist()
        own = st.ownership.tolist()
        acts = [bots[i].act(obs[i]) for i in (0, 1)]
        for i in (0, 1):
            S = bots[i].S
            p = S.plan
            ph = p.get("phase") if p is not None else None
            eg = gens[1 - i]
            if rec[i] is None and ph == "march" and prev_phase[i] != "march" and S.eg is not None:
                # stack at launch = biggest of our cells near the launch cell
                L = p.get("launch")
                lr, lc = divmod(L, W)
                stack = max(arm[r][c] for r in range(max(0, lr - 1), min(H, lr + 2))
                            for c in range(max(0, lc - 1), min(W, lc + 2)) if own[i][r][c])
                rec[i] = dict(t=t, stack=stack, need=p.get("need"), est=bots[i]._eg_army_est(S),
                              gen_true=arm[eg[0]][eg[1]], dist=S.dist[L][S.eg], total=obs[i]["my_army"],
                              opp_total=obs[i]["opp_army"])
            prev_phase[i] = ph
            r_ = rec[i]
            if r_ is not None and "arr_t" not in r_ and t - r_["t"] <= 45:
                best = 0
                for r in range(max(0, eg[0] - 2), min(H, eg[0] + 3)):
                    for c in range(max(0, eg[1] - 2), min(W, eg[1] + 3)):
                        if own[i][r][c] and abs(r - eg[0]) + abs(c - eg[1]) <= 2 and arm[r][c] > best:
                            best = arm[r][c]
                if best >= 5:
                    r_["arr_t"] = t
                    r_["arr_stack"] = best
                    r_["arr_gen"] = arm[eg[0]][eg[1]]
        st, info = e.step(st, acts)
        if bool(info.is_done):
            winner = int(st.winner)
            turns = t + 1
            break
    for i in (0, 1):
        if rec[i] is not None:
            rec[i]["won45"] = winner == i and turns - rec[i]["t"] <= 45
            rec[i]["won"] = winner == i
    return [r for r in rec if r is not None]


def main():
    a, b, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    rng = random.Random()
    jobs = [(a, b, rng.randrange(1 << 31)) for _ in range(n)]
    with mp.get_context("spawn").Pool(workers, maxtasksperchild=10) as pool:
        res = pool.map(job, jobs, chunksize=1)
    rows = [r for rs in res for r in rs]
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
    for name, sub in (("SUCCESS", [r for r in rows if r["won45"]]), ("FAIL", [r for r in rows if not r["won45"]])):
        arr = [r for r in sub if "arr_t" in r]
        print(f"{name}: {len(sub)} first marches | launch t {med([r['t'] for r in sub])} stack {med([r['stack'] for r in sub])} "
              f"need {med([round(r['need'] or 0) for r in sub])} est_gen {med([r['est'] for r in sub])} true_gen {med([r['gen_true'] for r in sub])} "
              f"dist {med([r['dist'] for r in sub])} share {med([round(r['stack'] / max(1, r['total']), 2) for r in sub])}")
        print(f"   reached within 2 cells: {len(arr)}/{len(sub)} | travel {med([r['arr_t'] - r['t'] for r in arr])} turns, "
              f"stack on arrival {med([r['arr_stack'] for r in arr])}, general on arrival {med([r['arr_gen'] for r in arr])}")
    fails = [r for r in rows if not r["won45"]]
    never = sum("arr_t" not in r for r in fails)
    short = sum("arr_t" in r and r["arr_stack"] - 1 <= r["arr_gen"] for r in fails)
    other = len(fails) - never - short
    print(f"FAIL causes: never got within 2 cells with 5+ army {never}, arrived smaller than the general {short}, "
          f"arrived bigger but still failed {other}")
    under = sum(r["gen_true"] > (r["est"] or 0) + 3 for r in fails)
    print(f"general bigger than estimated at launch (by 4+): {under}/{len(fails)} fails, "
          f"{sum(r['gen_true'] > (r['est'] or 0) + 3 for r in rows if r['won45'])}/{len(rows) - len(fails)} successes")


if __name__ == "__main__":
    main()
