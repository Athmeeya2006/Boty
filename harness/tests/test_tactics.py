"""Scenario tests for deathtouch tactics in the real engine.

Each scenario builds a position on a real generated map, lets the bot move, lets the scripted enemy
make its most dangerous move, and checks the outcome with the engine.

Run: .venv/bin/python harness/tests/test_tactics.py BOT [maps]
"""
import importlib.util
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import runner  # noqa: E402

e = runner.engine()
import jax.numpy as jnp  # noqa: E402

_n = [0]


def load(path):
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"tt{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def build(state0, own, arm, t):
    H, W = len(own), len(own[0])
    passable = state0.passable.tolist()
    ownership = jnp.array([[[own[r][c] == p for c in range(W)] for r in range(H)] for p in (0, 1)])
    return state0._replace(armies=jnp.array(arm, dtype=jnp.int32), ownership=ownership,
                           ownership_neutral=jnp.array([[bool(passable[r][c]) and own[r][c] < 0
                                                         for c in range(W)] for r in range(H)]),
                           time=jnp.int32(t))


def nbrs(passable, r, c):
    H, W = len(passable), len(passable[0])
    out = []
    for d, (dr, dc) in enumerate(((-1, 0), (1, 0), (0, -1), (0, 1))):
        rr, cc = r + dr, c + dc
        if 0 <= rr < H and 0 <= cc < W and passable[rr][cc]:
            out.append((rr, cc, d))
    return out


def mv(src, dst):
    d = {(-1, 0): 0, (1, 0): 1, (0, -1): 2, (0, 1): 3}[(dst[0] - src[0], dst[1] - src[1])]
    return [0, src[0], src[1], d, 0]


def main():
    bot_path = sys.argv[1]
    maps = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    rng = random.Random(7)
    res = {}

    def note(name, ok):
        a, b = res.get(name, (0, 0))
        res[name] = (a + (1 if ok else 0), b + 1)

    for k in range(maps):
        st0 = e.initial(rng.randrange(1 << 31))
        H, W = (int(x) for x in st0.armies.shape)
        passable = [[bool(v) for v in row] for row in st0.passable.tolist()]
        gens = [tuple(int(x) for x in st0.general_positions[p]) for p in (0, 1)]
        for me in (0, 1):
            en = 1 - me
            G, EG = gens[me], gens[en]

            def fresh():
                b = load(bot_path)
                b.act(e.observation(st0, me))     # turn 0: map analysis
                return b

            def base(garmy=5, egarmy=5):
                own = [[-1] * W for _ in range(H)]
                arm = [[0] * W for _ in range(H)]
                own[G[0]][G[1]] = me
                arm[G[0]][G[1]] = garmy
                own[EG[0]][EG[1]] = en
                arm[EG[0]][EG[1]] = egarmy
                return own, arm

            def play(state, enemy_action, bot):
                a = bot.act(e.observation(state, me))
                acts = [None, None]
                acts[me], acts[en] = a, enemy_action
                new, info = e.step(state, acts)
                return a, new, bool(info.is_done), int(new.winner)

            gn = nbrs(passable, *G)
            # --- A: enemy stack next to our general, we hold a bigger third tile: must chase it
            for (xr, xc, _) in gn:
                third = [(r, c) for (r, c, _) in nbrs(passable, xr, xc) if (r, c) != G]
                if not third:
                    continue
                own, arm = base()
                own[xr][xc] = en
                arm[xr][xc] = 6
                y = third[0]
                own[y[0]][y[1]] = me
                arm[y[0]][y[1]] = 9
                state = build(st0, own, arm, 805)
                a, new, done, w = play(state, mv((xr, xc), G), fresh())
                note("A defend by third-tile chase", not (done and w == en))
                break
            # --- C: we stand next to their general after 800: must touch and win
            egn = nbrs(passable, *EG)
            if egn:
                xr, xc, _ = egn[0]
                own, arm = base(egarmy=300)
                own[xr][xc] = me
                arm[xr][xc] = 3
                state = build(st0, own, arm, 801)
                a, new, done, w = play(state, [1, 0, 0, 0, 0], fresh())
                note("C touch when adjacent after 800", done and w == me)
                # --- D: before 800 with a bigger stack: must capture
                own, arm = base(egarmy=20)
                own[xr][xc] = me
                arm[xr][xc] = 40
                state = build(st0, own, arm, 500)
                a, new, done, w = play(state, [1, 0, 0, 0, 0], fresh())
                note("D capture when stronger before 800", done and w == me)
                # --- F: before 800 with a smaller stack: must NOT throw the stack away into the general
                own, arm = base(egarmy=50)
                own[xr][xc] = me
                arm[xr][xc] = 20
                state = build(st0, own, arm, 500)
                a = fresh().act(e.observation(state, me))
                note("F no suicide attack before 800", not (a[0] == 0 and (a[1], a[2]) == (xr, xc) and
                     (a[1] + (-1, 1, 0, 0)[a[3]], a[2] + (0, 0, -1, 1)[a[3]]) == EG))
            # --- E: enemy stack two steps out walks in; we hold armies around: must not lose in 2 turns
            for (xr, xc, _) in gn:
                outer = [(r, c) for (r, c, _) in nbrs(passable, xr, xc) if (r, c) != G]
                if not outer:
                    continue
                z = outer[0]
                own, arm = base(garmy=30)
                for (r, c, _) in gn:
                    own[r][c] = me
                    arm[r][c] = 4
                own[z[0]][z[1]] = en
                arm[z[0]][z[1]] = 12
                state = build(st0, own, arm, 810)
                bot = fresh()
                a, new, done, w = play(state, mv(z, (xr, xc)), bot)
                lost = done and w == en
                if not done:
                    # enemy now touches from X if it holds it with 2+
                    if bool(new.ownership[en][xr][xc]) and int(new.armies[xr][xc]) >= 2:
                        a, new, done, w = play(new, mv((xr, xc), G), bot)
                        lost = done and w == en
                note("E survive a two-step deathtouch approach", not lost)
                break
    bad = 0
    for name, (ok, n) in sorted(res.items()):
        print(f"{name:45s} {ok}/{n}")
        bad += n - ok
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
