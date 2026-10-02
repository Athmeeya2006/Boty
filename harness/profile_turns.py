"""Find the slowest turns of bots/current.py: plays games in-process and times each act() call.

Usage: .venv/bin/python harness/profile_turns.py OPP N_SEEDS
"""
import importlib.util
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import runner  # noqa

e = runner.engine()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    opp_path = sys.argv[1]
    n = int(sys.argv[2])
    worst = []
    for k in range(n):
        seed = random.randrange(1 << 31)
        for slot in (0, 1):
            me = load(ROOT / "bots" / "current.py", f"me{k}{slot}")
            op = load(opp_path, f"op{k}{slot}")
            bots = [me, op] if slot == 0 else [op, me]
            st = e.initial(seed)
            for t in range(1200):
                obs = [e.observation(st, i) for i in (0, 1)]
                acts = []
                for i in (0, 1):
                    t0 = time.perf_counter()
                    a = bots[i].act(obs[i])
                    dt = (time.perf_counter() - t0) * 1000
                    if bots[i] is me:
                        worst.append((dt, seed, slot, t, getattr(me.S, "layer", "?")))
                    acts.append(a)
                st, info = e.step(st, acts)
                if bool(info.is_done):
                    break
    worst.sort(reverse=True)
    for w in worst[:15]:
        print("%.1f ms seed %d slot %d turn %d layer %s" % w)


if __name__ == "__main__":
    main()
