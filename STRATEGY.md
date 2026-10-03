# KashyapBot: how it plays

One Python file (`Athmeeya_M_Kashyap_9353211491.py`), standard library only, entry point `act(observation)`.
About 1 to 4 ms per turn (limit 150 ms).

## 1. The core idea: tempo wins
Only a general capture scores more than a draw. Measured over thousands of self-play and test games,
the side that lands the first successful strike on the enemy general usually wins, and every attempt
to "play safe" (holding army at home, building castles early, reserving cells for defense) lost points.
So the bot is built to find the enemy general fast and strike as soon as a strike is affordable, while
defending only against threats it can actually see or track.

## 2. Finding the enemy general (inference from legal information)
* **Turn 0 terrain**: all mountains are visible from the start, so the bot computes walking distances
  between every pair of cells.
* **Spawn rule**: the map generator places the second general at least 17 walking steps from the first,
  with a similar amount of open ground within 7 steps. This narrows about 300 cells to about 25
  candidates (verified on 800 map-sides: the true general was always included).
* **Land evidence**: an enemy cell seen at turn t must be reachable from their general within t-2 moves
  and within their land count, and their unseen land must connect their general to the cells we see.
* **Castle leaks**: every castle shows through fog. From `opp_army` changes we decode the price they
  paid for a new castle; the price depends on the distance to their general, which pins it down further.
* Remaining candidates are ranked by a formula measured offline against the true answer (distance to
  their land, distance to the far end of their land, and evidence that a cell's surroundings are not theirs).

## 3. Economy
* Opening: the general sends small "runs" of army that claim neutral land for free (claiming costs no
  army in this ruleset). Land bonus army (+1 per cell every 50 turns) claims more land at the frontier.
* Castles mostly after turn 500 (measured: earlier castles cost strikes). Exception: if the enemy has
  more castles than us, we may build to keep parity.

## 4. Offense
* Hunting from about turn 120: a gathered stack walks toward the most likely candidate, revealing cells.
* Strike: once the general is known, gather a stack big enough for its estimated army (assumed to grow
  slowly, since most bots spend their general's army), march along a path that minimises time spent in
  the enemy's vision, and capture.
* From turn 800 (deathtouch: any move onto their general wins), the bot stages a stack nearby and
  touches; an exact simulator of the engine's move order decides between touching and countering.

## 5. Defense
* Every visible enemy stack near home is assessed by arrival time; stacks that can arrive together are
  summed. Responses: kill it if a neighbour can, pull army home with a "best army within k moves"
  gather, walk a nearby stack home, or hit the stack with ours.
* Stacks that walk into the fog are remembered as "ghosts" still approaching.
* After turn 740 a moat: every neighbour of our general holds at least as much as the largest enemy stack
  that could reach it. Deathtouch defense uses a third tile (attacking with the general itself fails).
* An exact 2-ply search (our move against every enemy reply, using the engine's real move order) checks
  every move near both generals and overrides the plan if it would lose.

## 6. How it was built and tested
* Local runner that reproduces the official Docker evaluator game for game, parallel paired-seed
  batches, held-out seeds for final checks, a local 18-bot league in the official format, and tests:
  simulator vs engine (6,606 cases, 0 mismatches), inference correctness, fuzzing with corrupted
  inputs, deathtouch scenarios, and a static check that every parameter is defined.
* Official evaluator runs: 30-game and 74-game tournaments, 0 forfeits, champion both times.
* Development with Anthropic Claude (Claude Code) under the participant's direction (disclosed in the file header).
