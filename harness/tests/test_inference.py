"""Inference test: over full games, the bot's enemy-general candidate set must always contain the
true enemy general, a found general must be the true one, and S_opp (1 + castles not ours) must match
the engine's true structure count.

Run: .venv/bin/python harness/tests/test_inference.py BOT OPP [games]
"""
import importlib.util
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import runner  # noqa: E402

e = runner.engine()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    bot_path, opp_path = sys.argv[1], sys.argv[2]
    games = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    rng = random.Random()
    fails = 0
    checks = 0
    sizes = []
    leaks = 0
    for k in range(games):
        seed = rng.randrange(1 << 31)
        slot = k % 2
        me = load(bot_path, f"me{k}")
        op = load(opp_path, f"op{k}")
        bots = [me, op] if slot == 0 else [op, me]
        st = e.initial(seed)
        H, W = (int(x) for x in st.armies.shape)
        gp = [int(x) for x in st.general_positions[1 - slot]]
        true_g = gp[0] * W + gp[1]
        first_size = None
        for t in range(1200):
            obs = [e.observation(st, i) for i in (0, 1)]
            acts = [bots[i].act(obs[i]) for i in (0, 1)]
            S = me.S
            checks += 1
            if first_size is None:
                first_size = len(S.cands)
            bad = []
            if S.eg is not None and S.eg != true_g:
                bad.append("wrong general %s" % (divmod(S.eg, W),))
            if S.eg is None and true_g not in S.cands:
                bad.append("true general dropped from %d candidates" % len(S.cands))
            # structures: 1 + enemy castles
            castles = st.castles.tolist()
            own_e = st.ownership[1 - slot].tolist()
            true_sopp = 1 + sum(1 for r in range(H) for c in range(W) if castles[r][c] and own_e[r][c])
            if S.S_opp != true_sopp:
                bad.append("S_opp %d vs true %d" % (S.S_opp, true_sopp))
            if bad:
                fails += 1
                if fails <= 10:
                    print("seed", seed, "slot", slot, "turn", t, bad)
            st, info = e.step(st, acts)
            if bool(info.is_done):
                break
        leaks += me.S.opp_builds
        sizes.append((first_size, len(me.S.cands), me.S.eg is not None))
    print(f"{checks} turn checks, {fails} failures; candidate sizes (start, end, found): {sizes}; "
          f"enemy builds decoded: {leaks}")
    return fails


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
