# CLAUDE.md: FYDY Code Bot (generals.bot competition ruleset)

You are helping Athmeeya M Kashyap build ONE competition bot for the FYDY "Code Bot" hackathon.
This file is the single source of truth for the project. Read all of it before writing code.

Participant ID: `Athmeeya_M_Kashyap_9353211491`
Submission file name: `Athmeeya_M_Kashyap_9353211491.py`

## 0. How you must work

1. **Never assume. Ask.** If a rule, a mechanic, the environment or the user's intent is unclear, stop and ask Athmeeya before building on a guess. The only exception is a fact you can settle yourself by reading the engine source in `evaluator/vendor/generals-bots/` or by running a small experiment against it. Prefer the experiment, and report what you verified.
2. **The engine source is authoritative.** Section 3 below was verified against the pinned engine (commit `13db8f69a422380ea184d2f4ca262a38866c5fc6`), with file and function names cited. If anything you observe contradicts this file, trust the engine, tell the user, and update this file.
3. **No overfitting to the evaluator.** The official tournament uses fresh random maps with private seeds. Never tune constants against a fixed list of seeds, never special-case map sizes or coordinates, never script openings for particular boards. Every decision must be computed from the observation and the bot's own memory. Use fresh random seeds for every evaluation batch and keep a held-out batch for final checks (Section 8).
4. **Always keep a working submission.** Before any risky change, copy the current best bot to `bots/archive/vN.py`. `submission/Athmeeya_M_Kashyap_9353211491.py` must always be a file that has passed the full safety suite.
5. **Measure every change.** A change is promoted only if it wins a statistically meaningful paired test (Section 8.4). Win rates over 20 games are noise.
6. **Explain as you go.** Athmeeya must be able to explain the strategy to judges. Keep a running `NOTES.md` with what each version changed and the measured result. Write clear comments in the bot.
7. **No em dashes or en dashes** in any file or message you write for the user. Use commas, colons or plain hyphens.

## 1. Event facts and hard constraints

Source: `docs/Code_Bot_Rules.pdf` v2.0, `docs/Code_Bot_Slides.pdf`, `evaluator/README.md`, `evaluator/sandbox.py`, `evaluator/worker.py`.

| Item | Value |
|---|---|
| Format | 1v1 games. Individual entry. One Python file per person. |
| Build window | 2 Oct 2026 18:00 IST to 3 Oct 2026 14:00 IST (hard deadline, late may be ignored) |
| Language | CPython 3.12, **standard library only**. No numpy, no third-party packages, no model files, no downloads, no network. |
| File | One UTF-8 `.py`, at most 1 MiB (1,048,576 bytes). Must contain a top-level `def act(observation)`. |
| Header | Top-level comment or docstring with registered ID, bot name, short strategy explanation, reused sources with attribution, and material AI assistance (Claude / Claude Code). No credentials. |
| Decision time | **150 ms wall clock per call**, measured from writing the observation JSON to reading the reply. It includes JSON transport and parsing inside the adapter. **The first call gets 10 s, including import.** |
| CPU | One logical CPU, shared with the opponent's container. The inactive bot is paused (docker pause) between turns. |
| Memory | 2 GiB, 16 MiB temp storage, at most 32 processes/threads. |
| Lifecycle | Fresh process per game. The module is imported on the first call, and module globals persist for the rest of that game only. |
| Fatal (immediate forfeit = loss) | Timeout, any exception escaping `act`, crash, malformed return, invalid action code, reply over 2048 bytes. There is no fault allowance. |
| Non-fatal | A well-formed action that is illegal on the board is treated as a pass. |
| Output | `print` goes to stderr (bounded log, first 64 KiB kept). Never print per turn in the submitted file. |
| Fair play | No reading other files, no hidden-state access, no human control, no network. AI help is allowed but must be disclosed in the header. No sharing strategy code with other participants. |

### 1.1 Exact return format (`evaluator/sandbox.py: validate_action`)

`act` returns a `list` or `tuple` of exactly 5 Python `int` values (not `bool`, not `float`), each a signed 32-bit integer:

`[kind, row, col, direction, split]`

* `kind`: 0 move, 1 pass, 2 build castle
* `row, col`: zero-based. Source cell for a move, target cell for a build.
* `direction`: 0 up (row-1), 1 down (row+1), 2 left (col-1), 3 right (col+1). **Must be 0..3 even for pass and build.**
* `split`: 0 moves all but one, 1 moves half (floor). **Must be 0 or 1 even for pass and build.**

Safe pass: `[1, 0, 0, 0, 0]`.

### 1.2 Observation dict (`evaluator/engine.py: observation`)

A fresh plain dict every call:

| Key | Meaning |
|---|---|
| `turn` | Engine time = number of steps already executed. The first call is turn 0. |
| `height`, `width` | Board size, each independently 18..21. |
| `player_id` | Starting slot, 0 or 1. Ownership codes below are relative to you regardless of slot. |
| `my_land`, `my_army` | Your exact totals. |
| `opp_land`, `opp_army` | **Opponent's exact totals, every turn, even under fog.** |
| `type` | H x W list of lists: 0 fog, 1 plain (visible), 2 mountain (visible), 3 castle (visible), 4 general (visible), 5 mountain-or-castle in fog |
| `owner` | H x W: 0 neutral or unknown, 1 you, 2 opponent. Fog cells are always 0. |
| `army` | H x W: army on visible cells. Fog cells are always 0. |

How the type grid is built (`competition/protocol.py: encode_observation`): start as 1 (plain), then fog cells become 0, structures in fog become 5, visible mountains 2, visible castles 3, visible generals 4. Consequences:
* An enemy general in fog shows as **0** (generals are not "structures").
* Enemy-owned land in fog shows as type 0 with owner 0. You cannot tell fog land from fog neutral.
* Every mountain on the map is visible as 5 (or 2) **from turn 0**, and at turn 0 there are no castles anywhere. **So the full static terrain is known at turn 0.**

## 2. Tournament scoring and what it implies

* League: full round robin. Each pair plays 2 games on fresh maps with swapped starting slots. Win 1, draw 0.5, loss 0. A forfeit gives the opponent 1. Top 4 go to semifinals (1v4, 2v3, 4 games each), then the final (6 games) and third place (4 games). Tied series get one extra 2-game pair, then the higher league seed wins.
* League ties: head-to-head points within the tied set, then total wins, then a seeded hash draw.
* **A game not decided by a general capture is a draw at turn 1200. Territory and army never break ties.** A mutual capture on the same turn is also a draw.
* Implication: only captures score above 0.5. Economy, land and army matter only as means to capture and to avoid being captured. The objective per game is maximizing P(win) minus P(loss). Total wins is the second league tiebreak, so prefer converting draws into wins.
* Implication: robustness is worth more than cleverness. One forfeit costs a full point.

## 3. Game mechanics, verified against the engine

Files: `generals/core/game.py`, `generals/modifiers/build_castles.py`, `generals/modifiers/deathtouch.py`, `generals/core/grid.py`, `generals/core/env.py` (preset `"competition"`), `competition/matchup.py: make_board, make_transition`.

### 3.1 Map generation (`grid.py: generate_grid`, `matchup.py: make_board`)
* Height and width are each drawn uniformly from 18..21, independently, so boards are often rectangular.
* Mountains: between floor(0.24 x H x W) and floor(0.26 x H x W) cells.
* 9 to 11 castles are carved out of mountains, then **stripped to plain ground** (build-castles mode). So the game starts with **zero castles** and those cells are ordinary open land.
* General A is placed on open ground. General B is drawn among cells whose **walking (BFS) distance from A is at least 17** and whose "room" (number of cells reachable within 7 steps, excluding the cell itself) differs from A's room by **at most 5**. Fallbacks exist for rare boards, so never treat this as a hard guarantee. Which spot becomes slot 0 is random.
* Verified on 150 random maps: the true enemy general was inside that candidate set every time. The set had between 3 and 54 cells (median about 28), and the walking distance between generals ranged from 17 to 36.
* Mountains never change during the game. Castles (including the cells where they are built) are walkable.

### 3.2 Turn loop and growth (`game.py: step, global_update`)
Each step does the following in order:
1. **Builds resolve first** (`build_castles.apply_build_actions`). Build actions are then rewritten as passes.
2. Deathtouch and mutual-capture checks wrap the base step (`deathtouch.step`).
3. Moves execute one at a time in the move order of 3.5.
4. `time += 1`.
5. Growth based on the new time t: if t % 50 == 0, every owned cell gets +1. If t % 2 == 0, every owned general and castle gets +1. Both apply on turns that are multiples of 50.

Verified: the general starts at 1 army on turn 0, and with no moves it shows 2 on turn 2, 3 on turn 4, 25 on turn 49 and 27 on turn 50.

Income summary: each general or castle gives +1 every 2 turns (0.5 per turn). Each owned cell gives +1 every 50 turns (0.02 per turn).

### 3.3 Moves and combat (`game.py: _execute_move, _apply_move`)
* A move is valid iff the source is in bounds and owned by you, the destination is in bounds and not a mountain, and the moved amount is greater than 0.
* Amount: split=0 moves `a - 1`, split=1 moves `a // 2`, capped at `a - 1`. **The source needs at least 2 army.** At least 1 always stays behind.
* Destination owned by you: armies add.
* Destination neutral or enemy: if moved > defender, you take the cell with `moved - defender` army. Otherwise the defender keeps it with `defender - moved` army. **Equal strength leaves the defender owning the cell with 0 army.**
* Neutral cells always have 0 army (there are no neutral castles, and cells never revert to neutral). **Expanding into neutral land costs no army, only a move.** Your army total is unchanged by expansion.
* **Every combat between the two players destroys exactly min(moved, defender) from each side.** This symmetry is used for inference in 3.8.
* Capturing the enemy general: the tile becomes a castle you own with your surplus, all of the loser's land transfers to you with armies halved (rounded up), and the game ends with you as winner.

### 3.4 Visibility (`game.py: get_visibility, _observe`)
You see every cell you own plus its 8 neighbors (a 3x3 box, including diagonals). Everything else is fog, except that mountains and castles in fog are shown as type 5.

### 3.5 Move order within a turn (`game.py: _determine_move_order`)
Both players choose simultaneously from the same pre-turn state. Moves then resolve sequentially, each on the board left by the previous one. Priority, compared lexicographically:
1. **Chasing** first: your destination is the source cell of the other player's (non-pass) move.
2. **Reinforcing** next: your destination is a cell you owned at the start of the turn.
3. **Smaller source army** first.
4. Lower player index (slot 0) first.
5. Passes and builds (which became passes) come last.

Consequences: if you attack a cell the enemy is moving out of, you resolve first. Reinforcing moves beat plain attacks. Between two plain attacks, the smaller stack resolves first, so on a contested cell the bigger stack ends up holding it.

### 3.6 Building castles (`build_castles.py`)
* Action `[2, r, c, d, s]` where d is 0..3 and s is 0..1 (both ignored).
* Valid iff (r, c) is in bounds, owned by you, plain (not a general or castle), you are alive, and its army is at least the cost.
* **Cost = 35 + sum over YOUR structures (your general and every castle you own) of max(0, 14 - 2 x manhattan_distance).** The surcharge is 0 at Manhattan distance 7 or more. It uses Manhattan distance, not walking distance, so mountains do not matter. Enemy structures never affect your price. Examples: adjacent to your general costs 47, distance 2 costs 45, distance 7 or more from all your structures costs 35.
* The cost is deducted from that cell and the remainder stays, **possibly 0**, which is snipeable by 1 unit. An invalid build is silently a pass.
* A new castle grows from the same step (if the new time is even). Builds resolve before moves, so you cannot build with army that arrives this turn.
* A build next to the enemy general never counts as a deathtouch.
* Economics: a castle costing C pays itself back after 2C turns. A 35-cost castle built at turn 100 returns about 550 army by turn 1200.

### 3.7 Deathtouch and endgame (`deathtouch.py`)
* Active for any step where the engine time at the start of the step is at least 800. **That is every action you return when `observation["turn"] >= 800`.**
* A **valid move whose destination is the enemy general tile wins instantly**, whatever the army sizes. Valid means the source has at least 2 army at the moment that move resolves.
* Defense: a counter-move from a third tile onto the attacker's source cell is a chase, so it resolves first. If it captures the source outright, the touch never executes. If the source is left with 2 or more army and still owned by the attacker, the touch executes and the attacker wins. (Leaving the source with exactly 1 army, or 0 after a tie, also stops it, so the defender needs army(Y) >= army(X).)
* **Do not defend by moving the general onto the attacker's source.** That is a mutual chase: the smaller stack resolves first, and either the attacker touches first or the general's move is too small. Defend from a different neighbor of the attacker's cell.
* Both players touching on the same turn is a draw. A mutual capture on the same turn (army-based) is a draw at any turn.
* Before turn 800, capturing the general requires moving more army than it holds.
* The game is a draw after 1200 steps. The last action you can submit is on observation turn 1199.

### 3.8 Legal information leaks (all of these are just reading the supplied observation)
1. **Full terrain at turn 0.** Wall cells are those whose type is 2 or 5 at turn 0. Precompute all-pairs walking distances on the first call.
2. **Enemy general candidate set at turn 0**: passable cells with walking distance from your general of at least 17, and |room(cell) - room(your general)| at most 5. Each turn, remove candidates that are visible and not an enemy general. An enemy cell seen at turn t also bounds the general: walking distance(general, cell) <= t - 2.
3. **Enemy castles are visible through fog.** Any cell that shows type 5 but was not a wall at turn 0 is a castle that is not yours. So S_opp = 1 + number of castles on the map that are not mine.
4. **Enemy economy is decodable from `opp_army`.** Expansion never changes army totals, and combat destroys equal amounts from both sides. For the step that produced observation turn t:
   * Your own combat loss L = [t even] x S_me + [t % 50 == 0] x my_land - (my build cost this step, if your build succeeded) - (my_army(t) - my_army(t-1)), where S_me is your structure count after the step.
   * B_opp = [t even] x S_opp + [t % 50 == 0] x opp_land(t) - L - (opp_army(t) - opp_army(t-1)).
   * **The surcharge B_opp - 35 is a function of the Manhattan distances from the new castle to their existing structures, including their general.** Intersect with the candidate set.
5. `opp_land` and `opp_army` totals give exact enemy strength for attack and defense decisions.

## 4. Repository layout

```
CLAUDE.md, NOTES.md
evaluator/                    organizer kit, UNMODIFIED
docs/                         Code_Bot_Rules.pdf, Code_Bot_Slides.pdf
bots/current.py               bot under development
bots/archive/vN.py            frozen versions
bots/opponents/               test opponents
harness/runner.py             local match runner mimicking the official evaluator
harness/batch.py              parallel paired-seed batches, stats, timing
harness/view.py            ASCII replay viewer
harness/tests/                safety and inference tests
submission/Athmeeya_M_Kashyap_9353211491.py
```
Never edit anything inside `evaluator/`.

## 5 to 9. Architecture, strategy, performance, testing, timeline

See the original planning text kept in `NOTES.md` (Plan section). Key rules that stay binding:
* Safety wrapper around `act`, `_sanitize` to five valid ints, catch `Exception`, never threads/files/exit.
* Time guard: target about 60 ms compute, hard stop 90 ms; first call under 3 s.
* All thresholds in a `PARAMS` dict at the top of the bot.
* Promotion rule: at least 200 paired games vs the pool, CI excludes no improvement, zero forfeits, timing passes.
* Safety suite: static validate, isolated import, 100 full games with no faults and no turn over 120 ms, worst-case timing, fuzz, inference tests.
* Feature freeze 3 Oct 11:30 IST, submit by 13:15 IST, hard deadline 14:00 IST.

## 10. Submission file header template

```python
"""
Participant ID: Athmeeya_M_Kashyap_9353211491
Bot name: <ask Athmeeya>
Strategy: <3 to 6 lines>
Sources: FYDY Code Bot organizer starter and evaluator (reference only); engine rules
         from strakam/generals-bots @ 13db8f6 (MIT).
AI assistance: Developed with Anthropic Claude (Claude Code), which wrote code under
               the participant's direction; strategy, testing and final review by the participant.
Runtime: CPython 3.12, standard library only.
"""
```

## 11. Environment (verified 2 Oct)
* Linux, 16 cores, Python 3.12.3 at /usr/bin/python3.12, local Docker daemon available.
* Engine venv: `.venv/` (jax 0.11.2, numpy 2.5.3). Engine step plus observations about 3 ms per turn; first compile per board shape 4 to 7 s (cached in `.jax_cache/`).
