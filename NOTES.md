# NOTES: version log

Results are points per game (win 1, draw 0.5, loss 0) over paired seeds (each seed in both slots).
Opponents: starter (organizer), expander and hunter (stdlib ports of engine agents), rusher (hoards then
drives at the inferred enemy general), pass_bot.

## v1 (2 Oct ~19:40 IST)
Map analysis (all-pairs BFS), enemy general candidates (spawn rule), castle leak + opp_army accounting,
gather tree with DP pruning, castle plans (walk a stack to a cheap site, build), claims, defense
(kill adjacent stacks, intercept, emergency gather), strike/hunt plan, exact 2-ply tactical search near
both generals (simulator verified against the engine: 6606 random cases, 0 mismatches).
Result: starter 1.00, expander 0.95, hunter 0.66, rusher 0.66 (16 seeds x 2 slots).

## v2
* Defense rewritten: kill, intercept (walk a beating stack out to an enemy stack within 4), emergency
  gather, long-memory garrison (0.8 x biggest enemy wave seen near home in last 100 turns).
* General only funds castles close to home, keeping the garrison as leftover, when threats exist.
* Hunting starts at turn 100 once enemy land is seen (was 450). General feeds its surplus above the
  garrison into the strike.
* New exact inference: an enemy cell at walking distance d from their general needs d owned path
  cells, so d <= opp_land - 1 (+ cells we took from them) and d <= turn - 2.
Result vs v1 (paired, 128 pairs): +0.059 +- 0.068. Pool: starter .98, hunter .81, rusher .84, expander 1.0.

## v3
Parameter variant "aggro": HUNT_T 50, HUNT_MIN 15, SCOUT_T 120, CASTLE_MIN_SCORE 150 (fewer castles,
earlier hunting). Beat v2-params head-to-head 24-8; pool +0.031 +- 0.059. Turtle variant (no hunting,
big garrison) lost every game: passivity loses in this ruleset.

## v4
* Found the bot passing 171 of 263 turns vs Hunter: the general's army was locked as garrison.
  The general now keeps sending expansion runs (half splits above the garrison) while open land
  borders us, walking through own land to the frontier.
* Fixed two ping-pong bugs: strike gathers never draw from the general (only its half-feed above the
  garrison); garrison upkeep pauses during a strike; emergency defense cancels a gathering strike;
  a lost strike stack is never replaced by the general or a castle.
* Strike gathers leave small frontier stacks alone so they keep claiming land.
Result vs v3 (paired, 140 pairs): +0.107 +- 0.093. Hunter 28-0, rusher .89, starter 1.0.

## v5 (2 Oct ~21:15 IST)
* Economy: measured with harness/econ.py (bot vs pass_bot, hunting off). Castles compound: about
  10,000 army and 45 castles by turn 800. A "land first, castles after turn 350" gate was 3% ahead at
  turn 200 but far behind later and lost long games, so it is off. General can fund castles with a
  half split while keeping its garrison.
* Emergency defense: new k-move gather (best army reachable within k moves, greedy by path ratio).
  The old threshold gather selected nothing when all nearby cells held 2.
* Counter-intercept: if the fast gather cannot cover a threat, hit the stack with our biggest stack that
  can reach it first (combat destroys equal amounts), unless our own strike provably lands first.
* Deathtouch defense: moat (every neighbour of our general holds at least the biggest enemy stack that
  can reach it), general's own army moves onto the moat after 800, tactical eval looks one step further.
* Garrison upkeep keeps running during a strike march.
* Inference: hidden enemy land must link their general to the cells we see:
  dist(general, visible enemy cells) <= opp_land - visible enemy cells + cells we took.
  test_inference: 5558 turn checks, 0 failures.
Result vs v4 (paired, 120 pairs): +0.092 +- 0.080. Rusher 24-0, hunter 21-3, v4 15-9, sniper 16-8.
Real bot vs defensive non-hunting opponents (turtle, v4_nohunt, sniper_nh): 69 W, 3 D, 0 L.

## Research notes (generals.io wiki, strakam RL blog, generals.bot rules)
Rules differ from classic generals.io (bonus every 50 not 25, structures +1 per 2 turns, free neutral
land, built castles, deathtouch, chase/reinforce/smaller-first order), so only these carry over:
take enemy land over neutral (2-cell swing), expand in several directions for warning time, strike
from the fog because defenders react to what they see.
Exploits to build against Claude-style bots: (1) multi-direction adjacency exactly at turn 800,
(2) raids on young enemy castles (visible through fog, near 0 army), (3) early kills of thin generals,
(4) approach paths outside enemy vision.

## v6 / v7 (2 Oct ~22:20 IST)
v6: strike launch cell must be in our main connected territory (an isolated outpost made the strike
think only 19 to 64 army was gatherable, causing 1200-turn draws); staged turn-800 strike (wait 4 cells
out, step adjacent on 799, touch on 800); castle raids (enemy castles are visible through fog at build
time; a nearby stack that beats the estimated army takes them).
v7: stealth strike path (cost per cell the enemy can see), scouting expansion after turn 50 (claims
nearer the candidate region and claims uncovering candidates score higher; run stacks walk through own
land to a better frontier point).
Results: v6 vs v5 +0.022 +- 0.063 (160 pairs), v7 vs v6 +0.016 +- 0.062 (192 pairs): not significant
but no draws left and faster wins. Safety run v6: 100 games at 150 ms, 0 forfeits, max turn 50 ms.

## Things measured and rejected
* Holding army at home (active garrison from enemy free army 0.4: -0.23; passive "never spend below
  0.2 to 0.5 x enemy free army": 0.55 to 0.62 vs 0.68). Initiative beats caution in this ruleset.
* Land-first castle gate (castles only after turn 350): better at turn 200, loses long games.
* Deploying the general before each land bonus: +0.5 land at turn 50, but 33 W / 50 L vs v6.
* Scouting expansion from turn 0: -0.095.
* 18 single-parameter variants (runs/sweep1.json): none beat the base; parameters are near a local optimum.
* Reinforcement learning / neural policy: not feasible (stdlib-only inference in 150 ms, no GPU, hours
  not weeks of self-play). Self-play parameter evolution (harness/tune.py) runs instead.

## Tests added
* harness/tests/test_sim.py: simulator vs engine, 6606 cases, 0 mismatches.
* harness/tests/test_inference.py: candidate set always contains the true general; S_opp exact.
* harness/tests/test_fuzz.py: 3161 calls (cold starts, corrupted observations), 0 invalid returns.
* harness/tests/test_tactics.py: 100 deathtouch scenario checks in the real engine, all pass.
* harness/rank_eval.py: offline ranking of hidden-general candidates against the truth (323 situations).
  Best formula (mean distance to enemy land + distance to the far end of it + penalty for known
  non-enemy surroundings) improves the true general's mean rank from 6.4 to 5.4 of about 20.

## v8, v9, v10 (2 Oct 22:30 to 3 Oct 00:10 IST)
v8: likelihood-ranked hunting (harness/rank_eval.py formula). vs v7: +0.075 +- 0.073 (120 pairs).
v9: "greedy" parameter hybrid found by the local 16-bot league (OPEN_STACK 5, RUN_STACK 6, HUNT_T 150,
    HUNT_MIN 40, GARRISON_F 0.3). vs v8: +0.113 +- 0.094 (128 pairs). League: we were 4-0 against
    every independent design; only our own parameter variants scored higher.
v10: opponent-adaptive hoarder rule (enemy land < 0.7 x ours with free army: general keeps 0.7 x their
     free army), defense order changed to reinforce-before-intercept, strike gathers route through small
     frontier cells without draining them. vs rush/hunter bots: 200 W, 0 L (previous build lost 6 on the
     same seeds, paired +0.030 +- 0.024). vs strong pool (v9, v8, sniper, late-strike hybrid):
     +0.016 +- 0.092 (160 pairs). Fuzz 1224 calls and 80 tactics checks pass. Submission = v10.

## Machine note
The laptop crashed twice (20:50 and 23:48) from a global out-of-memory: each game worker holds
0.5 to 0.9 GB (JAX engine) and I had up to 17 running. Fix: at most 9 workers in total, pools recycle
workers (maxtasksperchild), and heavy jobs run through harness/safe.sh (systemd memory-capped scope).
