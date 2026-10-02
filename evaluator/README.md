# Code Bot evaluator

Organizer-run evaluation for **Code Bot, 2 October 2026**, organized by **Fuzzy Dynamics** and presented by **Animish Sharma**. Kickoff is **2 October 2026 at 6:00 PM IST in H 205**; submission closes **3 October 2026 at 2:00 PM IST**. Participants build for 20 hours, submit **one Python file**, and then compete for **US$500 / US$300 / US$200**.

The kit includes the pinned Generals competition engine, a Docker sandbox, a starter bot, a match runner, a round-robin tournament with playoffs, and tests. It runs locally; it is **not a submission website**. Collect files through your chosen channel, record the deadline receipts, and place accepted entries in a directory.

## Participant contract

- Submit `participant_id.py`: UTF-8, at most **1 MiB**, containing a top-level `def act(observation)`.
- Use **Python 3.12 and the standard library only**. No packages, separate assets, binaries, model files, network services or installation steps.
- Put participant ID, bot name, short strategy, attribution and AI assistance in a header comment/docstring.
- Return `[kind, row, col, direction, split]`: five signed 32-bit integers. Do not return booleans or floats.
- Globals persist during a game. Each new game starts a fresh container and module.
- Calls get **150 ms wall time**, with **10 seconds for the first call including import**. Container startup and engine compilation are excluded; observation transport is included.
- Each bot gets **2 GiB memory**, 16 MiB temporary storage and a maximum of 32 processes/threads. Both bots use the **same selected logical CPU**, take turns, and are paused between decisions. No GPU or network access.
- Timeout, crash, exception, malformed return or invalid action code causes an **immediate game forfeit**. A correctly formatted action that is illegal on the board is a pass. The public platform's 50-fault policy does not apply to this event.

Minimal entry:

```python
"""Participant: alice | Bot: Example | Sources: none | AI: none"""

def act(observation):
    return [1, 0, 0, 0, 0]
```

Use [examples/starter.py](examples/starter.py) for a simple expanding bot, or [examples/pass_bot.py](examples/pass_bot.py) for a protocol baseline. The starter is intentionally basic, not a competitive strategy guarantee.

### Observation and action API

| Key | Meaning |
|---|---|
| `turn`, `height`, `width` | Engine turn and exact board dimensions |
| `player_id` | Starting slot, 0 or 1 |
| `my_land`, `my_army`, `opp_land`, `opp_army` | Engine-provided totals |
| `type` | Grid: 0 fog, 1 plain, 2 mountain, 3 castle, 4 general, 5 structure in fog |
| `owner` | Grid: 0 neutral/unknown, 1 you, 2 opponent, regardless of starting slot |
| `army` | Grid of observed armies, with hidden cells masked by the engine |

All grids are ordinary lists of rows. Coordinates are zero-based. Actions:

| Field | Values |
|---|---|
| `kind` | 0 move; 1 pass; 2 build castle |
| `row`, `col` | Source tile for move, target tile for build |
| `direction` | 0 up; 1 down; 2 left; 3 right |
| `split` | 0 all but one; 1 half, rounded down |

Use valid direction and split codes even when ignored for pass/build. The engine applies legality, combat, fog, castle costs, movement priority and deathtouch. Both observations are computed from the same pre-turn state. Prints become diagnostic output and do not count as actions.

## Install once on the organizer machine

Supported evaluator host: **Linux**, Python **3.12 or later**, and a running local Docker daemon accessible to your user through a Unix socket. The sandbox always runs Python 3.12, independent of the host version. Docker Desktop/remote daemons and non-Linux hosts are not supported by this runner.

From the project root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r evaluator/requirements.txt
.venv/bin/python evaluator/evaluate.py build
.venv/bin/python evaluator/evaluate.py doctor
```

Setup downloads the Python image and host dependencies. **Evaluation itself requires no internet**, does not pull images and does not install bot dependencies. The Docker base image is pinned by digest; the engine is vendored, so a checkout of the live upstream branch is unnecessary.

The image tag is `codebot-python:1`. The runner resolves it to an immutable image ID at the beginning of a run and records that ID. The dependency lock includes the engine's numerical stack. The bot image exposes only Python's standard library.

To prepare a separate disconnected machine of the same architecture, export the image and download dependency wheels during setup:

```bash
docker save codebot-python:1 -o codebot-image.tar
.venv/bin/pip download -r evaluator/requirements.txt -d wheelhouse
# On the offline machine, with a matching Python version and architecture:
docker load -i codebot-image.tar
python3 -m venv .venv
.venv/bin/pip install --no-index --find-links=wheelhouse -r evaluator/requirements.txt
```

## Check and practice

Static validation reads and parses a file without importing or executing it on the host:

```bash
.venv/bin/python evaluator/evaluate.py validate evaluator/examples/starter.py
.venv/bin/python evaluator/evaluate.py match \
  evaluator/examples/starter.py evaluator/examples/pass_bot.py \
  --seed 42 --out runs/practice-01
```

Use a new output directory each time; existing results are never overwritten. Filenames become participant IDs, so use unique names with letters, digits, underscores or hyphens. To play two copies of one bot, give the copies different filenames.

For a quick smoke test only:

```bash
.venv/bin/python evaluator/evaluate.py match \
  evaluator/examples/starter.py evaluator/examples/pass_bot.py \
  --seed 42 --max-turns 8 --out runs/smoke-01
```

`--max-turns` and `--move-ms` are practice overrides. Official settings are **1200 turns and 150 ms**; the manifest records whether these limits are in use. Do not use shortened games for awards. Test a full game, both starting slots and several maps before the deadline.

## Run the tournament

1. Announce the final rulebook, image/kit version, start and deadline with timezone, collection link and support/dispute channel. The uploaded files need no ZIP or companion README.
2. After H20, put the latest accepted on-time files into `submissions/`. Validate them and run practice intake games before determining the eligible field. Keep original receipt timestamps separately; this CLI does not enforce the upload deadline.
3. Publish the final tiebreak seed and participant IDs before official results. The default tiebreak seed is `CODE-BOT-2026-10-02`.
4. Run on an otherwise idle event host, with one evaluator at a time on its selected CPU. Reserve additional host capacity for Docker and the game engine; single-core restrictions apply to the submitted bots, not every organizer process.

```bash
.venv/bin/python evaluator/evaluate.py validate submissions/*.py
.venv/bin/python evaluator/evaluate.py tournament submissions \
  --cpu 0 --draw-seed CODE-BOT-2026-10-02 --out runs/official
```

Choose an available CPU from `doctor`; omit `--cpu` to use the first CPU available to the evaluator. Do not change settings, rebuild images or edit frozen submissions mid-event. The runner snapshots every source file read-only, checks its hash before each game, and freezes the image ID. Bot containers cannot access another entry, the engine, the Docker socket or organizer logs.

### Scoring and bracket

- League: each unordered pairing plays two fresh random maps, exchanging starting slots. Win 1, draw 0.5, loss 0. Double forfeit: 0 each.
- League ties: points within the entire tied set, then total league wins, then ascending SHA-256 of UTF-8 `draw_seed:participant_id` (ID breaks a hypothetical hash collision). No recursive mini-league recalculation.
- Four or more entrants: seeds 1–4 and 2–3 play four-game semifinals; losers play four games for third place; winners play a six-game final.
- Each tied playoff receives one extra two-game pair. If still tied, higher league seed wins that series, including the final or third-place playoff.
- Three entrants: league top two play the final; remaining entrant is third. Two entrants: final after the league, with no third-place award. Fewer than two entries are rejected.

The league takes `N × (N−1)` games. With 16 entrants, budget for 240 league games, 18 scheduled playoff games and up to eight playoff tiebreak games. Measure host performance before announcing tournament duration. Run games sequentially to maintain the published CPU policy.

## Results and replay evidence

Each run contains:

| File | Contents |
|---|---|
| `manifest.json` | Engine commit/tree hash, image ID, CPU, limits, file hashes and run time |
| `submissions/` | Frozen `.py` files actually evaluated |
| `game_XXXX/metadata.json` | Pairing, stage and private map seed |
| `game_XXXX/replay.jsonl` | Initial full board, every action, response timing, state and faults |
| `game_XXXX/bot_0.stderr.log`, `bot_1.stderr.log` | Bounded diagnostics (first 64 KiB; excess drained) |
| `game_XXXX/result.json`, `games.json` | Completed game outcomes |
| `standings.json`, `standings.csv` | League standings, updated after every game |
| `bracket.json`, `podium.json` | Playoffs and prize placements |
| `completed.json` | Successful completion marker |
| `ABORTED.json` | Interrupted/infrastructure-failed run; never treat it as a completed event |

Replays and seeds reveal hidden information. Keep run directories private while play is in progress. The JSONL replay is an audit record; this kit does not include a graphical replay viewer.

Bot faults award forfeits; engine errors or Docker control failures abort the run without inventing a match result. Completed game files survive. There is **no automatic resume or referee override UI**. Preserve an aborted directory, resolve the issue and adjudicate before continuing. A disputed game can be reproduced in a new directory using the frozen files, recorded seed and original starting order with the `match` command. Do not restart a partially completed tournament and silently replace valid results. Integrity disqualifications and appeal corrections are human referee decisions; they must be recorded and affected advancement paused.

The runner's `finally` cleanup removes its containers, including paused processes. After a host crash or a force-kill, inspect only this kit's labeled leftovers:

```bash
docker ps -a --filter label=codebot=true
# Remove only the specific Code Bot container IDs shown above:
docker rm -f CONTAINER_ID
```

Run submitted code on a dedicated event machine/VM. Docker provides the isolation used here; it shares the host kernel and is not a claim of protection against every kernel vulnerability. The standard-library rule is an eligibility rule, not static proof of intent: organizers can inspect source when an integrity concern arises.

## Tests and provenance

```bash
.venv/bin/pip install pytest
.venv/bin/pytest -q evaluator/tests
```

Integration tests require the built Docker image; they explicitly skip if it is absent. They exercise real offline containers, CPU affinity, read-only files, persistent state, memory settings, timeouts, crashes, missing dependencies and bounded protocol output. Unit tests cover validation, immutable file copies, game legality, fog, scoring and series tiebreaks.

The unchanged game engine is vendored from [`strakam/generals-bots` at `13db8f69a422380ea184d2f4ca262a38866c5fc6`](https://github.com/strakam/generals-bots/tree/13db8f69a422380ea184d2f4ca262a38866c5fc6), under its included [MIT license](vendor/generals-bots/LICENSE). Non-runtime upstream examples, paper material, demo GIFs and GitHub workflows are omitted. This historical version retains the competition mode and its documented chasing/reinforcing/smaller-army move order; the current upstream branch has changed since then.

Game references: [competition mechanics](https://www.generals.bot/rules), [platform interface](https://www.generals.bot/docs). This event deliberately substitutes the single-file `act()` API, standard-library environment and immediate runtime forfeits for the website's submission wrapper and fault budget.

The editable participant materials are in `../deliverables/`. Their generator is `../scripts/build_materials.py`; install `python-pptx` and `python-docx` to regenerate, then use LibreOffice to export PDFs. Edit remaining tournament-time, submission-link and contact placeholders before announcing the event.
