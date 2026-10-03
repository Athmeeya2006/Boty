"""Fuzz test: act() must always return a valid action, whatever it is given.

Cases:
  * real observations from random engine states at random turns, given to a FRESH module (cold start
    in the middle of a game, both slots);
  * the same with corrupted fields (missing keys, wrong types, wrong sizes, negative numbers);
  * a full game where the bot is fed only every k-th observation (turn jumps);
  * pathological boards (no own cells, everything fog).
Run: .venv/bin/python harness/tests/test_fuzz.py BOT [cases]
"""
import copy
import importlib.util
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import runner  # noqa: E402

e = runner.engine()
_n = [0]


def load(path):
    _n[0] += 1
    spec = importlib.util.spec_from_file_location(f"fz{_n[0]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def check(action, where):
    try:
        runner.validate_action(action)
        return 0
    except Exception as exc:
        print("INVALID", where, repr(action), exc)
        return 1


def corrupt(obs, rng):
    o = copy.deepcopy(obs)
    k = rng.randrange(12)
    if k == 0:
        del o[rng.choice(list(o))]
    elif k == 1:
        o["type"] = o["type"][:-1]
    elif k == 2:
        o["army"][0] = o["army"][0][:-2]
    elif k == 3:
        o["turn"] = rng.choice([-5, 10 ** 9, None, "7", 3.5])
    elif k == 4:
        o["height"], o["width"] = o["width"] + 3, o["height"] + 2
    elif k == 5:
        o["owner"] = [[0] * o["width"] for _ in range(o["height"])]
    elif k == 6:
        o["type"] = [[0] * o["width"] for _ in range(o["height"])]
    elif k == 7:
        o["army"] = [[rng.choice([-3, 0, 10 ** 9]) for _ in range(o["width"])] for _ in range(o["height"])]
    elif k == 8:
        o["owner"] = [[rng.randrange(3) for _ in range(o["width"])] for _ in range(o["height"])]
    elif k == 9:
        o["type"] = [[rng.randrange(6) for _ in range(o["width"])] for _ in range(o["height"])]
    elif k == 10:
        o["opp_army"] = None
        o["my_army"] = "x"
    else:
        o["player_id"] = rng.choice([5, None, -1])
    return o


def main():
    bot_path = sys.argv[1]
    cases = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    rng = random.Random(12345)
    bad = 0
    n = 0
    starter = load(str(ROOT / "bots/opponents/starter.py"))
    for g in range(max(1, cases // 60)):
        st = e.initial(rng.randrange(1 << 31))
        live = load(bot_path)      # plays the whole game normally
        corrupted_live = [False]
        skip = load(bot_path)      # sees only some observations
        for t in range(1200):
            obs = [e.observation(st, i) for i in (0, 1)]
            e0 = getattr(live, "ERRORS", 0)
            a0 = live.act(obs[0])
            bad += check(a0, ("live", t))
            if getattr(live, "ERRORS", 0) != e0 and not corrupted_live[0]:
                bad += 1
                if bad < 5:
                    print("INTERNAL EXCEPTION on a normal observation at turn", t)
            n += 1
            if rng.random() < 0.3:
                bad += check(skip.act(obs[0]), ("skip", t))
                n += 1
            if rng.random() < 0.05:
                for slot in (0, 1):
                    fresh = load(bot_path)
                    bad += check(fresh.act(obs[slot]), ("cold", t, slot))
                    bad += check(fresh.act(corrupt(obs[slot], rng)), ("cold-corrupt", t, slot))
                    n += 2
                bad += check(live.act(corrupt(obs[0], rng)), ("live-corrupt", t))
                corrupted_live[0] = True   # state may be damaged afterwards: exceptions tolerated
                # after a corrupted call the bot must keep working on the real stream
                n += 1
            a1 = starter.act(obs[1]) if rng.random() < 0.9 else [1, 0, 0, 0, 0]
            st, info = e.step(st, [a0, a1])
            if bool(info.is_done):
                break
    # degenerate inputs
    fresh = load(bot_path)
    for junk in (None, {}, [], 5, {"turn": 0}, {"turn": 0, "height": 18, "width": 18}):
        bad += check(fresh.act(junk), ("junk", junk))
        n += 1
    print(f"{n} calls, {bad} invalid returns")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
