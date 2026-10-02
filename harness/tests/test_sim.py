"""Differential test: the bot's one-turn simulator (_sim) vs the real engine transition.

Random positions are built around both generals (random ownership and armies, random time
around the deathtouch threshold), random move pairs are drawn from the contact zone, and the
predicted outcome (winner, ownership and armies of every cell, minus growth) must equal the
engine's result.

Run: .venv/bin/python harness/tests/test_sim.py [cases]
"""
import importlib.util
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import runner  # noqa: E402  (sets JAX env)

e = runner.engine()
import jax.numpy as jnp  # noqa: E402

spec = importlib.util.spec_from_file_location("bot", ROOT / "bots" / "current.py")
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


def make_world(state, me):
    obs = e.observation(state, me)
    S = bot.World()
    S.ready = False
    bot._init(S, obs)
    gp = [int(x) for x in state.general_positions[1 - me]]
    S.eg = gp[0] * S.W + gp[1]
    return S


def run(cases=3000, seed=0):
    rng = random.Random(seed)
    bad = 0
    tested = 0
    outcomes = {}
    state0 = None
    for case in range(cases):
        if case % 300 == 0:
            state0 = e.initial(rng.randrange(1 << 30))
            H, W = (int(x) for x in state0.armies.shape)
            passable = [[bool(v) for v in row] for row in state0.passable.tolist()]
            gens = [tuple(int(x) for x in state0.general_positions[p]) for p in (0, 1)]
            worlds = [make_world(state0, 0), make_world(state0, 1)]
        # random contact zone: around a random general, both players own cells
        gr, gc = gens[rng.randrange(2)]
        arm = [[0] * W for _ in range(H)]
        own = [[-1] * W for _ in range(H)]
        for p in (0, 1):
            r, c = gens[p]
            own[r][c] = p
            arm[r][c] = rng.choice([1, 2, 3, 5, 10, 30])
        zone = []
        for r in range(max(0, gr - 3), min(H, gr + 4)):
            for c in range(max(0, gc - 3), min(W, gc + 4)):
                if passable[r][c] and (r, c) not in gens:
                    zone.append((r, c))
                    x = rng.random()
                    if x < 0.4:
                        own[r][c] = 0
                    elif x < 0.8:
                        own[r][c] = 1
                    if own[r][c] >= 0:
                        arm[r][c] = rng.choice([0, 1, 1, 2, 2, 3, 4, 5, 7, 10, 20])
        # place an attacker near the target general too
        t = rng.choice([500, 798, 799, 800, 801, 900, 1000])
        ownership = jnp.array([[[own[r][c] == p for c in range(W)] for r in range(H)] for p in (0, 1)])
        st = state0._replace(armies=jnp.array(arm, dtype=jnp.int32), ownership=ownership,
                             ownership_neutral=jnp.array([[passable[r][c] and own[r][c] < 0 for c in range(W)]
                                                          for r in range(H)]),
                             time=jnp.int32(t))
        # random moves (sometimes pass, sometimes split, sometimes into the general)
        acts = []
        for p in (0, 1):
            mine = [(r, c) for r in range(H) for c in range(W) if own[r][c] == p and arm[r][c] >= 2]
            if not mine or rng.random() < 0.1:
                acts.append([1, 0, 0, 0, 0])
                continue
            r, c = rng.choice(mine)
            acts.append([0, r, c, rng.randrange(4), 1 if rng.random() < 0.2 else 0])
        new, info = e.step(st, acts)
        winner = int(new.winner)
        done = bool(info.is_done)
        # bot prediction from player 0's perspective (and player 1's)
        for me in (0, 1):
            S = worlds[me]
            S.t = t
            N = H * W
            o0 = [0] * N
            a0 = [0] * N
            for r in range(H):
                for c in range(W):
                    i = r * W + c
                    a0[i] = arm[r][c]
                    if own[r][c] == me:
                        o0[i] = 1
                    elif own[r][c] == 1 - me:
                        o0[i] = 2

            def conv(a):
                if a[0] != 0:
                    return None
                s = a[1] * W + a[2]
                r, c = a[1] + (-1, 1, 0, 0)[a[3]], a[2] + (0, 0, -1, 1)[a[3]]
                if not (0 <= r < H and 0 <= c < W) or not passable[r][c]:
                    return "invalid"
                return (s, r * W + c, a[4])
            mm, em = conv(acts[me]), conv(acts[1 - me])
            if mm == "invalid" or em == "invalid":
                continue  # the bot never generates off-board/mountain moves
            res, ov_o, ov_a = bot._sim(S, o0, a0, mm, em, t)
            exp = None
            if done:
                exp = 0 if winner < 0 else (1 if winner == me else -1)
            ok = res == exp
            if ok and res is None:
                # compare every cell (engine armies minus growth)
                na = new.armies.tolist()
                no = new.ownership.tolist()
                nt = int(new.time)
                for r in range(H):
                    for c in range(W):
                        i = r * W + c
                        po = ov_o.get(i, o0[i])
                        pa = ov_a.get(i, a0[i])
                        eo = 1 if no[me][r][c] else (2 if no[1 - me][r][c] else 0)
                        ea = na[r][c]
                        if eo:
                            if nt % 50 == 0:
                                ea -= 1
                            if nt % 2 == 0 and (bool(new.generals[r][c]) or bool(new.castles[r][c])):
                                ea -= 1
                        if po != eo or (eo and pa != ea):
                            ok = False
            tested += 1
            outcomes[exp] = outcomes.get(exp, 0) + 1
            if not ok:
                bad += 1
                if bad <= 5:
                    print("MISMATCH case", case, "t", t, "me", me, "acts", acts, "pred", res, "exp", exp)
    print(f"{tested} predictions, {bad} mismatches, outcomes {outcomes}")
    return bad


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    sys.exit(1 if run(n) else 0)
