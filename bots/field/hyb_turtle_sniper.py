"""Deathtouch sniper test opponent (local testing only, not stdlib-single-file on purpose).

Plays exactly like bots/archive/v4.py until turn 760, then swarms: every turn it moves the stack
that is closest to the enemy general (with at least 2 army) one step closer, touches when adjacent
at turn >= 800, and prefers stacks approaching from directions not yet used.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sniper_base", str(Path(__file__).resolve().parent.parent / "opponents" / "turtle.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)


def act(obs):
    a = _base.act(obs)
    try:
        S = _base.S
        t = obs["turn"]
        if t < 760 or S is None:
            return a
        e = S.eg if S.eg is not None else _base._hunt_target(S, S.myG)
        if e is None:
            return a
        de = S.dist[e]
        own, arm = S.own, S.arm
        # touch
        if t >= 800 and S.eg is not None:
            for x in S.adj[e]:
                if own[x] == 1 and arm[x] >= 2:
                    return _base._mv(S, x, e)
        best = None
        for i in S.mine:
            if arm[i] < 2 or i == S.myG or de[i] >= 9999:
                continue
            for y in S.adj[i]:
                if de[y] < de[i] and (own[y] == 1 or arm[y] < arm[i] - 1):
                    k = (de[i], -arm[i])
                    if best is None or k < best[0]:
                        best = (k, i, y)
        if best is not None:
            return _base._mv(S, best[1], best[2])
    except Exception:
        pass
    return a
