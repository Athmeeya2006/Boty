"""Economy benchmark: a bot plays against pass_bot with hunting/striking disabled, and we record its
army, land and castle count at checkpoints. Same seeds for every bot (paired), in-process, parallel.

Usage: .venv/bin/python harness/econ.py SEEDS bot1.py [bot2.py ...]
"""
import importlib.util
import multiprocessing as mp
import random
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import os
CHECK = tuple(int(x) for x in os.environ.get('ECON_CHECK', '50,100,150,200,300').split(','))
NOHUNT = {"HUNT_T": "99999", "SCOUT_T": "99999", "STRIKE_T": "99999"}


def neutered(path):
    src = open(path).read()
    for k, v in NOHUNT.items():
        src = re.sub(r'(\n\s*"%s":\s*)([^,]+)(,)' % k, lambda m: m.group(1) + v + m.group(3), src, count=1)
    f = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False)
    f.write(src)
    f.close()
    return f.name


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def job(args):
    import runner
    e = runner.engine()
    path, seed, slot = args
    me = load(path, "me")
    op = load(str(ROOT / "bots/opponents/pass_bot.py"), "op")
    bots = [me, op] if slot == 0 else [op, me]
    st = e.initial(seed)
    out = {}
    for t in range(max(CHECK) + 1):
        obs = [e.observation(st, i) for i in (0, 1)]
        if t in CHECK:
            o = obs[slot]
            out[t] = (o["my_army"], o["my_land"], len(me.S.my_castles) if getattr(me, "S", None) else 0)
        acts = [bots[i].act(obs[i]) for i in (0, 1)]
        st, info = e.step(st, acts)
        if bool(info.is_done):
            break
    return path, seed, slot, out


def main():
    n = int(sys.argv[1])
    bots = sys.argv[2:]
    tmp = {b: neutered(b) for b in bots}
    seeds = [random.randrange(1 << 31) for _ in range(n)]
    jobs = [(tmp[b], s, k % 2) for b in bots for k, s in enumerate(seeds)]
    with mp.get_context("spawn").Pool(int(os.environ.get('ECON_WORKERS', '4'))) as pool:
        res = pool.map(job, jobs)
    inv = {v: k for k, v in tmp.items()}
    for b in bots:
        rs = [r for r in res if r[0] == tmp[b]]
        line = []
        for t in CHECK:
            vals = [r[3][t] for r in rs if t in r[3]]
            if vals:
                a = sum(v[0] for v in vals) / len(vals)
                l = sum(v[1] for v in vals) / len(vals)
                c = sum(v[2] for v in vals) / len(vals)
                line.append(f"t{t}: army {a:6.0f} land {l:5.1f} castles {c:4.1f}")
        print(Path(inv[rs[0][0]]).stem if rs else b)
        print("   " + "\n   ".join(line))


if __name__ == "__main__":
    main()
