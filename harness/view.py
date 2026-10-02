"""ASCII replay viewer for a recorded game (runner.py --record file.jsonl).

Usage: .venv/bin/python harness/view.py replay.jsonl 100 200 300
Cells: '#' mountain, '.' neutral, 'aNN' player 0, 'bNN' player 1; G general, C castle (capital letters).
"""
import json
import sys


def show(state, turn):
    arm, own, gen, cas, pas = (state[k] for k in ("armies", "ownership", "generals", "castles", "passable"))
    H, W = len(arm), len(arm[0])
    tot = [[0, 0], [0, 0]]
    lines = []
    for r in range(H):
        row = []
        for c in range(W):
            if not pas[r][c]:
                row.append("  ##")
                continue
            p = 0 if own[0][r][c] else (1 if own[1][r][c] else -1)
            a = arm[r][c]
            if p < 0:
                row.append("   .")
                continue
            tot[p][0] += 1
            tot[p][1] += a
            ch = "ab"[p]
            if gen[r][c]:
                ch = "AB"[p] if True else ch
                ch = "G" if p == 0 else "H"
            elif cas[r][c]:
                ch = "C" if p == 0 else "D"
            row.append(f"{ch}{min(a, 999):3d}")
        lines.append("".join(row))
    print(f"--- turn {turn}  p0 land {tot[0][0]} army {tot[0][1]} | p1 land {tot[1][0]} army {tot[1][1]}")
    print("\n".join(lines))


def main():
    path = sys.argv[1]
    turns = set(int(x) for x in sys.argv[2:])
    with open(path) as f:
        first = json.loads(f.readline())
        print("seed", first.get("seed"), "bots", first.get("bots"))
        if 0 in turns:
            show(first["initial"], 0)
        for line in f:
            rec = json.loads(line)
            t = rec["turn"] + 1
            if t in turns:
                print("actions that led here:", rec["actions"])
                show(rec["state"], t)


if __name__ == "__main__":
    main()
