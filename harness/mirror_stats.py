"""What decides games between equal bots? Plays BOT_A vs BOT_B in-process, records per side when the
enemy general was found and economy snapshots, then reports how often the side that is ahead on each
feature wins.

Usage: .venv/bin/python harness/mirror_stats.py BOT_A BOT_B GAMES [workers]
"""
import importlib.util
import multiprocessing as mp
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
SNAP = (100, 150, 200, 250, 300)


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
    feat = [dict(found=None, plans=0), dict(found=None, plans=0)]
    last_plan = [None, None]
    winner = -1
    turns = 1200
    for t in range(1200):
        obs = [e.observation(st, i) for i in (0, 1)]
        acts = [bots[i].act(obs[i]) for i in (0, 1)]
        for i in (0, 1):
            S = bots[i].S
            if feat[i]["found"] is None and S.eg is not None:
                feat[i]["found"] = t
            p = S.plan
            if p is not None and p is not last_plan[i]:
                feat[i]["plans"] += 1
            last_plan[i] = p
            if p is not None and S.eg is not None and "plan_t" not in feat[i]:
                feat[i]["plan_t"] = t
                feat[i]["plan_need"] = p.get("need")
                feat[i]["plan_total"] = obs[i]["my_army"]
            if p is not None and p.get("phase") == "march" and S.eg is not None and "march_t" not in feat[i]:
                at = p.get("at")
                feat[i]["march_t"] = t
                feat[i]["march_army"] = S.arm[at] if at is not None else 0
                feat[i]["march_share"] = (S.arm[at] if at is not None else 0) / max(1, obs[i]["my_army"])
                feat[i]["home_at_march"] = S.arm[S.myG]
            if t in SNAP:
                feat[i][f"land{t}"] = obs[i]["my_land"]
                feat[i][f"army{t}"] = obs[i]["my_army"]
                feat[i][f"castles{t}"] = len(S.my_castles)
                feat[i][f"gen{t}"] = S.arm[S.myG]
        st, info = e.step(st, acts)
        if bool(info.is_done):
            winner = int(st.winner)
            turns = t + 1
            break
    return dict(winner=winner, turns=turns, feat=feat, seed=seed)


def main():
    a, b, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    rng = random.Random()
    jobs = [(a, b, rng.randrange(1 << 31)) for _ in range(n)]
    with mp.get_context("spawn").Pool(workers, maxtasksperchild=10) as pool:
        res = pool.map(job, jobs, chunksize=1)
    dec = [r for r in res if r["winner"] >= 0]
    print(f"{len(res)} games, {len(dec)} decided, slot0 wins {sum(r['winner'] == 0 for r in dec)}, "
          f"median length {sorted(r['turns'] for r in res)[len(res) // 2]}")
    keys = ["found"] + [f"{k}{t}" for t in SNAP for k in ("land", "army", "castles", "gen")]
    print(f"{'feature':12s} {'games':>5s} {'ahead wins':>10s}")
    for k in keys:
        n_ = 0
        w_ = 0
        for r in dec:
            f0, f1 = r["feat"][0].get(k), r["feat"][1].get(k)
            if k == "found":
                # earlier is better; never found = infinity
                f0 = 10 ** 6 if f0 is None else f0
                f1 = 10 ** 6 if f1 is None else f1
                if f0 == f1:
                    continue
                ahead = 0 if f0 < f1 else 1
            else:
                if f0 is None or f1 is None or f0 == f1:
                    continue
                ahead = 0 if f0 > f1 else 1
            n_ += 1
            w_ += ahead == r["winner"]
        if n_:
            print(f"{k:12s} {n_:5d} {w_ / n_:10.2f}")
    # strike timing
    n_ = w_ = 0
    for r in dec:
        m0, m1 = r["feat"][0].get("march_t"), r["feat"][1].get("march_t")
        m0 = 10 ** 6 if m0 is None else m0
        m1 = 10 ** 6 if m1 is None else m1
        if m0 == m1:
            continue
        n_ += 1
        w_ += (0 if m0 < m1 else 1) == r["winner"]
    print(f"first real strike march (general known): first striker wins {w_}/{n_}")
    for key in ("march_army", "march_share", "home_at_march"):
        n_ = w_ = 0
        for r in dec:
            f0, f1 = r["feat"][0].get(key), r["feat"][1].get(key)
            if f0 is None or f1 is None or f0 == f1:
                continue
            n_ += 1
            w_ += (0 if f0 > f1 else 1) == r["winner"]
        print(f"bigger {key} wins {w_}/{n_}")
    wm = [r["feat"][r["winner"]].get("march_army") for r in dec if r["feat"][r["winner"]].get("march_army")]
    lm = [r["feat"][1 - r["winner"]].get("march_army") for r in dec if r["feat"][1 - r["winner"]].get("march_army")]
    ws = [r["feat"][r["winner"]].get("march_share") for r in dec if r["feat"][r["winner"]].get("march_share")]
    ls = [r["feat"][1 - r["winner"]].get("march_share") for r in dec if r["feat"][1 - r["winner"]].get("march_share")]
    med = lambda x: sorted(x)[len(x) // 2] if x else None
    print("median first-march army: winner", med(wm), "loser", med(lm), "| share of total army: winner",
          round(med(ws) or 0, 2), "loser", round(med(ls) or 0, 2))
    print("winner never marched:", sum("march_t" not in r["feat"][r["winner"]] for r in dec),
          "loser never marched:", sum("march_t" not in r["feat"][1 - r["winner"]] for r in dec), "of", len(dec))
    rows = []
    for r in dec:
        f = r["feat"][r["winner"]]
        if f.get("found") is not None and f.get("plan_t") is not None and f.get("march_t") is not None:
            rows.append((f["found"], f["plan_t"] - f["found"], f["march_t"] - f["plan_t"], r["turns"] - f["march_t"],
                         f.get("plan_need") or 0, f.get("plan_total") or 0))
    if rows:
        med = lambda k: sorted(x[k] for x in rows)[len(rows) // 2]
        print(f"winner timeline medians over {len(rows)} games: found t{med(0)}, +{med(1)} until a strike is planned, "
              f"+{med(2)} gathering, +{med(3)} marching to the kill; need {med(4):.0f} of total army {med(5)}")
    fnd = [f["found"] for r in res for f in r["feat"] if f["found"] is not None]
    if fnd:
        fnd.sort()
        print("general found: median turn", fnd[len(fnd) // 2], "never:", sum(f["found"] is None for r in res for f in r["feat"]),
              "of", 2 * len(res))
    print("winner found the general before the game ended:",
          sum(r["feat"][r["winner"]]["found"] is not None for r in dec), "of", len(dec))
    print("loser had found the winner's general:", sum(r["feat"][1 - r["winner"]]["found"] is not None for r in dec), "of", len(dec))


if __name__ == "__main__":
    main()
