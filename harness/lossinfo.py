"""Summarise how a recorded game ended: last N turns of the loser's general neighbourhood.
Usage: .venv/bin/python harness/lossinfo.py replay.jsonl LOSER_SLOT [turns_back]"""
import json, sys
path, loser = sys.argv[1], int(sys.argv[2])
back = int(sys.argv[3]) if len(sys.argv) > 3 else 12
recs = [json.loads(l) for l in open(path)]
init = recs[0]["initial"]
H, W = len(init["armies"]), len(init["armies"][0])
gen = None
for r in range(H):
    for c in range(W):
        if init["generals"][r][c] and init["ownership"][loser][r][c]:
            gen = (r, c)
print("loser general", gen, "game length", len(recs) - 1)
for rec in recs[-back - 1:-1]:
    st = rec["state"]; t = rec["turn"] + 1
    arm, own = st["armies"], st["ownership"]
    tot = [sum(arm[r][c] for r in range(H) for c in range(W) if own[p][r][c]) for p in (0, 1)]
    big = []
    for r in range(H):
        for c in range(W):
            if own[1 - loser][r][c] and arm[r][c] >= 10 and abs(r - gen[0]) + abs(c - gen[1]) <= 9:
                big.append((abs(r - gen[0]) + abs(c - gen[1]), arm[r][c], (r, c)))
    home = sum(arm[r][c] for r in range(H) for c in range(W)
               if own[loser][r][c] and abs(r - gen[0]) + abs(c - gen[1]) <= 2)
    print(f"t{t}: loser army {tot[loser]} winner army {tot[1-loser]} | general {arm[gen[0]][gen[1]]} home(r2) {home} | enemy stacks near (md, army, cell): {sorted(big)[:4]} | acts {rec['actions']}")
