"""Offline evaluation of candidate-ranking formulas for the hidden enemy general.

Plays games in-process (our bot vs several opponent styles). Whenever our bot has seen enemy land
but not the general, every scoring formula ranks the candidates and we record the rank of the true
general (0 = best). Lower mean rank / higher top-1 and top-3 rates = better hunting target.

Usage: .venv/bin/python harness/rank_eval.py GAMES_PER_OPP
"""
import importlib.util
import multiprocessing as mp
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
OPPS = ["bots/archive/v6.py", "bots/opponents/hunter.py", "bots/opponents/rusher.py",
        "bots/opponents/kingstack.py", "bots/opponents/starter.py", "bots/opponents/expander.py"]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def formulas(S):
    """Return {name: {cand: score}} with higher = more likely."""
    dist = S.dist
    cands = list(S.cands)
    seen = [i for i in S.enemy_seen_cells if S.own[i] != 1]
    vis_enemy = list(S.enemy)
    L = S.opp_land
    out = {}
    # A: current heuristic (mean distance to remembered enemy cells)
    out["meandist"] = {c: -sum(dist[c][e] for e in seen) / max(1, len(seen)) for c in cands}
    # B: farthest remembered enemy cell (territory is a ball around the general)
    out["maxdist"] = {c: -max(dist[c][e] for e in seen) for c in cands}
    # C: ball model: share of remembered enemy cells inside the radius that holds L cells
    ball = {}
    for c in cands:
        ds = sorted(d for d in dist[c] if d < 9999)
        R = ds[min(len(ds) - 1, int(L * 1.5))]
        inside = sum(1 for e in seen if dist[c][e] <= R)
        ball[c] = (inside / max(1, len(seen)), R)
    out["ball"] = {c: ball[c][0] for c in cands}
    # D: ball + penalty for known non-enemy cells close to the candidate
    pen = {}
    for c in cands:
        dc = dist[c]
        R = ball[c][1]
        r2 = max(2, R // 2)
        tot = 0
        non = 0
        for i in S.passable:
            if dc[i] <= r2 and S.seen_ever[i]:
                tot += 1
                if S.mem_own[i] != 2:
                    non += 1
        pen[c] = non / tot if tot else 0.0
    out["ball_pen"] = {c: ball[c][0] - 1.0 * pen[c] for c in cands}
    out["pen_only"] = {c: -pen[c] for c in cands}
    out["mean_pen"] = {c: out["meandist"][c] - 6.0 * pen[c] for c in cands}
    # E: enemy castles as evidence (castles are built near home)
    cast = list(S.en_castles)
    if cast:
        out["castles"] = {c: -sum(dist[c][k] for k in cast) / len(cast) for c in cands}
        out["mean_castles"] = {c: out["meandist"][c] - 0.5 * sum(dist[c][k] for k in cast) / len(cast) for c in cands}
    else:
        out["castles"] = dict(out["meandist"])
        out["mean_castles"] = dict(out["meandist"])
    # F: unseen-neighbourhood: candidates whose surroundings we have never seen are more likely
    unk = {}
    for c in cands:
        dc = dist[c]
        tot = sum(1 for i in S.passable if dc[i] <= 3)
        un = sum(1 for i in S.passable if dc[i] <= 3 and not S.seen_ever[i])
        unk[c] = un / max(1, tot)
    out["unseen"] = unk
    out["mean_unseen"] = {c: out["meandist"][c] + 6.0 * unk[c] for c in cands}
    # G: far end of the enemy land as seen from our general (trails lead back to their general)
    dg = dist[S.myG]
    far = sorted(seen, key=lambda e: -dg[e])
    k3 = far[:3]
    out["farend"] = {c: -dist[c][far[0]] for c in cands}
    out["far3"] = {c: -sum(dist[c][e] for e in k3) / len(k3) for c in cands}
    out["far3_pen"] = {c: out["far3"][c] - 6.0 * pen[c] for c in cands}
    q = far[:max(1, len(far) // 3)]
    out["farthird"] = {c: -sum(dist[c][e] for e in q) / len(q) for c in cands}
    out["farthird_pen"] = {c: out["farthird"][c] - 6.0 * pen[c] for c in cands}
    out["mean_pen12"] = {c: out["meandist"][c] - 12.0 * pen[c] for c in cands}
    out["mean_pen3"] = {c: out["meandist"][c] - 3.0 * pen[c] for c in cands}
    out["mix"] = {c: 0.5 * out["meandist"][c] + 0.5 * out["farthird"][c] - 6.0 * pen[c] for c in cands}
    out["mix_unseen"] = {c: out["mix"][c] + 4.0 * unk[c] for c in cands}
    out["random"] = {c: random.random() for c in cands}
    return out


def job(args):
    import runner
    e = runner.engine()
    opp_path, seed, slot = args
    me = load(str(ROOT / "bots/current.py"), "me")
    op = load(str(ROOT / opp_path), "op")
    bots = [me, op] if slot == 0 else [op, me]
    st = e.initial(seed)
    H, W = (int(x) for x in st.armies.shape)
    gp = [int(x) for x in st.general_positions[1 - slot]]
    truth = gp[0] * W + gp[1]
    rows = []
    for t in range(500):
        obs = [e.observation(st, i) for i in (0, 1)]
        acts = [bots[i].act(obs[i]) for i in (0, 1)]
        S = me.S
        if t % 20 == 10 and S.eg is None and S.enemy_seen_cells and len(S.cands) >= 4 and truth in S.cands:
            fs = formulas(S)
            rec = {"n": len(S.cands), "t": t, "opp": opp_path}
            for name, sc in fs.items():
                ts = sc[truth]
                rec[name] = sum(1 for c, v in sc.items() if v > ts) + 0.5 * sum(1 for c, v in sc.items() if v == ts and c != truth)
            rows.append(rec)
        st, info = e.step(st, acts)
        if bool(info.is_done):
            break
    return rows


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    rng = random.Random()
    jobs = [(o, rng.randrange(1 << 31), k % 2) for o in OPPS for k in range(n)]
    with mp.get_context("spawn").Pool(6) as pool:
        res = pool.map(job, jobs)
    rows = [r for rs in res for r in rs]
    names = [k for k in rows[0] if k not in ("n", "t", "opp")]
    print(f"{len(rows)} situations, mean candidates {sum(r['n'] for r in rows) / len(rows):.1f}")
    print(f"{'formula':14s} {'meanrank':>8s} {'relrank':>8s} {'top1':>6s} {'top3':>6s}")
    for name in sorted(names, key=lambda k: sum(r[k] / r['n'] for r in rows)):
        mr = sum(r[name] for r in rows) / len(rows)
        rr = sum(r[name] / r["n"] for r in rows) / len(rows)
        t1 = sum(r[name] < 1 for r in rows) / len(rows)
        t3 = sum(r[name] < 3 for r in rows) / len(rows)
        print(f"{name:14s} {mr:8.2f} {rr:8.3f} {t1:6.2f} {t3:6.2f}")
    for o in OPPS:
        sub = [r for r in rows if r["opp"] == o]
        if sub:
            best = sorted(names, key=lambda k: sum(r[k] / r['n'] for r in sub))[:3]
            print(Path(o).stem, len(sub), "best:", [(b, round(sum(r[b] / r['n'] for r in sub) / len(sub), 3)) for b in best],
                  "meandist:", round(sum(r['meandist'] / r['n'] for r in sub) / len(sub), 3))


if __name__ == "__main__":
    main()
