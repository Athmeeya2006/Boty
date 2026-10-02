"""Stdlib port of generals/agents/expander_agent.py (test opponent).

Pick a random move weighted by source army, x10 for captures it can win, x2 more on enemy cells.
"""
import random

_rng = random.Random(5)


def act(obs):
    H, W = obs["height"], obs["width"]
    typ, own, arm = obs["type"], obs["owner"], obs["army"]
    moves = []
    weights = []
    for r in range(H):
        for c in range(W):
            if own[r][c] != 1 or arm[r][c] < 2:
                continue
            for d, (dr, dc) in enumerate(((-1, 0), (1, 0), (0, -1), (0, 1))):
                nr, nc = r + dr, c + dc
                if not (0 <= nr < H and 0 <= nc < W) or typ[nr][nc] in (2, 5):
                    continue
                a = arm[r][c]
                if a <= arm[nr][nc] + 1:
                    continue
                w = float(a)
                if own[nr][nc] != 1:
                    w *= 10.0
                    if own[nr][nc] == 2:
                        w *= 2.0
                moves.append([0, r, c, d, 0])
                weights.append(w)
    if not moves:
        return [1, 0, 0, 0, 0]
    return _rng.choices(moves, weights)[0]
