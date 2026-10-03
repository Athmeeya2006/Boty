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

## v11 (3 Oct ~03:00 IST) = submission
Measured on paired fresh seeds (deterministic bots, so identical games cancel exactly):
* Castles delayed to turn 500, with a parity exception (build earlier only if the enemy, whose castles
  we see through fog, has more than we do). First-400: +0.090 +- 0.087; first-500/600: +0.099 +- 0.078;
  never: +0.094; a later seed set showed +0.008 +- 0.067. Mid-game moves are worth more as strike
  gathering than as castles.
* Threat summing fixed: stacks that can arrive together are summed, but only visible stacks >= 12
  (summing remembered cells double-counted one moving stack and cost -0.22). +0.025 +- 0.028.
* Bug fix: in _static_eval an `else` had become a for-else, so the pre-800 "adjacent stack captures
  next turn" check never ran. Neutral in results (-0.007 +- 0.024), correct logic.
* Fortress mode: before turn 800 the general only attacks nearby enemy cells with a half split.
* Mixed-strategy deathtouch (idea from the overnight review): when every attacker next to their
  general can be countered, pick the attacker at random; when every defensive move loses to some reply,
  play the one with the fewest losing replies. Seeded from the map, so games stay reproducible.
* Safety: act() now counts swallowed exceptions (ERRORS); fuzz and tactics tests fail if it rises on
  normal input (a missing import once made every move a pass and the old fuzz test still passed).
Result vs v10 (paired, 180 pairs, 9 opponent types): +0.058 +- 0.055 (0.850 vs 0.792 pts/game).

## More things measured and rejected (3 Oct 00:30 to 02:50)
* Castle building with priority over strike gathering: -0.27 (from turn 300), -0.05 (from 450).
* Not marching under-strength on a known general (abandon + cooldown): -0.01 +- 0.05.
* Keep army once the enemy has seen our general (0.3 x their free army): +0.017 +- 0.070, no gain.
* Home castle (a castle on a cell touching the general as a defensive reserve), 4 variants: -0.04 to -0.10.
* Mirror statistics (harness/mirror_stats.py, 90 games): the first side to launch a real strike on a
  known general wins about 2/3; only 35% of first marches win within 45 turns; winner's timeline is
  found t207, +42 gathering, +43 marching. Finding the general first is only weakly predictive.
Lesson: in this ruleset every army or move spent on anything but the next strike loses tempo.

## Official evaluator check (3 Oct ~03:25 IST, v11 as submission)
evaluate.py tournament with the submission, starter, hunter and rusher in Docker (150 ms, real pause
and forfeit rules): 30 games, 0 forfeits, our slowest response 23.8 ms (first call 91 to 137 ms).
Won the league (5/6), semifinal 4-0, final 5-1. All 8 official games against rusher reproduce
turn for turn in harness/runner.py, so local testing matches the official environment exactly.

## v12 (3 Oct ~03:45 IST)
From the official loss to rusher (seed 3506931667): a 29-stack was seen 12 cells out, then walked
through a gap in our vision while its old cell stayed visible, so the bot forgot it, stopped gathering,
and saw it again 6 cells out. Fixes: "ghost" stacks (a big stack that vanishes next to fog is assumed to
keep approaching at one cell per turn for 10 turns), and a garrison factor of 1.0 for 60 turns after an
enemy stack has stood next to our general. Wins that seed. vs v11 on the strong pool: +0.042 +- 0.069
(192 pairs, fewer losses); rush pool 128-0 like v11.
Rejected: strike gathers leaving cells within 2 to 4 of our general undrained (-0.07 to -0.14).

## v13 (3 Oct ~04:10 IST)
Bug: after turn 800 the "leave now to arrive by turn 800" shortcut stayed on, so every post-800 strike
marched at once with whatever was on the launch cell (often 1 to 10 army) while 700 was available.
Fix: the shortcut only applies before 800; after 800 a strike gathers at least 0.3 x our army.
Long-game matchups: +0.016 to +0.023 (few games reach 800). Pre-800 behaviour unchanged.

## League 2 (18 bots, 2 rounds, 612 games, v12 as KashyapBot)
Top six within noise: old_v9 53.0, old_v11 52.5, KashyapBot 51.0, hyb_rushboom 51.0, hyb_greedy 50.5,
old_v10 50.0 (of 68). KashyapBot 4-0 against every independent design (rusher, hunter, bigrush90/130,
kingstack, turtle, turtle-sniper, sniper, old_v8). The family of our own versions sits on a plateau.
Pure defenders that never spend their general (fatgen, fatgen2): 47 W, 1 D, 0 L, mostly by turn 400.

## v14 (3 Oct ~04:25 IST) = submission
Held-out seed check of v13 vs v12: -0.003 +- 0.005 (288 pairs, identical play before turn 800).
Held-out losses read (rusher, hunter): a stack of ours 3 to 4 cells from home was sent chasing an
enemy stack from behind ("counter") instead of walking home. Fix: if the fast gather is short, the
biggest stack that can reach the general before the threat walks home; counter-attacks only when the
stack can hit the enemy stack this turn. vs v13: +0.005 +- 0.022 (192 pairs, 6 games changed).
Found while testing: a new parameter was referenced but not defined, so the bot threw and passed on
those turns. New static test harness/tests/test_params.py (every PARAMS key used is defined, DEBUG off);
all archived versions and the submission pass it.
Overnight tuner restarted on v14 with stricter promotion (confirmation on 16 fresh seeds must be
>= +0.025 on its own).

## Loss mining v14 (3 Oct ~04:40 IST)
v14 vs independent bots (rusher, hunter, bigrush90/130/200, kingstack, sniper, turtle-sniper, fatgen2),
24 seeds x 2 slots each: 424 W, 1 D, 7 L (0.983 pts/game, 0 forfeits). Losses: sniper 4 (our own code
family), hunter 1, bigrush90 1, kingstack 1. The hunter and bigrush losses are the known pattern (a 40 to
60 stack meets a general of 8 to 21 while our larger total army is spread out). The kingstack loss was an
outlier where it out-built us (18 castles vs 5 by turn 750).
Rejected: castle priority whenever the enemy has more castles ("parity priority"): -0.086 +- 0.047
(216 pairs); it triggers against every castle-building opponent and costs tempo.

## v15 (3 Oct ~05:35 IST) = submission
"Assume a thin enemy general": the estimate of an unseen enemy general's army grows 0.1 per turn
instead of 0.5 (Claude-style bots, like ours, spend their general's army, so the old estimate made our
strikes wait too long). Evidence on three independent seed sets, all positive:
  batch 1 (EG 0.2): +0.031 +- 0.058; batch 2: EG 0.1 +0.085 +- 0.051, 0.2 +0.058, 0.3 +0.077;
  held-out seeds: EG 0.1 +0.008 +- 0.033, EG 0.0 +0.029 +- 0.044. Pooled about +0.04.
  No harm against fat-general bots (pass_bot, fatgen, fatgen2, turtle): 119 W 1 D 0 L, wins ~40 turns sooner.
Other ideas tested on v14/v15 and rejected: early snipe when few candidates remain (rarely triggers),
counterpunch after killing a big stack (-0.012), strike margin 1.0/extra 0 (-0.016), reinforcement
allowance 0.3 (-0.034), HUNT_MIN 60 (-0.034), castle-parity priority (-0.086), inference slack 3
(-0.019).
Inference audit: one game in about 170 dropped the true general from the candidate set mid-game (rare
same-turn ownership flips can tighten the land bounds by one). Self-recovering (remaining candidates get
scouted away, then every unseen cell is searched). 800 map-sides confirmed the turn-0 candidate set
always contains the true general; 165 later games had zero inference failures.
Official evaluator, 8-entrant tournament with the submission (in progress): 21-0, 0 forfeits.
Official 8-entrant tournament (v14 as submission at the time): champion, 24 W 0 D 0 L, final 6-0,
74 games with 0 forfeits. One response of 105.9 ms (p99.9 19.8 ms) came from host load (my parallel
batches); the same turn takes 0.42 ms when replayed in isolation.
Rejected on held-out seeds: HUNT_MIN 25 (-0.042 +- 0.053), HUNT_MIN 30 (-0.044 +- 0.050) after +0.056 on
a first batch.
Final held-out comparison (40 fresh seeds, 15 opponents): v15 vs v14 +0.018 +- 0.035, draws 6 vs 15.

## Tuner run on v15 (06:16 to 08:02 IST) and final decision
Strict tuner (promotion needs a positive search batch and a >= +0.025 confirmation on 16 fresh seeds)
promoted two change sets: gen 2 (OPEN_STACK 10, THREAT_R 10, DEF_MARGIN 4, RUN_OPEN_MIN 10; confirm
+0.074 +- 0.075) and gen 5 (GARRISON_F 0, SCOUT_W 1.1, STACK_MIN 31; confirm +0.125 +- 0.076). Several other
generations showed +0.10 to +0.16 search gains that confirmed at -0.05 to 0.00.
Independent held-out check of the tuner champion vs v15 (40 unused held-out seeds, 14 opponents,
336 pairs): -0.022 +- 0.052, more losses (71 vs 60). Rejected. Even double-confirmed tuner results were
noise; v15 stays the submission.
Final safety suite on the submission file (= v15): params 88/88 defined, DEBUG off, official validate,
isolated import, tactics 100/100, fuzz 1629 calls 0 invalid, simulator 3272 cases 0 mismatches,
inference 0 failures.

## v16 candidate (3 Oct ~09:35 IST)
Final official run with v15 (idle machine, 8 entrants incl. our v12 and fatgen2): champion, 20 W 2 D 2 L,
final 3.5-2.5 vs rival_v12, 0 forfeits, max response 25.1 ms, p99.9 12.3 ms.
One loss (turn 881 vs v12) showed a deathtouch-phase defense flaw: a 392-stack closed in on one
neighbour of our general (235 army) while our 505-stack sat two cells away on the other side; the moat
refill moved deepest cells first, and the threat was counted against every neighbour, so one big stack
shuttled between two moat cells. v16: each enemy stack threatens only the neighbour(s) nearest to it,
and a stack that is actually closing in triggers a time-limited, biggest-first refill.
Wins that game. vs v15: late-game pool +0.005 +- 0.010 (192 pairs); held-out seeds -0.003 +- 0.008
(288 pairs, 1 game differs). Safety suite passes.
