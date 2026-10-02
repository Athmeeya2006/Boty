"""Code Bot single-file starter. Python 3.12 standard library only.
Participant: EXAMPLE ONLY
Bot: Frontier
Sources: organizer starter
AI assistance: organizer-provided example

Implement act(observation) and return [kind, row, col, direction, split].
Global variables persist during a game; a fresh process starts for each game.
"""
import random

_rng = random.Random(73)


def act(obs):
    owner, army, terrain = obs["owner"], obs["army"], obs["type"]
    choices = []
    for r in range(obs["height"]):
        for c in range(obs["width"]):
            if owner[r][c] != 1 or army[r][c] < 2:
                continue
            for direction, (dr, dc) in enumerate(((-1, 0), (1, 0), (0, -1), (0, 1))):
                nr, nc = r + dr, c + dc
                if not (0 <= nr < obs["height"] and 0 <= nc < obs["width"]):
                    continue
                if terrain[nr][nc] in (2, 5):
                    continue
                score = _rng.random()
                if owner[nr][nc] != 1:
                    score += 3
                if owner[nr][nc] == 2 and army[r][c] - 1 <= army[nr][nc]:
                    score -= 6
                if terrain[nr][nc] == 4 and owner[nr][nc] == 2:
                    score += 100
                choices.append((score, [0, r, c, direction, 0]))
    return max(choices, key=lambda x: x[0])[1] if choices else [1, 0, 0, 0, 0]
