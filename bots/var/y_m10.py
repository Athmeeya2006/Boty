"""
Participant ID: Athmeeya_M_Kashyap_9353211491
Bot name: KashyapBot
Strategy: Tempo-first. Expand fast with general runs and land-bonus claims, find the enemy
          general by inference (spawn distance/room rules from turn-0 terrain, enemy land that
          must connect back to their general, castle cost leaks decoded from opp_army), then
          gather and strike as early as the strike is affordable. Defense reacts to visible and
          fog-tracked enemy stacks with fast k-move gathers. Castles mostly after turn 500.
          From turn 800 an exact 2-ply simulator of the engine's move order picks touches and
          third-tile counters (mixed strategy when both sides must guess).
Sources: FYDY Code Bot organizer starter and evaluator (reference only); game rules from
         strakam/generals-bots @ 13db8f6 (MIT). Mixed-strategy deathtouch idea from an overnight
         review of this project. No other code reused.
AI assistance: Developed with Anthropic Claude (Claude Code), which wrote code under the
               participant's direction; strategy, testing and final review by the participant.
Runtime: CPython 3.12, standard library only.
"""
import random
import time

DEBUG = False

# ---------------------------------------------------------------------------
# Tunable parameters (every threshold lives here)
# ---------------------------------------------------------------------------
PARAMS = {
    "BUDGET_S": 0.075,          # soft per-turn compute budget (seconds)
    "OPEN_STACK": 5,            # opening: general launches a run once it holds this much
    "OPEN_T": 70,               # opening ends: general then saves for castles
    "DEPLOY_WINDOW": 0,         # this close to a land bonus the general deploys what it has
    "DEPLOY_LAST_T": 160,       # ... during the first bonuses only
    "SCOUT_FROM_T": 50,         # scouting expansion starts after the first land bonus
    "SCOUT_EXPAND_T": 250,      # until this turn (and while their general is unknown) expansion scouts
    "SCOUT_W": 0.6,             # claim score per step closer to the candidate region
    "REVEAL_BONUS": 4.0,        # claim score per candidate cell uncovered
    "WALK_PEN": 0.6,            # score cost per step a run stack walks through our own land
    "RUN_STACK": 6,            # after the opening the general runs with this much (each half)
    "RUN_OPEN_MIN": 6,          # ... while at least this many open cells border our land
    "RUN_LAST_T": 600,          # no general expansion runs after this turn
    "CASTLE_HORIZON": 1000,     # castle income counted until this turn
    "CASTLE_MOVE_COST": 1.5,    # army-equivalent cost of one move spent walking to a site
    "CASTLE_MIN_SCORE": 150,     # minimum net value to start a castle plan
    "CASTLE_DEPTH": 9,          # search depth for castle sites from a stack
    "CASTLE_DANGER_R": 5,       # sites this close to known enemy land are penalised
    "HOME_CASTLE_N": 0,         # castles to build on cells touching our general (defensive reserve)
    "HOME_CASTLE_T": 150,       # ... from this turn
    "HOME_CASTLE_MODE": 0,      # 0: gather for it actively, 1: the general saves up for it
    "HOME_CASTLE_MAX_MOVES": 45,  # ... if the army can be gathered within this many moves
    "CASTLE_FIRST_T": 500,      # no castles before this turn (measured: earlier ones cost strikes)
    "CASTLE_PARITY": 1,         # ... except to match an enemy who has more castles than we do
    "CASTLE_PARITY_SLACK": 0,   # allowed castle deficit before parity building starts
    "CASTLE_LAST_T": 700,       # no new castles after this turn
    "CASTLE_FRONTIER_MAX": 9999,  # build castles only when at most this many open cells border us (off: measured worse)
    "CASTLE_ANYWAY_T": 350,     # ... or after this turn
    "MOAT_CASTLE_T": 250,       # from this turn castles on the general's neighbours are favoured
    "MOAT_CASTLE_BONUS": 120,   # score bonus for such a site
    "STACK_MIN": 30,            # a cell with this much army is a castle/strike source
    "GATHER_LAMBDA": 0.6,       # gather prune threshold (army per move)
    "THREAT_R": 14,             # enemy stacks within this walking distance are threats
    "THREAT_SUM_MIN": 12,       # ... counting only visible stacks at least this big
    "THREAT_SUM": 1,            # 1: enemy stacks that can arrive together are summed
    "KILL_R": 6,
    "INTERCEPT_R": 4,           # our stacks this close to an enemy stack may walk out to kill it
    "THREAT_MEM": 100,          # turns an enemy wave near home is remembered
    "GARRISON_F": 0.3,          # garrison target = this x biggest remembered wave
    "GARRISON_HIT_F": 1.0,      # garrison factor for a while after a stack reached our general
    "GARRISON_HIT_MEM": 60,     # ... for this many turns
    "WALK_HOME": 1,             # 1: a stack that can get home before a threat walks back
    "GHOST": 1,                 # 1: track enemy stacks that walk into fog as still approaching
    "GHOST_MIN": 10,            # ... stacks at least this big
    "GHOST_TTL": 10,            # ... for this many turns
    "GARRISON_FREE_F": 0.0,     # ... or this x the enemy's free army (opp_army - opp_land)
    "GARRISON_FREE_T": 100,     # from this turn
    "KEEP_FREE_F": 0.0,         # general never spends below this x enemy free army (passive)
    "FOUND_KEEP_F": 0.0,        # once the enemy has seen our general it keeps this x their free army
    "HOARD_T": 50,              # hoarder detection starts
    "HOARD_LAND_RATIO": 0.7,    # enemy land below this x ours = hoarding for a rush
    "HOARD_MIN_FREE": 15,       # ... with at least this much free army
    "HOARD_KEEP_F": 0.7,        # then the general keeps this x enemy free army
    "KEEP_T": 120,              # ... from this turn                # enemy stacks this close to home get attacked when beatable
    "DEF_MARGIN": 2,            # extra army wanted above a threat
    "STRIKE_MARGIN": 1.0,       # attack stack must exceed estimated need by this factor
    "STRIKE_EXTRA": 0,          # plus this flat amount
    "STRIKE_REINF": 0.6,        # fraction of visible army near their general assumed to reinforce
    "STRIKE_T": 650,            # after this turn, strike toward the general for turn 800
    "RAID_MIN": 10,             # stacks at least this big may raid enemy castles
    "RAID_R": 10,               # ... within this walking distance
    "RAID_MARGIN": 3,           # army to spare on arrival
    "RAID_PAD": 6,              # unknown leftover assumed on a castle never seen
    "STEALTH_COST": 1.5,        # path cost per cell the enemy can see (strike march)
    "ECON_FIRST": 0,            # 1: castle building runs before strike gathering
    "ECON_FIRST_T": 300,        # ... from this turn (before it, land and hunting come first)
    "STRIKE_ABANDON": 0,        # 1: do not march on a known general with less than the need
    "STRIKE_COOLDOWN": 40,      # turns to wait after abandoning an unaffordable strike
    "POST800_SHARE": 0.3,       # after turn 800 a strike gathers at least this share of our army
    "STAGE_D": 4,               # wait this far from their general until it is time to step in
    "SCOUT_T": 120,             # after this turn, actively hunt an unknown general
    "HUNT_T": 150,              # hunt earlier once enemy land has been seen
    "INF_SLACK": 1,             # safety margin (cells) on the land-based candidate bounds
    "EG_GROWTH": 0.1,           # assumed army growth per turn of an unseen enemy general
    "HUNT_LIK": 1.0,            # weight of candidate likelihood vs travel distance when hunting
    "HUNT_FILL": 0.0,           # a hunt gathers at least this x HUNT_MIN before marching
    "SNIPE_CANDS": 0,           # early snipe when at most this many general candidates remain (0: off)
    "SNIPE_T": 50,              # ... from this turn
    "SNIPE_MIN": 14,            # ... with a stack of at least this much
    "PUNCH_MIN": 0,             # counterpunch after killing an enemy stack this big near home (0: off)
    "PUNCH_WINDOW": 25,         # ... for this many turns
    "PUNCH_F": 0.6,             # ... strike requirement multiplied by this
    "HUNT_MIN": 40,             # minimum stack to send hunting
    "FORT_T": 740,              # fortress mode around our general starts
    "FORT_R": 3,                # enemy cells this close to our general get attacked
    "MOAT_MIN": 10,             # every neighbour of our general holds at least this late game
    "MOAT_R": 8,                # ... or the biggest enemy stack within this distance of it
    "TACT_R_ME": 2,             # tactical search radius around our general
    "TACT_R_EN": 2,             # tactical search radius around the enemy general
}

INF = 9999
PASS = [1, 0, 0, 0, 0]


# ---------------------------------------------------------------------------
# Safety wrapper: never raise, always return five valid ints
# ---------------------------------------------------------------------------
ERRORS = 0   # exceptions swallowed by the safety wrapper (tests assert this stays 0)


def act(observation):
    global ERRORS
    try:
        action = _decide(observation)
    except Exception:
        action = None
        ERRORS += 1
        if DEBUG:
            import traceback
            traceback.print_exc()
    return _sanitize(action, observation)


def _sanitize(action, observation):
    try:
        if action is None or not isinstance(action, (list, tuple)) or len(action) != 5:
            return [1, 0, 0, 0, 0]
        out = []
        for x in action:
            if isinstance(x, bool):
                return [1, 0, 0, 0, 0]
            out.append(int(x))
        kind, r, c, d, s = out
        if kind not in (0, 1, 2) or d not in (0, 1, 2, 3) or s not in (0, 1):
            return [1, 0, 0, 0, 0]
        h = int(observation["height"])
        w = int(observation["width"])
        if not (0 <= r < h and 0 <= c < w):
            return [1, 0, 0, 0, 0]
        return out
    except Exception:
        return [1, 0, 0, 0, 0]


def _log(*a):
    if DEBUG:
        import sys
        print(*a, file=sys.stderr)


# ---------------------------------------------------------------------------
# World state (module globals persist for one game)
# ---------------------------------------------------------------------------
class World:
    pass


S = None


def _decide(obs):
    global S
    t0 = time.perf_counter()
    turn = obs["turn"]
    h, w = obs["height"], obs["width"]
    if (S is None or not S.ready or turn == 0 or S.H != h or S.W != w or turn < S.t
            or obs["player_id"] != S.pid):
        S = World()
        S.ready = False
        _init(S, obs)
        S.ready = True
    S.t0 = t0
    S.deadline = t0 + PARAMS["BUDGET_S"]
    _update(S, obs)
    S.layer = "win"
    a = _choose(S)
    _after(S, a)
    if DEBUG:
        _log("T", turn, S.layer, a, "ms", round((time.perf_counter() - t0) * 1000, 1))
        if turn % 25 == 0:
            _log("C", turn, "cands", len(S.cands), "eg", S.eg is not None, "land", S.my_land, S.opp_land,
                 "army", S.my_army, S.opp_army, "castles", len(S.my_castles), len(S.en_castles))
    return a


def _time_left(S):
    return S.deadline - time.perf_counter()


# ---------------------------------------------------------------------------
# Map analysis (first call)
# ---------------------------------------------------------------------------
def _init(S, obs):
    H, W = obs["height"], obs["width"]
    S.H, S.W, S.N = H, W, H * W
    S.pid = obs["player_id"]
    S.t = obs["turn"]
    N = S.N
    typ = [v for row in obs["type"] for v in row]
    own = [v for row in obs["owner"] for v in row]
    # Static terrain: at turn 0 every 2/5 is a mountain. If we (re)initialise later,
    # castles also show as 5; treating them as walls is a safe approximation.
    wall = [x == 2 or x == 5 for x in typ]
    S.wall = wall
    S.passable = [i for i in range(N) if not wall[i]]
    adj = [[] for _ in range(N)]
    for i in S.passable:
        r, c = divmod(i, W)
        if r > 0 and not wall[i - W]:
            adj[i].append(i - W)
        if r < H - 1 and not wall[i + W]:
            adj[i].append(i + W)
        if c > 0 and not wall[i - 1]:
            adj[i].append(i - 1)
        if c < W - 1 and not wall[i + 1]:
            adj[i].append(i + 1)
    S.adj = adj
    S.rc = [divmod(i, W) for i in range(N)]
    # 8-neighbourhood for vision
    nb8 = [[] for _ in range(N)]
    for i in range(N):
        r, c = S.rc[i]
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                rr, cc = r + dr, c + dc
                if 0 <= rr < H and 0 <= cc < W:
                    nb8[i].append(rr * W + cc)
    S.nb8 = nb8
    # All-pairs walking distances
    dist = [None] * N
    for s in S.passable:
        d = [INF] * N
        d[s] = 0
        q = [s]
        for x in q:
            dx = d[x] + 1
            for y in adj[x]:
                if d[y] == INF:
                    d[y] = dx
                    q.append(y)
        dist[s] = d
    S.dist = dist
    S.room = [0] * N
    for s in S.passable:
        S.room[s] = sum(1 for v in dist[s] if 0 < v <= 7)

    S.myG = None
    for i in range(N):
        if typ[i] == 4 and own[i] == 1:
            S.myG = i
    if S.myG is None:
        for i in range(N):
            if own[i] == 1:
                S.myG = i
                break
    g = S.myG
    # Enemy general candidates (spawn rule: walk >= 17, room within 5)
    gd = dist[g]
    rg = S.room[g]
    c1 = [i for i in S.passable if i != g and 17 <= gd[i] < INF and abs(S.room[i] - rg) <= 5]
    if not c1:
        far = [i for i in S.passable if 17 <= gd[i] < INF]
        if far:
            best = min(abs(S.room[i] - rg) for i in far)
            c1 = [i for i in far if abs(S.room[i] - rg) == best]
    if not c1:
        reach = [i for i in S.passable if gd[i] < INF and i != g]
        mx = max(gd[i] for i in reach) if reach else 0
        c1 = [i for i in reach if gd[i] == mx]
    S.cands = set(c1)
    S.cand_fallback = False
    S.eg = None              # enemy general cell once known
    S.eg_army = 0
    S.eg_seen_t = -1
    # Memory of fogged cells
    S.mem_own = [0] * N
    S.mem_army = [0] * N
    S.mem_t = [-1] * N
    S.seen_ever = [False] * N
    S.enemy_seen_cells = {}  # cell -> last turn seen enemy-owned
    S.my_castles = set()
    S.en_castles = set()
    S.prev = None            # previous totals
    S.pending_build = None   # (cell, cost) we asked to build last turn
    S.plan = None
    S.cplan = None           # castle plan (separate track from strike plans)
    S.strike_cooldown = 0
    S.last_action = None
    S.target_cache = None
    S.surcharge_notes = []
    S.threat_hist = []
    S.castle_born = {}
    S.punch_t = -10 ** 6
    S.ghosts = []            # enemy stacks that walked into fog: [army, est. distance to our general, turn, cell]
    S.prev_stacks = {}       # visible enemy stacks last turn: cell -> army
    S.hit_t = -10 ** 6       # last turn an enemy stack stood next to our general
    # deterministic per map (reproducible games), used only for deathtouch guessing games
    S.rng = random.Random(hash((H, W, S.pid, tuple(typ))) & 0xFFFFFFFF)
    S.found_me = False
    S.found_me_t = -1
    S.sight = None
    S.lik_cache = None
    S.sight_t = -1
    S.taken_from_enemy = 0
    S.opp_builds = 0


# ---------------------------------------------------------------------------
# Per-turn world update
# ---------------------------------------------------------------------------
def _update(S, obs):
    t = obs["turn"]
    S.t = t
    N = S.N
    typ = [v for row in obs["type"] for v in row]
    own = [v for row in obs["owner"] for v in row]
    arm = [v for row in obs["army"] for v in row]
    S.typ, S.own, S.arm = typ, own, arm
    vis = [x != 0 and x != 5 for x in typ]
    S.vis = vis
    mine = []
    enemy = []
    for i in range(N):
        o = own[i]
        if o == 1:
            mine.append(i)
        elif o == 2:
            enemy.append(i)
    S.mine, S.enemy = mine, enemy
    mem_own, mem_army, mem_t, seen = S.mem_own, S.mem_army, S.mem_t, S.seen_ever
    mem_own_prev = list(mem_own)
    mem_army_prev = list(mem_army)
    for i in range(N):
        if vis[i]:
            mem_own[i] = own[i]
            mem_army[i] = arm[i]
            mem_t[i] = t
            seen[i] = True
    for i in mine:
        if mem_own_prev[i] == 2:
            S.taken_from_enemy += 1
    for i in enemy:
        S.enemy_seen_cells[i] = t
    # cells that we see are no longer enemy: drop them from the remembered set
    if S.enemy_seen_cells:
        for i in list(S.enemy_seen_cells):
            if vis[i] and own[i] != 2:
                del S.enemy_seen_cells[i]

    # Has the enemy seen our general? (they see the 3x3 around every cell they own)
    if not S.found_me:
        for j in S.nb8[S.myG]:
            if own[j] == 2:
                S.found_me = True
                S.found_me_t = t
                break
    # Long memory of enemy stack sizes seen near home (rushers come in waves)
    dg = S.dist[S.myG]
    for i in enemy:
        if arm[i] >= 5 and dg[i] <= PARAMS["THREAT_R"] + 2:
            S.threat_hist.append((t, arm[i]))
    if S.threat_hist and t - S.threat_hist[0][0] > PARAMS["THREAT_MEM"]:
        S.threat_hist = [x for x in S.threat_hist if t - x[0] <= PARAMS["THREAT_MEM"]]

    # Ghost stacks: a big enemy stack we saw last turn that is gone now, with fog next to where
    # it stood, has walked into the fog. Assume it keeps coming at one cell per turn.
    gmin = PARAMS["GHOST_MIN"]
    cur = {}
    for i in enemy:
        if arm[i] >= gmin and dg[i] <= PARAMS["THREAT_R"] + 6:
            cur[i] = arm[i]
    if PARAMS["GHOST"]:
        adj_ = S.adj
        for c, a in S.prev_stacks.items():
            if own[c] == 1:
                continue                     # we took the cell: the stack was destroyed
            if vis[c] and own[c] == 2 and arm[c] >= 0.7 * a:
                continue                     # still standing there
            moved = False
            fog = False
            for n in adj_[c]:
                if not vis[n]:
                    fog = True
                elif own[n] == 2 and arm[n] >= 0.6 * a:
                    moved = True             # we can see where it went
                elif own[n] == 1 and mem_own_prev[n] == 1 and arm[n] < mem_army_prev[n]:
                    moved = True             # it attacked one of our cells and died or shrank there
            if not vis[c]:
                continue                     # its cell went dark: the remembered-cell rule covers it
            if fog and not moved:
                S.ghosts.append([a, max(1, dg[c] - 1), t, c])
        if S.ghosts:
            keep = []
            for gh in S.ghosts:
                a, d, t0g, c = gh
                if t - t0g > PARAMS["GHOST_TTL"]:
                    continue
                # reappeared: a visible stack of similar size no farther than the ghost could be
                if any(av >= 0.6 * a and dg[i] <= d + 4 for i, av in cur.items()):
                    continue
                keep.append(gh)
            S.ghosts = keep
    S.prev_stacks = cur
    for j in S.adj[S.myG]:
        if own[j] == 2 and arm[j] >= 5:
            S.hit_t = t
    # Castles: every castle on the map shows as 3 (visible) or 5 (fog, non-wall)
    my_c = set()
    all_c = set()
    for i in range(N):
        ty = typ[i]
        if ty == 3:
            all_c.add(i)
            if own[i] == 1:
                my_c.add(i)
        elif ty == 5 and not S.wall[i]:
            all_c.add(i)
        elif ty == 4 and own[i] == 2:
            if S.eg is None:
                _log(t, "enemy general found at", S.rc[i])
            S.eg = i
    # an enemy general that we captured would be a castle now; ignore
    prev_en = S.en_castles
    en_c = all_c - my_c
    if S.eg is not None:
        en_c.discard(S.eg)
    new_en = en_c - prev_en
    for c in new_en:
        S.castle_born[c] = t
    S.my_castles, S.en_castles = my_c, en_c
    if S.eg is not None and vis[S.eg]:
        S.eg_army = arm[S.eg]
        S.eg_seen_t = t

    # Economy accounting (section 3.8.4)
    my_land, my_army = obs["my_land"], obs["my_army"]
    opp_land, opp_army = obs["opp_land"], obs["opp_army"]
    S.my_land, S.my_army, S.opp_land, S.opp_army = my_land, my_army, opp_land, opp_army
    S.S_me = 1 + len(my_c)
    S.S_opp = 1 + len(en_c)
    if S.prev is not None and S.prev[0] == t - 1:
        _, pml, pma, pol, poa, prev_my_c = S.prev
        even = 1 if t % 2 == 0 else 0
        bonus = 1 if t % 50 == 0 else 0
        my_cost = 0
        if S.pending_build is not None:
            cell, cost = S.pending_build
            if cell in my_c and cell not in prev_my_c:
                my_cost = cost
        L = even * S.S_me + bonus * my_land - my_cost - (my_army - pma)
        B = even * S.S_opp + bonus * opp_land - L - (opp_army - poa)
        # castles that changed hands make the books unreliable this turn
        swapped = (prev_my_c - my_c) or (my_c - prev_my_c - ({S.pending_build[0]} if S.pending_build else set()))
        if len(new_en) == 1 and not swapped and B >= 35:
            c = next(iter(new_en))
            S.opp_builds += 1
            _castle_leak(S, c, B - 35, prev_en)
    S.prev = (t, my_land, my_army, opp_land, opp_army, set(my_c))
    S.pending_build = None

    # Candidate filtering
    if S.eg is not None:
        S.cands = {S.eg}
    else:
        before = len(S.cands)
        cands = {c for c in S.cands if not vis[c]}
        if enemy:
            # a cell at walking distance d from their general needs a path of d owned
            # cells and at least d moves: d <= turn - 2 and d <= land - 1 (+ cells we took)
            dist = S.dist
            slack = PARAMS["INF_SLACK"]   # margin for rare same-turn ownership flips we miss
            lim = min(t - 2, opp_land - 1 + S.taken_from_enemy + slack)
            ok = {c for c in cands if all(dist[c][e] <= lim for e in enemy)}
            if ok:
                cands = ok
            # their hidden land must link the general to the cells we see: the hidden
            # part holds at least dist(general, visible enemy land) cells (minus ours taken)
            lim2 = opp_land - len(enemy) + S.taken_from_enemy + slack
            ok = {c for c in cands if min(dist[c][e] for e in enemy) <= lim2}
            if ok:
                cands = ok
        if not cands:
            # inconsistent (rare fallback map): every unseen passable cell
            cands = {i for i in S.passable if not S.seen_ever[i]}
            S.cand_fallback = True
            if not cands:
                cands = {i for i in S.passable if not vis[i]}
        S.cands = cands
        if len(cands) != before:
            S.target_cache = None


def _castle_leak(S, c, surcharge, prev_en):
    """Use the surcharge of a fresh enemy castle at c to pin their general."""
    W = S.W
    cr, cc = S.rc[c]
    known = 0
    for k in prev_en:
        kr, kc = S.rc[k]
        known += max(0, 14 - 2 * (abs(kr - cr) + abs(kc - cc)))
    gen = surcharge - known
    _log(S.t, "enemy castle at", S.rc[c], "surcharge", surcharge, "gen part", gen)
    if S.eg is not None or gen < 0 or gen > 14 or gen % 2:
        return
    if gen > 0:
        md = (14 - gen) // 2
        keep = {x for x in S.cands if abs(S.rc[x][0] - cr) + abs(S.rc[x][1] - cc) == md}
    else:
        keep = {x for x in S.cands if abs(S.rc[x][0] - cr) + abs(S.rc[x][1] - cc) >= 7}
    if keep:
        S.cands = keep
        S.target_cache = None
        _log(S.t, "candidates now", len(keep))


def _after(S, a):
    S.last_action = a
    if a is not None and a[0] == 2:
        cell = a[1] * S.W + a[2]
        S.pending_build = (cell, _build_cost(S, cell))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _dir(S, s, d):
    if d == s - S.W:
        return 0
    if d == s + S.W:
        return 1
    if d == s - 1:
        return 2
    return 3


def _mv(S, s, d, split=0):
    r, c = S.rc[s]
    return [0, r, c, _dir(S, s, d), split]


def _build_cost(S, p):
    pr, pc = S.rc[p]
    cost = 35
    structs = list(S.my_castles) + [S.myG]
    for k in structs:
        kr, kc = S.rc[k]
        md = abs(kr - pr) + abs(kc - pc)
        if md < 7:
            cost += 14 - 2 * md
    return cost


def _target(S):
    """Best guess of the enemy general cell."""
    if S.eg is not None:
        return S.eg
    if S.target_cache is not None and S.target_cache[0] == S.t // 10:
        return S.target_cache[1]
    cands = list(S.cands)
    if not cands:
        return None
    dist = S.dist
    seen = list(S.enemy_seen_cells)
    if seen:
        unl = _cand_unlikeliness(S)
        best = min(cands, key=lambda c: (unl[c], dist[S.myG][c]))
    else:
        sample = cands if len(cands) <= 60 else cands[:: len(cands) // 60]
        best = min(cands, key=lambda c: sum(dist[c][x] for x in sample))
    S.target_cache = (S.t // 10, best)
    return best


def _eg_army_est(S):
    if S.eg is None:
        return None
    if S.vis[S.eg]:
        return S.arm[S.eg]
    if S.eg_seen_t < 0:
        return S.t // 2
    # a general gains 1 per 2 turns if it never spends; most bots spend, so assume a share
    est = S.eg_army + int((S.t - S.eg_seen_t) * PARAMS["EG_GROWTH"])
    return min(est, max(1, S.opp_army - S.opp_land + 1))


def _gather(S, roots, lam, max_nodes=None, exclude=None, frozen=None):
    """Gather move toward `roots` over our own cells.

    Builds a BFS tree over our cells rooted at `roots`, prunes subtrees whose
    gatherable army per move is below `lam` (tree DP), then moves the deepest
    selected cell holding >= 2 army toward its parent. Returns (action, gain, moves).
    """
    own, arm, adj = S.own, S.arm, S.adj
    depth = {}
    parent = {}
    q = []
    for r in roots:
        depth[r] = 0
        parent[r] = -1
        q.append(r)
    for x in q:
        dx = depth[x] + 1
        for y in adj[x]:
            if own[y] == 1 and y not in depth and (exclude is None or y not in exclude):
                depth[y] = dx
                parent[y] = x
                q.append(y)
    rootset = set(roots)

    def select(lmb):
        f = {}
        for x in reversed(q):
            if x in rootset:
                continue
            own_v = 0 if (frozen is not None and x in frozen) else arm[x] - 1
            v = own_v - lmb + f.get(x, 0)
            f[x] = v
            p = parent[x]
            if p not in rootset and v > 0:
                f[p] = f.get(p, 0) + v
        sel = []
        ss = set()
        for x in q:
            if x in rootset:
                continue
            if f[x] > 0 and (parent[x] in rootset or parent[x] in ss):
                ss.add(x)
                sel.append(x)
        return sel

    sel = select(lam)
    if max_nodes is not None:
        lmb = lam
        while len(sel) > max_nodes and lmb < 64:
            lmb = lmb * 2 + 0.5
            sel = select(lmb)
    best = None
    bkey = None
    gain = 0
    for x in sel:
        a = arm[x]
        if frozen is None or x not in frozen:
            gain += a - 1
        if a >= 2:
            k = (depth[x], a)
            if bkey is None or k > bkey:
                bkey = k
                best = x
    if best is None:
        return None, 0, 0
    return _mv(S, best, parent[best]), gain, len(sel)


def _gather_k(S, root, k, exclude=None):
    """Best gather toward `root` using at most k moves (for emergencies).

    Greedy: repeatedly add the tree path (toward the already selected set) with the best
    army-per-move ratio that still fits the budget. Every selected cell moves exactly once,
    deepest first, so everything selected arrives within k turns.
    Returns (action, gain, moves).
    """
    own, arm, adj = S.own, S.arm, S.adj
    depth = {root: 0}
    parent = {root: -1}
    q = [root]
    for x in q:
        dx = depth[x] + 1
        if dx > k:
            continue
        for y in adj[x]:
            if own[y] == 1 and y not in depth and (exclude is None or y not in exclude):
                depth[y] = dx
                parent[y] = x
                q.append(y)
    sel = {root}
    budget = k
    gain = 0
    while budget > 0:
        best = None
        bratio = 0.0
        for v in q:
            if v in sel:
                continue
            g_ = 0
            c = 0
            x = v
            while x not in sel:
                g_ += arm[x] - 1
                c += 1
                x = parent[x]
            if c > budget or g_ <= 0:
                continue
            r = g_ / c
            if r > bratio:
                bratio, best = r, v
        if best is None:
            break
        x = best
        while x not in sel:
            sel.add(x)
            gain += arm[x] - 1
            budget -= 1
            x = parent[x]
    mv = None
    mk = None
    for x in sel:
        if x != root and arm[x] >= 2:
            kk = (depth[x], arm[x])
            if mk is None or kk > mk:
                mk, mv = kk, x
    if mv is None:
        return None, 0, 0
    return _mv(S, mv, parent[mv]), gain, len(sel) - 1


# ---------------------------------------------------------------------------
# Exact one-turn simulator (mirrors game._determine_move_order / _apply_move /
# deathtouch) for local tactics. Moves are (src, dst, split) or None; builds
# are ('b', cell, cost).
# ---------------------------------------------------------------------------
def _sim(S, own0, arm0, my_mv, en_mv, t):
    """Return (result, own_overlay, arm_overlay). result: 1 we win, -1 we lose, 0 draw, None ongoing."""
    own = {}
    arm = {}

    def go(i):
        return own[i] if i in own else own0[i]

    def ga(i):
        return arm[i] if i in arm else arm0[i]

    me_idx = S.pid
    en_idx = 1 - S.pid
    moves = []
    for player, mv, other in ((1, my_mv, en_mv), (2, en_mv, my_mv)):
        idx = me_idx if player == 1 else en_idx
        if mv is None or mv[0] == 'b':
            moves.append((1, 1, 1 << 40, idx, player, None))
            continue
        s, d, sp = mv
        chasing = other is not None and other[0] != 'b' and d == other[0]
        reinforcing = own0[d] == player
        moves.append((0 if chasing else 1, 0 if reinforcing else 1, arm0[s], idx, player, mv))
    # builds first
    for player, mv in ((1, my_mv), (2, en_mv)):
        if mv is not None and mv[0] == 'b':
            _, cell, cost = mv
            if go(cell) == player and ga(cell) >= cost:
                arm[cell] = ga(cell) - cost
    moves.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    touch = {1: False, 2: False}
    capt = {1: False, 2: False}
    gen_of = {1: S.myG, 2: S.eg}   # general owned by player
    for _, _, _, _, player, mv in moves:
        if mv is None:
            continue
        s, d, sp = mv
        if go(s) != player:
            continue
        a = ga(s)
        amt = a // 2 if sp else a - 1
        if amt > a - 1:
            amt = a - 1
        if amt <= 0:
            continue
        foe = 3 - player
        target_gen = gen_of[foe]
        if target_gen is not None and d == target_gen and t >= 800:
            touch[player] = True
        arm[s] = a - amt
        if go(d) == player:
            arm[d] = ga(d) + amt
        else:
            da = ga(d)
            if amt > da:
                own[d] = player
                arm[d] = amt - da
                if target_gen is not None and d == target_gen:
                    capt[player] = True
            else:
                arm[d] = da - amt
    w1 = touch[1] or capt[1]
    w2 = touch[2] or capt[2]
    if w1 and w2:
        return 0, own, arm
    if w1:
        return 1, own, arm
    if w2:
        return -1, own, arm
    return None, own, arm


def _local_moves(S, cells, player, own, arm):
    out = []
    adj = S.adj
    for s in cells:
        if own[s] == player and arm[s] >= 2:
            for d in adj[s]:
                out.append((s, d, 0))
    return out


def _static_eval(S, own0, arm0, ov_own, ov_arm, t_next):
    """Score the position at the start of the next turn from our side."""
    def go(i):
        return ov_own[i] if i in ov_own else own0[i]

    def ga(i):
        return ov_arm[i] if i in ov_arm else arm0[i]

    adj = S.adj
    score = 0
    g = S.myG
    # Enemy threats against our general
    threats = []
    for x in adj[g]:
        if go(x) == 2 and ga(x) >= 2:
            threats.append(x)
    if threats:
        if t_next >= 800:
            unanswered = 0
            for x in threats:
                ax = ga(x)
                ok = False
                for y in adj[x]:
                    if y != g and go(y) == 1 and ga(y) >= ax:
                        ok = True
                        break
                if not ok:
                    unanswered += 1
            if unanswered or len(threats) >= 2:
                return -800
            score -= 60
        else:
            # before deathtouch: an adjacent stack that beats the general plus our best
            # single reinforcement captures it next turn
            gar = ga(g)
            best_re = 0
            for y in adj[g]:
                if go(y) == 1:
                    best_re = max(best_re, ga(y) - 1)
            for x in threats:
                if ga(x) - 1 > gar + best_re:
                    return -700
                if ga(x) - 1 > gar:
                    score -= 100
    if t_next >= 800:
        # one step further: an enemy stack next to a neighbour X of our general that can take X
        # and keep >= 2 there with no counter from a third tile is a threat for the turn after
        for x in adj[g]:
            ox, ax = go(x), ga(x)
            if ox == 2:
                continue
            for z in adj[x]:
                if z == g or go(z) != 2:
                    continue
                rest = ga(z) - 1 - (ax if ox == 1 else 0)
                if rest >= 2:
                    ok = False
                    for y in adj[x]:
                        if y != g and y != z and go(y) == 1 and ga(y) >= rest:
                            ok = True
                            break
                    if not ok:
                        score -= 250
    # Our threats against their general
    e = S.eg
    if e is not None:
        mine_adj = [x for x in adj[e] if go(x) == 1 and ga(x) >= 2]
        if mine_adj:
            if t_next >= 800:
                unanswered = 0
                for x in mine_adj:
                    ax = ga(x)
                    ok = False
                    for y in adj[x]:
                        if y != e and go(y) == 2 and ga(y) >= ax:
                            ok = True
                            break
                    if not ok:
                        unanswered += 1
                if unanswered or len(mine_adj) >= 2:
                    score += 500
                else:
                    score += 50
            else:
                ge = ga(e)
                for x in mine_adj:
                    if ga(x) - 1 > ge:
                        score += 100
    # Material near our general and theirs
    for i, v in ov_arm.items():
        o = go(i)
        if o == 1:
            score += 0.01 * (v - arm0[i]) if own0[i] == 1 else 0.02 * v
        elif o == 2:
            score -= 0.01 * (v - arm0[i]) if own0[i] == 2 else 0.02 * v
    return score


def _tactical(S, strategic_mv):
    """2-ply search: our move vs every enemy reply, near both generals.

    Returns an action list if it should override the strategic move, else None.
    """
    t = S.t
    own, arm, dist = S.own, S.arm, S.dist
    g = S.myG
    e = S.eg
    dg = dist[g]
    near_me = [i for i in S.passable if dg[i] <= PARAMS["TACT_R_ME"]]
    hot_me = any(own[i] == 2 for i in near_me if dg[i] <= 2) or any(
        own[i] == 2 and arm[i] >= 2 for i in near_me)
    hot_en = False
    near_en = []
    if e is not None:
        de = dist[e]
        near_en = [i for i in S.passable if de[i] <= PARAMS["TACT_R_EN"]]
        hot_en = any(own[i] == 1 and arm[i] >= 2 and de[i] <= 2 for i in near_en)
    if not hot_me and not hot_en:
        return None
    cells = set()
    if hot_me:
        cells.update(near_me)
    if hot_en:
        cells.update(near_en)
    my_moves = _local_moves(S, cells, 1, own, arm)
    en_moves = _local_moves(S, cells, 2, own, arm)
    # also let our general split (keeps a garrison)
    if own[g] == 1 and arm[g] >= 4:
        for d in S.adj[g]:
            my_moves.append((g, d, 1))
    if len(en_moves) > 30:
        en_moves.sort(key=lambda m: -arm[m[0]])
        en_moves = en_moves[:30]
    if len(my_moves) > 30:
        my_moves.sort(key=lambda m: -arm[m[0]])
        my_moves = my_moves[:30]
    en_moves.append(None)
    strat_key = None
    if strategic_mv is not None:
        if strategic_mv[0] == 0:
            s = strategic_mv[1] * S.W + strategic_mv[2]
            d = s + (-S.W, S.W, -1, 1)[strategic_mv[3]]
            strat_key = (s, d, strategic_mv[4])
        elif strategic_mv[0] == 2:
            cell = strategic_mv[1] * S.W + strategic_mv[2]
            strat_key = ('b', cell, _build_cost(S, cell))
    # the strategic move is scored first and exactly (no pruning)
    cand = [strat_key] + [m for m in my_moves if m != strat_key]
    if strat_key is not None:
        cand.append(None)
    found = False
    best = None
    best_score = None
    strat_score = None
    t_next = t + 1
    guess = t >= 799            # deathtouch: count losing replies instead of stopping at the first
    nlose_of = {}
    complete = True
    for k, m in enumerate(cand):
        worst = None
        nlose = 0
        for em in en_moves:
            res, oo, oa = _sim(S, own, arm, m, em, t)
            if res == 1:
                sc = 1000
            elif res == -1:
                sc = -1000
            elif res == 0:
                sc = -300
            else:
                sc = _static_eval(S, own, arm, oo, oa, t_next)
            if sc <= -1000:
                nlose += 1
            if worst is None or sc < worst:
                worst = sc
                if guess:
                    if worst > -1000 and k > 0 and worst <= best_score:
                        break
                elif worst <= -1000 or (k > 0 and worst <= best_score):
                    break
        if guess and worst is not None and worst <= -1000:
            nlose_of[k] = nlose
        if k == 0:
            strat_score = worst
        if not found or worst > best_score:
            best_score = worst
            best = m
            found = True
        if _time_left(S) < 0:
            complete = False
            break
    if guess and found and complete and best_score <= -1000 and len(nlose_of) == len(cand):
        # Every move of ours loses to some enemy reply. The enemy must guess too, so play the
        # move with the fewest losing replies, breaking ties at random.
        lo = min(nlose_of.values())
        ks = [k for k, v in nlose_of.items() if v == lo]
        if 0 in ks:
            return None
        best = cand[S.rng.choice(ks)]
        _log(t, "tactical guess", best, "losing replies", lo)
        if best is None:
            return list(PASS)
        if best[0] == 'b':
            r, c = S.rc[best[1]]
            return [2, r, c, 0, 0]
        return _mv(S, best[0], best[1], best[2])
    if not found or strat_score >= best_score - 20:
        return None
    _log(t, "tactical override", best, best_score, "strategic", strat_key, strat_score)
    if best is None:
        return list(PASS)
    if best[0] == 'b':
        r, c = S.rc[best[1]]
        return [2, r, c, 0, 0]
    return _mv(S, best[0], best[1], best[2])


# ---------------------------------------------------------------------------
# Decision making
# ---------------------------------------------------------------------------
def _choose(S):
    a = _win_now(S)
    if a is not None:
        return a
    strat = _strategic(S)
    try:
        if _time_left(S) > 0.02:
            tac = _tactical(S, strat)
            if tac is not None:
                return tac
    except Exception:
        if DEBUG:
            import traceback
            traceback.print_exc()
    return strat if strat is not None else list(PASS)


def _win_now(S):
    e = S.eg
    if e is None:
        return None
    own, arm = S.own, S.arm
    best = None
    bv = None
    for x in S.adj[e]:
        if own[x] == 1 and arm[x] >= 2:
            if S.t >= 800:
                # pick the attacker that is hardest to intercept
                threat = 0
                for y in S.adj[x]:
                    if y != e and own[y] == 2:
                        threat = max(threat, arm[y])
                v = arm[x] - threat
                if bv is None or v > bv:
                    bv, best = v, x
            elif S.vis[e] and own[e] == 2 and arm[x] - 1 > arm[e]:
                v = arm[x] - arm[e]
                if bv is None or v > bv:
                    bv, best = v, x
    if best is None:
        return None
    if S.t >= 800 and bv is not None and bv <= 0:
        # Every attacker can be countered, but the enemy has only one move: with two or more
        # attackers it is a guessing game, so pick one at random (a fixed choice could be
        # blocked every turn by a defender that always counters the same cell). Only when our
        # own general is not about to be touched; otherwise the tactical search decides.
        atk = [x for x in S.adj[e] if own[x] == 1 and arm[x] >= 2]
        danger = any(own[y] == 2 and arm[y] >= 2 for y in S.adj[S.myG])
        if len(atk) >= 2 and not danger:
            return _mv(S, S.rng.choice(atk), e)
        return None
    return _mv(S, best, e)


def _strategic(S):
    late = S.t >= PARAMS["STRIKE_T"] and S.eg is not None
    if late or not PARAMS["ECON_FIRST"] or S.t < PARAMS["ECON_FIRST_T"]:
        order = (_defend, _fortress, _march_first, _home_castle, _castle_walk, _continue_plan, _raid, _strike,
                 _economy_idle, _expand, _idle)
    else:
        order = (_defend, _fortress, _march_first, _economy, _continue_plan, _raid, _strike, _expand, _idle)
    for f in order:
        a = f(S)
        if a is not None:
            if DEBUG:
                S.layer = f.__name__
            return a
        if _time_left(S) < 0:
            break
    if DEBUG:
        S.layer = "pass"
    return None


# --- defense ---------------------------------------------------------------
def _threats(S):
    """Enemy stacks (visible, or seen in the last few turns) that could reach our general."""
    g = S.myG
    dg = S.dist[g]
    t = S.t
    out = []
    R = PARAMS["THREAT_R"]
    for i in S.enemy:
        a = S.arm[i]
        if a >= 3 and dg[i] <= R:
            out.append((i, a, dg[i]))
    vis = S.vis
    for i, ts in S.enemy_seen_cells.items():
        if not vis[i] and t - ts <= 8 and S.mem_army[i] >= 5 and dg[i] <= R:
            # it may have moved one step per turn toward us since
            out.append((i, S.mem_army[i], max(1, dg[i] - (t - ts))))
    for a, d, t0g, c in S.ghosts:
        dd = max(1, d - (t - t0g))
        if dd <= R:
            out.append((g, a, dd))           # labelled with our own general: never mistaken for a visible stack
    return out


def _garrison(S):
    """Garrison target near home: recent enemy waves, and a share of the army the enemy
    could concentrate (opp_army minus one per owned cell bounds any stack they can bring)."""
    g1 = 0
    if S.threat_hist:
        f = PARAMS["GARRISON_F"]
        if S.t - S.hit_t <= PARAMS["GARRISON_HIT_MEM"]:
            f = max(f, PARAMS["GARRISON_HIT_F"])   # they reached our general recently: expect more
        g1 = f * max(a for _, a in S.threat_hist)
    free = max(0, S.opp_army - S.opp_land)
    g2 = PARAMS["GARRISON_FREE_F"] * free if S.t >= PARAMS["GARRISON_FREE_T"] else 0
    return int(max(g1, g2))


def _keep(S):
    """Army the general will not SPEND (runs, castles, strike feeds). Costs no moves: the general
    simply accumulates. Sized against the waves seen and a share of the enemy's free army."""
    k = max(_reserve(S), _garrison(S))
    free = max(0, S.opp_army - S.opp_land)
    if S.t >= PARAMS["KEEP_T"]:
        k = max(k, int(PARAMS["KEEP_FREE_F"] * free))
    # Opponent-adaptive: an enemy that owns much less land than we do while holding army is
    # hoarding for a rush. Its free army (opp_army - opp_land) bounds the stack it can bring.
    if S.found_me and PARAMS["FOUND_KEEP_F"] > 0:
        # they know where our general is: bank its production against their strike
        k = max(k, int(PARAMS["FOUND_KEEP_F"] * free))
    if S.t >= PARAMS["HOARD_T"] and S.opp_land < PARAMS["HOARD_LAND_RATIO"] * S.my_land \
            and free >= PARAMS["HOARD_MIN_FREE"]:
        k = max(k, int(PARAMS["HOARD_KEEP_F"] * free))
    return k


def _home_army(S):
    """Army that can reach the general within about two moves."""
    g = S.myG
    own, arm, dg = S.own, S.arm, S.dist[S.myG]
    tot = arm[g]
    for y in S.adj[g]:
        if own[y] == 1 and arm[y] > 1:
            tot += arm[y] - 1
    for c in S.my_castles:
        if 2 <= dg[c] <= 3 and arm[c] > 1:
            tot += arm[c] - 1
    return tot


def _reserve(S):
    """Army the general must keep against the threats we know about."""
    r = 0
    for i, a, d in _threats(S):
        v = a - 1 - d // 2 + PARAMS["DEF_MARGIN"]
        if v > r:
            r = v
    return r


def _safe_without_general(S, ignore):
    """Would emptying the general be safe from every visible stack except `ignore`?"""
    dg = S.dist[S.myG]
    for i in S.enemy:
        if i != ignore and S.arm[i] >= 3 and dg[i] <= 6:
            return False
    return True


def _defend(S):
    g = S.myG
    own, arm, adj, dist = S.own, S.arm, S.adj, S.dist
    threats = _threats(S)
    gar = arm[g]
    kr = PARAMS["KILL_R"]
    visible = [(i, a, d) for i, a, d in threats if S.vis[i] and own[i] == 2]
    # A) kill an enemy stack near home whenever one of our neighbours beats it
    kills = []
    for i, a, d in visible:
        if d > kr:
            continue
        for y in adj[i]:
            if own[y] != 1:
                continue
            ay = arm[y]
            if y == g:
                if ay // 2 > a and S.t < 800:
                    kills.append((d, -a, y, i, 1))
                elif ay - 1 > a and (S.t >= 800 or _safe_without_general(S, i)):
                    kills.append((d, -a, y, i, 0))
            elif ay - 1 > a:
                kills.append((d, -a, y, i, 0))
    if kills:
        kills.sort()
        _, _, y, i, sp = kills[0]
        if PARAMS["PUNCH_MIN"] > 0 and arm[i] >= PARAMS["PUNCH_MIN"]:
            S.punch_t = S.t
        _log(S.t, "defend kill", S.rc[i], arm[i], "from", S.rc[y], arm[y])
        return _mv(S, y, i, sp)
    # B before A2: when the general is really in danger, reinforcing beats chasing a moving stack
    if S.t < 800:
        # B) a stack that could beat the general by the time it arrives: pull army home fast
        worst = None
        # stacks can merge on the way in: judge them cumulatively by arrival time
        cum = 0
        for i, a, d in sorted(threats, key=lambda x: x[2]):
            # sum only stacks we can see right now (remembered cells would double count a
            # moving stack) and only real stacks
            if S.vis[i] and own[i] == 2 and a >= PARAMS["THREAT_SUM_MIN"]:
                cum += a
            for power in ((a - 1, cum - 1) if PARAMS["THREAT_SUM"] else (a - 1,)):
                cap = gar + d // 2
                need = power - cap + PARAMS["DEF_MARGIN"]
                if need > 0 and (worst is None or need / max(d, 1) > worst[0]):
                    worst = (need / max(d, 1), i, a, d, need)
        if worst is not None:
            _, i, a, d, need = worst
            if _strike_lands_first(S, d):
                return None
            act, gain, n = _gather_k(S, g, max(1, d))
            if act is None or gain < need:
                dg_ = dist[g]
                # 1) a stack that can walk home before the threat arrives (its path may cross
                #    land we do not own, which the gather tree cannot see): bring it home
                if PARAMS["WALK_HOME"]:
                    bh = None
                    for y in S.mine:
                        if y == g or arm[y] < 4 or dg_[y] <= 1 or dg_[y] > d:
                            continue
                        if S.plan is not None and S.plan.get("phase") == "march" and y == S.plan.get("at") \
                                and _strike_lands_first(S, d):
                            continue
                        if bh is None or arm[y] > arm[bh]:
                            bh = y
                    if bh is not None and arm[bh] - 1 > gain:
                        nxt = _step_toward(S, bh, g)
                        if nxt is not None and (own[nxt] != 2 or arm[nxt] < arm[bh] - 1):
                            if S.plan is not None and S.plan.get("at") == bh:
                                S.plan = None
                            _log(S.t, "defend walk home", S.rc[bh], arm[bh], "vs", a, "at", d)
                            return _mv(S, bh, nxt)
                # 2) hit the stack with our biggest stack that can reach it first (combat destroys
                #    equal amounts, so even a smaller stack helps) - only if it can strike now
                if S.vis[i] and own[i] == 2:
                    di = dist[i]
                    bx = None
                    for y in S.mine:
                        if y == g or arm[y] < 6 or dg_[y] <= 1:
                            continue  # stacks beside the general are its reinforcement, keep them
                        if di[y] <= (1 if PARAMS["WALK_HOME"] else d) and (bx is None or arm[y] > arm[bx]):
                            bx = y
                    if bx is not None and arm[bx] - 1 >= min(need - gain, a) * 0.5 and arm[bx] >= 0.4 * a:
                        if di[bx] == 1:
                            nxt = i
                        else:
                            nxt = _step_toward(S, bx, i)
                        if nxt is not None:
                            if S.plan is not None and S.plan.get("kind") == "strike":
                                S.plan = None
                            _log(S.t, "defend counter", S.rc[i], a, "with", S.rc[bx], arm[bx])
                            return _mv(S, bx, nxt)
            if act is not None and gain > 0:
                if S.plan is not None and S.plan.get("phase") == "gather":
                    S.plan = None
                _log(S.t, "defend gather", gain, "need", need)
                return act
    # A2) intercept: walk a stack that beats a nearby enemy stack toward it
    best = None
    for i, a, d in visible:
        if d > kr or a < 3:
            continue
        di = dist[i]
        for y in S.mine:
            dy = di[y]
            if dy < 2 or dy > PARAMS["INTERCEPT_R"]:
                continue
            ay = arm[y]
            usable = ay // 2 if y == g else ay - 1
            if usable <= a + 2 * dy:
                continue
            if y == g and S.t < 800 and ay - usable < _reserve_excluding(S, i):
                continue
            k = (dy, d, -ay)
            if best is None or k < best[0]:
                best = (k, y, i)
    if best is not None:
        _, y, i = best
        nxt = _step_toward(S, y, i)
        if nxt is not None and (own[nxt] != 2 or arm[nxt] < (arm[y] // 2 if y == g else arm[y] - 1)):
            _log(S.t, "defend intercept", S.rc[i], arm[i], "from", S.rc[y], arm[y])
            return _mv(S, y, nxt, 1 if y == g else 0)
    if S.t >= 800:
        return None  # post-800 handled by tactics and fortress
    # D) keep the long-memory garrison on (or next to) the general
    gn = _garrison(S)
    plan = S.plan
    striking = plan is not None and plan.get("kind") == "strike"
    if gn > 0 and not (striking and plan.get("phase") == "gather"):
        near = _home_army(S)
        if near < gn:
            # never pull a marching strike stack back
            excl = {plan["at"]} if striking and plan.get("at") is not None else None
            act, gain, n = _gather_amount(S, g, gn - near, exclude=excl)
            if act is not None and gain >= 3:
                _log(S.t, "defend garrison", near, "target", gn)
                return act
    return None


def _strike_lands_first(S, their_eta):
    """True if our marching strike will take the enemy general before their stack lands."""
    p = S.plan
    e = S.eg
    if p is None or p.get("kind") != "strike" or p.get("phase") != "march" or e is None:
        return False
    at = p.get("at")
    if at is None or S.own[at] != 1:
        return False
    army_path, path = _path_cost(S, at, e)
    if path is None:
        return False
    eta = len(path) - 1
    if eta >= their_eta:
        return False
    if S.t + eta >= 800:
        return S.arm[at] - army_path >= 3
    est = (_eg_army_est(S) or 0) + eta // 2
    return S.arm[at] - 1 - army_path > est + 2


def _reserve_excluding(S, ignore):
    r = 0
    for i, a, d in _threats(S):
        if i == ignore:
            continue
        v = a - 1 - d // 2 + PARAMS["DEF_MARGIN"]
        if v > r:
            r = v
    return r


def _fortress(S):
    """From FORT_T: claim/hold the ring around our general and clear nearby enemy."""
    t = S.t
    if t < PARAMS["FORT_T"]:
        return None
    g = S.myG
    own, arm, dist = S.own, S.arm, S.dist
    dg = dist[g]
    # attack enemy cells close to the general
    best = None
    bk = None
    for i in S.enemy:
        if dg[i] <= PARAMS["FORT_R"]:
            for y in S.adj[i]:
                if own[y] != 1:
                    continue
                if y == g and t < 800:
                    # before deathtouch the general must keep its army: only a half split
                    if arm[y] // 2 > arm[i]:
                        k = (dg[i], -arm[i], 1)
                        if bk is None or k < bk:
                            bk, best = k, (y, i, 1)
                    continue
                if arm[y] - 1 > arm[i]:
                    k = (dg[i], -arm[i], 0)
                    if bk is None or k < bk:
                        bk, best = k, (y, i, 0)
    if best is not None:
        return _mv(S, best[0], best[1], best[2])
    # own every neighbour of the general
    for x in S.adj[g]:
        if own[x] == 0:
            if arm[g] >= 2:
                return _mv(S, g, x, 1 if arm[g] >= 4 else 0)
            for y in S.adj[x]:
                if own[y] == 1 and arm[y] >= 2:
                    return _mv(S, y, x, 0)
    return _moat(S)


def _enemy_stacks(S, max_age=15):
    """(cell, army) of enemy stacks: visible ones and recently remembered ones."""
    out = [(i, S.arm[i]) for i in S.enemy if S.arm[i] >= 3]
    t = S.t
    for i, ts in S.enemy_seen_cells.items():
        if not S.vis[i] and t - ts <= max_age and S.mem_army[i] >= 3:
            out.append((i, S.mem_army[i]))
    return out


def _moat(S):
    """Deathtouch defense: every neighbour of our general must hold at least as much as the
    biggest enemy stack that could reach it, so a capture leaves a small, counterable rest."""
    t = S.t
    g = S.myG
    own, arm, dist = S.own, S.arm, S.dist
    stacks = _enemy_stacks(S)
    worst = None
    for x in S.adj[g]:
        if own[x] != 1:
            continue
        dx = dist[x]
        need = PARAMS["MOAT_MIN"]
        for i, a in stacks:
            if dx[i] <= PARAMS["MOAT_R"]:
                need = max(need, a + 2)
        deficit = need - arm[x]
        if deficit > 0 and (worst is None or deficit > worst[0]):
            worst = (deficit, x)
    if worst is None:
        return None
    deficit, x = worst
    if t >= 800 and arm[g] >= 2:
        return _mv(S, g, x, 0)  # the general's own army cannot defend a touch: put it on the moat
    excl = {g} if t < 800 else None
    act, gain, n = _gather_amount(S, x, deficit, exclude=excl)
    if act is not None and gain >= 2:
        _log(t, "moat", S.rc[x], arm[x], "deficit", deficit)
        return act
    return None


# --- plans -------------------------------------------------------------------
def _castle_step(S):
    """Continue the castle plan: walk the stack to the site and build."""
    p = S.cplan
    if p is None:
        return None
    own, arm = S.own, S.arm
    if S.t - p["start"] > p.get("ttl", 30):
        S.cplan = None
        return None
    at, site = p["at"], p["site"]
    if own[at] != 1:
        S.cplan = None
        return None
    cost = _build_cost(S, site)
    if at == site:
        if S.typ[site] == 3:
            S.cplan = None
            return None
        if arm[site] >= cost:
            S.cplan = None
            r, c = S.rc[site]
            return [2, r, c, 0, 0]
        # wait / gather in a little
        act, gain, n = _gather(S, [site], PARAMS["GATHER_LAMBDA"], max_nodes=8)
        if act is not None and arm[site] + gain >= cost:
            return act
        if S.t - p["start"] > 40 or act is None:
            S.cplan = None
        return None
    if arm[at] < 2:
        S.cplan = None
        return None
    nxt = _step_toward(S, at, site, avoid_enemy=True)
    if nxt is None:
        S.cplan = None
        return None
    sp = p.pop("split", 0) if at == S.myG else 0
    p["at"] = nxt
    return _mv(S, at, nxt, sp)


def _continue_plan(S):
    """Continue the strike plan."""
    p = S.plan
    if p is None:
        return None
    if S.t - p["start"] > p.get("ttl", 60):
        S.plan = None
        return None
    if p["kind"] == "strike":
        return _strike_step(S)
    S.plan = None
    return None


def _home_castles(S):
    """Castles on cells touching our general: the defensive reserve."""
    dg = S.dist[S.myG]
    return {c for c in S.my_castles if dg[c] == 1}


def _home_castle(S):
    """Build a castle next to our general early. It banks +1 per 2 turns with no moves, one
    reinforcing move from the general, and nothing but defense is allowed to drain it."""
    t = S.t
    n_want = PARAMS["HOME_CASTLE_N"]
    if n_want <= 0 or t < PARAMS["HOME_CASTLE_T"] or t >= PARAMS["CASTLE_LAST_T"]:
        return None
    if len(_home_castles(S)) >= n_want:
        return None
    g = S.myG
    own, arm, typ = S.own, S.arm, S.typ
    if _reserve(S) > 0:
        return None            # not while a stack is bearing down on us
    tgt = _target(S)
    dtg = S.dist[tgt] if tgt is not None else None
    site = None
    sk = None
    for x in S.adj[g]:
        if own[x] != 1 or typ[x] != 1:
            continue
        k = (-arm[x], dtg[x] if dtg is not None else 0)
        if sk is None or k < sk:
            sk, site = k, x
    if site is None:
        return None
    cost = _build_cost(S, site)
    if arm[site] >= cost:
        _log(t, "home castle built at", S.rc[site], "cost", cost)
        r, c = S.rc[site]
        return [2, r, c, 0, 0]
    short = cost - arm[site]
    if arm[g] - 1 >= short:
        return _mv(S, g, site, 0)
    if PARAMS["HOME_CASTLE_MODE"] == 1:
        return None            # saving mode: the general stops its runs and simply accumulates
    excl = set()
    if S.plan is not None and S.plan.get("at") is not None and S.plan.get("phase") == "march":
        excl.add(S.plan["at"])
    act, gain, n = _gather_amount(S, site, short, exclude=excl or None, frozen=_claim_cells(S))
    if act is not None and gain >= short and n <= PARAMS["HOME_CASTLE_MAX_MOVES"]:
        return act
    return None


def _march_first(S):
    """A strike that is already marching keeps moving (timing and stealth matter)."""
    p = S.plan
    if p is not None and p.get("kind") == "strike" and p.get("phase") == "march":
        return _continue_plan(S)
    return None


def _economy(S):
    """Castle track: continue the castle plan or start a new one."""
    a = _castle_step(S)
    if a is not None:
        return a
    return _castle(S)


def _castle_walk(S):
    """A castle stack already walking finishes its walk unless a strike plan is active."""
    if S.cplan is not None and S.plan is None:
        return _castle_step(S)
    return None


def _economy_idle(S):
    """Castle track when it does not have priority: only while no strike plan is active
    (the behaviour of the versions before the separate track)."""
    if S.plan is not None:
        return None
    return _economy(S)


def _step_toward(S, at, goal, avoid_enemy=False):
    dg = S.dist[goal]
    best = None
    bk = None
    own, arm = S.own, S.arm
    for y in S.adj[at]:
        if dg[y] >= dg[at]:
            continue
        o = own[y]
        pen = 0
        if o == 2:
            pen = arm[y] + (100 if avoid_enemy else 0)
        k = (pen, -arm[y] if o == 1 else 0)
        if bk is None or k < bk:
            bk, best = k, y
    return best


# --- strike ------------------------------------------------------------------
def _enemy_sight(S):
    """Cells the enemy can probably see: their known land and its 8 neighbours (cached per turn)."""
    if S.sight_t == S.t:
        return S.sight
    sight = [False] * S.N
    nb8 = S.nb8
    own = S.own
    for i in S.enemy_seen_cells:
        if own[i] == 1:
            continue
        sight[i] = True
        for j in nb8[i]:
            sight[j] = True
    S.sight, S.sight_t = sight, S.t
    return sight


def _path_cost(S, src, goal, stealth=0.0):
    """Dijkstra from src to goal over passable cells, cost = 1 + enemy army estimate
    (+ `stealth` per cell the enemy can see, so strikes arrive with little warning).
    Returns (enemy_army_on_path, path list)."""
    import heapq
    own, arm, vis = S.own, S.arm, S.vis
    mem_own, mem_army = S.mem_own, S.mem_army
    N = S.N
    sight = _enemy_sight(S) if stealth else None
    best = {src: 0}
    prev = {src: -1}
    pq = [(0, src)]
    adj = S.adj
    while pq:
        c, x = heapq.heappop(pq)
        if x == goal:
            break
        if c > best.get(x, INF):
            continue
        for y in adj[x]:
            if vis[y]:
                w = arm[y] if own[y] == 2 else 0
                if own[y] == 1:
                    w = -0.5
            else:
                w = mem_army[y] if mem_own[y] == 2 else (1 if not S.seen_ever[y] else 0)
            nc = c + 1 + max(w, -0.5)
            if sight is not None and sight[y]:
                nc += stealth
            if nc < best.get(y, INF):
                best[y] = nc
                prev[y] = x
                heapq.heappush(pq, (nc, y))
    if goal not in prev:
        return None, None
    path = []
    x = goal
    while x != -1:
        path.append(x)
        x = prev[x]
    path.reverse()
    enemy_army = 0
    for y in path[1:-1]:
        if vis[y]:
            if own[y] == 2:
                enemy_army += arm[y]
        elif mem_own[y] == 2:
            enemy_army += mem_army[y]
        elif not S.seen_ever[y]:
            enemy_army += 1
    return enemy_army, path


def _strike_need(S, path_army, eta):
    """Army the strike stack must hold at launch to take the general on arrival."""
    t = S.t
    if t - S.punch_t <= PARAMS["PUNCH_WINDOW"]:
        # we just destroyed a big enemy stack near home: their side is at its weakest
        return _strike_need_base(S, path_army, eta) * PARAMS["PUNCH_F"]
    return _strike_need_base(S, path_army, eta)


def _strike_need_base(S, path_army, eta):
    t = S.t
    e = S.eg
    near = 0
    if e is not None:
        de = S.dist[e]
        for i in S.enemy:
            if i != e and de[i] <= 3:
                near += S.arm[i]
    if t + eta >= 800:
        # deathtouch: reach an adjacent cell and survive one interception
        need = path_army + 0.5 * near + 12
        if t >= 800:
            # nothing else matters now: bring a stack that wins the fight around their general
            need = max(need, PARAMS["POST800_SHARE"] * S.my_army)
    else:
        est = _eg_army_est(S) or 0
        est += eta // 2
        need = est + path_army + PARAMS["STRIKE_REINF"] * near + 3
    return need * PARAMS["STRIKE_MARGIN"] + PARAMS["STRIKE_EXTRA"]


def _cand_unlikeliness(S):
    """Per candidate: lower = more likely to be their general (cached for a few turns).

    Measured offline on 323 hidden-general situations (harness/rank_eval.py): mean distance to
    their known land, distance to the far end of that land as seen from us (trails lead home),
    and a penalty when the cells around the candidate are known not to be theirs."""
    key = (S.t // 4, len(S.cands), len(S.enemy_seen_cells))
    if S.lik_cache is not None and S.lik_cache[0] == key:
        return S.lik_cache[1]
    dist = S.dist
    seen = [i for i in S.enemy_seen_cells if S.own[i] != 1]
    out = {}
    if seen:
        dg = dist[S.myG]
        far = sorted(seen, key=lambda e: -dg[e])
        far = far[:max(1, len(far) // 3)]
        if len(seen) > 40:
            seen = seen[:: len(seen) // 40 + 1]
        mem_own, seen_ever = S.mem_own, S.seen_ever
        for c in S.cands:
            dc = dist[c]
            mean = sum(dc[e] for e in seen) / len(seen)
            fmean = sum(dc[e] for e in far) / len(far)
            tot = 0
            non = 0
            for i in S.passable:
                if dc[i] <= 3 and seen_ever[i]:
                    tot += 1
                    if mem_own[i] != 2:
                        non += 1
            pen = non / tot if tot else 0.0
            out[c] = 0.5 * mean + 0.5 * fmean + 6.0 * pen
    else:
        for c in S.cands:
            out[c] = 0.0
    S.lik_cache = (key, out)
    return out


def _hunt_target(S, origin):
    """Enemy general if known, else the most promising candidate as seen from origin."""
    if S.eg is not None:
        return S.eg
    if not S.cands:
        return None
    unl = _cand_unlikeliness(S)
    do = S.dist[origin]
    w = PARAMS["HUNT_LIK"]
    best = None
    bk = None
    for c in S.cands:
        k = do[c] + w * unl[c]
        if bk is None or k < bk:
            bk, best = k, c
    return best


def _gather_amount(S, root, want, max_nodes=None, exclude=None, frozen=None):
    """Gather toward root, preferring the most efficient subtree that still yields `want`."""
    last = None
    for lam in (12, 6, 3, 1.5, 0.75, 0.3):
        act, gain, n = _gather(S, [root], lam, max_nodes=max_nodes, exclude=exclude, frozen=frozen)
        if act is None:
            continue
        last = (act, gain, n)
        if gain >= want:
            return last
    return last if last is not None else (None, 0, 0)


def _strike(S):
    t = S.t
    hunting = S.eg is None
    snipe = (PARAMS["SNIPE_CANDS"] > 0 and hunting and t >= PARAMS["SNIPE_T"]
             and len(S.cands) <= PARAMS["SNIPE_CANDS"])
    if hunting and not ((t >= PARAMS["HUNT_T"] and S.enemy_seen_cells) or t >= PARAMS["SCOUT_T"] or snipe):
        return None
    if not hunting and t < S.strike_cooldown and t < PARAMS["STRIKE_T"]:
        return None
    own, arm = S.own, S.arm
    g = S.myG
    tgt = _hunt_target(S, g)
    if tgt is None:
        return None
    dist_t = S.dist[tgt]
    # launch cell: the cell of our main territory (the connected part holding most army)
    # closest to the target; isolated outposts cannot gather anything
    main = _main_component(S)
    launch = None
    lk = None
    for i in main:
        k = dist_t[i] - arm[i] / 40.0
        if lk is None or k < lk:
            lk, launch = k, i
    if launch is None:
        return None
    path_army, path = _path_cost(S, launch, tgt)
    if path is None:
        return None
    eta = len(path) - 1
    need = _strike_need(S, path_army, eta)
    _, gain, n = _gather(S, [launch], 0.3)
    avail = arm[launch] - 1 + gain
    excl = None
    th = [d for i, a, d in _threats(S) if a - 1 > 1 + d // 2]
    race_ok = not th or n + eta + 2 < min(th)
    if launch != g or not race_ok:
        # the general's army joins only through its explicit half-feed above the garrison
        if launch == g:
            return None
        excl = {g}
        _, gain, n = _gather(S, [launch], 0.3, exclude=excl, frozen=_claim_cells(S) | _home_castles(S))
        gn = _keep(S)
        avail = arm[launch] - 1 + gain + max(0, min(arm[g] // 2, arm[g] - gn))
    go = False
    if DEBUG and t % 10 == 0:
        _log(t, "strike eval launch", S.rc[launch], "tgt", S.rc[tgt], "eg", S.eg is not None, "need", round(need),
             "avail", avail, "n", n, "eta", eta, "path_army", path_army, "excl", excl, "est", _eg_army_est(S))
    if not hunting:
        if avail >= need:
            go = True
        elif t >= PARAMS["STRIKE_T"] and t + n + eta >= 780:
            go = True  # deathtouch window: commit what we have
    else:
        go = avail >= (PARAMS["SNIPE_MIN"] if snipe and t < PARAMS["SCOUT_T"] else PARAMS["HUNT_MIN"])
    if not go:
        return None
    if hunting:
        # a hunt marches with a real stack, not just the bare path cost
        need = max(need, min(avail, PARAMS["HUNT_MIN"] * PARAMS["HUNT_FILL"]))
    S.plan = dict(kind="strike", start=t, ttl=260, launch=launch, need=need, phase="gather",
                  target=tgt, at=launch, excl=excl)
    _log(t, "strike plan", S.rc[launch], "->", S.rc[tgt], "need", round(need), "avail", avail,
         "hunting" if hunting else "")
    return _strike_step(S)


def _main_component(S):
    """Cells of our connected territory that holds the most army."""
    own, arm, adj = S.own, S.arm, S.adj
    seen = set()
    best = None
    bsum = -1
    for i in S.mine:
        if i in seen:
            continue
        comp = [i]
        seen.add(i)
        tot = 0
        for x in comp:
            tot += arm[x]
            for y in adj[x]:
                if own[y] == 1 and y not in seen:
                    seen.add(y)
                    comp.append(y)
        if tot > bsum:
            bsum, best = tot, comp
    return best or []


def _claim_cells(S):
    """Small frontier stacks that can claim neutral land themselves."""
    own, arm = S.own, S.arm
    out = set()
    for i in S.mine:
        if 2 <= arm[i] <= 3:
            for n in S.adj[i]:
                if own[n] == 0:
                    out.add(i)
                    break
    return out


def _strike_excl(S, p):
    """Cells a strike gather must not pull from: its own exclusions plus a walking castle stack."""
    excl = p.get("excl")
    if S.cplan is not None:
        excl = set(excl) if excl else set()
        excl.add(S.cplan["at"])
    return excl


def _new_head(S, tgt):
    own, arm = S.own, S.arm
    dt = S.dist[tgt]
    best = None
    bk = None
    g = S.myG
    for i in S.mine:
        if arm[i] >= 2 and i != g and i not in S.my_castles:
            k = -arm[i] + dt[i] * 3
            if bk is None or k < bk:
                bk, best = k, i
    return best


def _strike_step(S):
    p = S.plan
    own, arm = S.own, S.arm
    t = S.t
    if p["phase"] == "gather":
        L = p["launch"]
        if own[L] != 1:
            S.plan = None
            return None
        tgt = _hunt_target(S, L)
        if tgt is None:
            S.plan = None
            return None
        remaining = p["need"] - (arm[L] - 1)
        dl = S.dist[L][tgt]
        # "late": the last moment to leave so the stack is adjacent on turn 799. Only before
        # 800; afterwards a strike gathers its full need like any other.
        late = S.eg is not None and t < 800 and t + dl >= 795
        g = S.myG
        excl = p.get("excl")
        if remaining > 0 and not late and excl and g in excl and L != g:
            gn = _keep(S)
            half = arm[g] // 2
            if half >= 8 and arm[g] - half >= gn:
                nxt = None
                dL = S.dist[L]
                for y in S.adj[g]:
                    if own[y] == 1 and dL[y] < dL[g] and (nxt is None or arm[y] > arm[nxt]):
                        nxt = y
                if nxt is not None:
                    return _mv(S, g, nxt, 1)
        if remaining > 0 and not late and t - p["start"] < 90:
            act, gain, n = _gather_amount(S, L, remaining, exclude=_strike_excl(S, p),
                                          frozen=(_claim_cells(S) if p.get("excl") else set()) | _home_castles(S))
            if act is not None and gain >= 3:
                return act
        if PARAMS["STRIKE_ABANDON"] and remaining > 0 and S.eg is not None \
                and t < PARAMS["STRIKE_T"] and not late:
            # could not reach the army needed to take a known general: do not throw the stack
            # away. Back to economy; try again later.
            S.plan = None
            S.strike_cooldown = t + PARAMS["STRIKE_COOLDOWN"]
            _log(t, "strike abandoned: short by", remaining)
            return None
        p["phase"] = "march"
        p["at"] = L
        _log(t, "strike march from", S.rc[L], "army", arm[L])
    at = p["at"]
    if own[at] != 1 or arm[at] < 2:
        tgt0 = p.get("target")
        at = _new_head(S, tgt0 if tgt0 is not None else S.myG)
        if at is None or arm[at] < 12:
            S.plan = None
            return None
        p["at"] = at
    tgt = _hunt_target(S, at)
    if tgt is None or tgt == at:
        S.plan = None
        return None
    p["target"] = tgt
    path_army, path = _path_cost(S, at, tgt, PARAMS["STEALTH_COST"])
    if path is None or len(path) < 2:
        S.plan = None
        return None
    nxt = path[1]
    eg = S.eg
    if eg is not None and t < 800:
        dd = S.dist[at][eg]
        est = arm[eg] if S.vis[eg] else (_eg_army_est(S) or 0)
        can_capture = arm[at] - 1 - path_army > est + dd // 2 + 1
        if not can_capture and dd <= PARAMS["STAGE_D"] and t < 801 - dd:
            # Too weak to capture outright: stage a few cells out (their general's army could
            # kill a stack parked next to it before deathtouch) and grow, then step in so the
            # stack becomes adjacent on turn 799 and touches on turn 800.
            act, gain, n = _gather_amount(S, at, est + 50, max_nodes=12)
            if act is not None and gain > 0:
                return act
            if t < PARAMS["STRIKE_T"]:
                # nothing left to pull in and deathtouch is far away: drop the plan so the
                # economy keeps running; a new strike is planned when it is affordable
                S.plan = None
            return None
    if own[nxt] == 2 and arm[at] - 1 <= arm[nxt]:
        act, gain, n = _gather_amount(S, at, arm[nxt] + 2 - arm[at], max_nodes=12)
        if act is not None and gain > 0:
            return act
        S.plan = None
        return None
    p["at"] = nxt
    return _mv(S, at, nxt)


# --- castle raids --------------------------------------------------------------
def _castle_est(S, c):
    """Estimated army on an enemy castle (exact if visible)."""
    if S.vis[c]:
        return S.arm[c]
    t = S.t
    born = S.castle_born.get(c, 0)
    if S.mem_t[c] >= born and S.mem_own[c] == 2:
        return S.mem_army[c] + (t - S.mem_t[c]) // 2 + 1
    return (t - born) // 2 + PARAMS["RAID_PAD"]


def _raid(S):
    """Take enemy castles that a nearby stack clearly beats: their income becomes ours."""
    if not S.en_castles or S.t < 60:
        return None
    own, arm, dist = S.own, S.arm, S.dist
    g = S.myG
    held = S.plan["at"] if S.plan is not None and S.plan.get("kind") == "strike" else None
    home = _home_castles(S)
    srcs = [i for i in S.mine if arm[i] >= PARAMS["RAID_MIN"] and i != g and i != held and i not in home]
    if not srcs:
        return None
    R = PARAMS["RAID_R"]
    pairs = []
    for c in S.en_castles:
        if own[c] == 1:
            continue
        est = _castle_est(S, c)
        dc = dist[c]
        for i in srcs:
            d = dc[i]
            if d <= R and arm[i] - 1 > est + d + PARAMS["RAID_MARGIN"]:
                pairs.append((d, -(arm[i] - est), i, c, est))
    if not pairs:
        return None
    pairs.sort()
    for d, _, i, c, est in pairs[:3]:
        path_army, path = _path_cost(S, i, c)
        if path is None or len(path) < 2 or len(path) - 1 > R + 2:
            continue
        if arm[i] - 1 - path_army <= est + PARAMS["RAID_MARGIN"] + (len(path) - 1) // 2:
            continue
        nxt = path[1]
        if own[nxt] == 2 and arm[i] - 1 <= arm[nxt]:
            continue
        _log(S.t, "raid castle", S.rc[c], "est", est, "from", S.rc[i], arm[i])
        return _mv(S, i, nxt)
    return None


# --- economy -----------------------------------------------------------------
def _castle(S):
    t = S.t
    if t >= PARAMS["CASTLE_LAST_T"]:
        return None
    if t < PARAMS["CASTLE_FIRST_T"]:
        # Mid-game moves are worth more as strike gathering than as castles (measured), unless
        # the enemy is out-building us: their castles are visible through fog, so keep parity.
        if not PARAMS["CASTLE_PARITY"] or len(S.my_castles) + PARAMS["CASTLE_PARITY_SLACK"] >= len(S.en_castles):
            return None
    if S.cplan is not None:
        return None
    own, arm, typ = S.own, S.arm, S.typ
    g = S.myG
    # sources: cells holding a big stack
    # while plenty of open land borders us, army and moves are worth more as land
    frontier = 0
    for i in S.mine:
        for n in S.adj[i]:
            if own[n] == 0:
                frontier += 1
    moat_only = frontier > PARAMS["CASTLE_FRONTIER_MAX"] and t < PARAMS["CASTLE_ANYWAY_T"]
    if moat_only and t < PARAMS["MOAT_CASTLE_T"]:
        return None
    reserve = _reserve(S)
    avail = {i: arm[i] for i in S.mine}
    gar_need = _keep(S)
    busy = set()
    if S.plan is not None:
        # never take a strike's stack or its launch cell
        for key in ("at", "launch"):
            if S.plan.get(key) is not None:
                busy.add(S.plan[key])
    busy |= _home_castles(S)
    sources = [i for i in S.mine if avail[i] >= PARAMS["STACK_MIN"] and i not in busy]
    if not sources:
        return None
    if g in sources and t < PARAMS["OPEN_T"] and arm[g] < 45:
        sources.remove(g)
    sources.sort(key=lambda i: -arm[i])
    sources = sources[:4]
    enemy_near = list(S.enemy_seen_cells)
    best = None
    bscore = PARAMS["CASTLE_MIN_SCORE"]
    horizon = PARAMS["CASTLE_HORIZON"]
    mc = PARAMS["CASTLE_MOVE_COST"]
    dr = PARAMS["CASTLE_DANGER_R"]
    dist = S.dist
    if g not in sources and gar_need > 0:
        half = arm[g] // 2
        if half >= PARAMS["STACK_MIN"] and arm[g] - half >= gar_need:
            sources.append(g)
    split_src = {}
    for s in sources:
        A = avail[s]
        if s == g and gar_need > 0:
            # the general keeps its garrison: send half
            A = arm[g] // 2
            split_src[g] = 1
        arrive = {s: A}
        depth = {s: 0}
        q = [s]
        for x in q:
            if depth[x] >= PARAMS["CASTLE_DEPTH"]:
                continue
            for y in S.adj[x]:
                if y in depth or own[y] == 2:
                    continue
                av = arrive[x] - 1 + (arm[y] if own[y] == 1 else 0)
                if av < 2:
                    continue
                depth[y] = depth[x] + 1
                arrive[y] = av
                q.append(y)
        for p in q:
            if typ[p] in (3, 4):
                continue
            cost = _build_cost(S, p)
            if arrive[p] < cost:
                continue
            if moat_only and S.dist[g][p] != 1:
                continue
            if s == g and gar_need > 0 and arm[g] - arm[g] // 2 < gar_need:
                continue
            k = depth[p]
            val = 0.5 * (horizon - t - k) - cost - mc * k
            if enemy_near:
                dmin = min(dist[p][e] for e in enemy_near) if len(enemy_near) < 80 else min(
                    dist[p][e] for e in enemy_near[::4])
                if dmin <= dr:
                    val -= (dr + 1 - dmin) * 25
            # keep castles reasonably close to home for defense and gathering
            val -= 0.8 * dist[g][p]
            # castles on our general's neighbours grow the deathtouch moat with no moves
            if t >= PARAMS["MOAT_CASTLE_T"] and dist[g][p] == 1:
                val += PARAMS["MOAT_CASTLE_BONUS"]
            if val > bscore:
                bscore = val
                best = (s, p)
    if best is None:
        return None
    s, p = best
    if s == p:
        r, c = S.rc[p]
        return [2, r, c, 0, 0]
    S.cplan = dict(start=t, ttl=30, at=s, site=p, split=split_src.get(s, 0))
    _log(t, "castle plan from", S.rc[s], "to", S.rc[p], "score", round(bscore))
    return _castle_step(S)


def _expand(S):
    t = S.t
    own, arm, typ, adj = S.own, S.arm, S.typ, S.adj
    g = S.myG
    tgt = _target(S)
    dist = S.dist
    dtg = dist[tgt] if tgt is not None else None
    dg = dist[g]
    vis = S.vis
    best = None
    bscore = None
    opening = t < PARAMS["OPEN_T"]
    # The general sends expansion runs while open land borders us and it has army
    # above its garrison (a half split keeps the garrison home).
    gn = _keep(S)
    frontier = 0
    for i in S.mine:
        for n in adj[i]:
            if own[n] == 0:
                frontier += 1
    g_split = 0
    g_run = False
    ag = arm[g]
    left = 50 - t % 50          # turns until the next land bonus (moves made now count for it)
    if gn == 0 and t < PARAMS["DEPLOY_LAST_T"] and left <= PARAMS["DEPLOY_WINDOW"] and ag >= 3 \
            and frontier > 0 and ag - 1 <= left + 2:
        # deploy before the bonus: every cell claimed now earns +1 at the bonus turn
        g_run = True
    elif opening and gn == 0:
        g_run = ag >= PARAMS["OPEN_STACK"]
    elif frontier >= PARAMS["RUN_OPEN_MIN"] and t < PARAMS["RUN_LAST_T"]:
        if gn == 0:
            g_run = ag >= PARAMS["RUN_STACK"]
        else:
            g_run = ag // 2 >= PARAMS["RUN_STACK"] and ag - ag // 2 >= gn
            g_split = 1
    if (PARAMS["HOME_CASTLE_MODE"] == 1 and PARAMS["HOME_CASTLE_N"] > 0 and PARAMS["HOME_CASTLE_T"] <= t
            < PARAMS["CASTLE_LAST_T"] and len(_home_castles(S)) < PARAMS["HOME_CASTLE_N"]):
        g_run = False          # the general is saving for its home castle
    held = S.plan["at"] if S.plan is not None and S.plan.get("kind") == "strike" else None
    # While their general is unknown, expansion doubles as scouting: claims nearer the candidate
    # region and claims that uncover candidate cells score higher.
    scouting = S.eg is None and PARAMS["SCOUT_FROM_T"] <= t < PARAMS["SCOUT_EXPAND_T"]
    sw = PARAMS["SCOUT_W"] if scouting else 0.25
    d0 = dtg[g] if dtg is not None else 0
    cands = S.cands if scouting else None
    nb8 = S.nb8

    def claim_score(n):
        o = own[n]
        sc = 10.0
        free = 0
        for m in adj[n]:
            if own[m] == 0:
                free += 1
        sc += 0.8 * free
        ng = 0
        for m in nb8[n]:
            if not vis[m]:
                ng += 1
                if cands is not None and m in cands:
                    sc += PARAMS["REVEAL_BONUS"]
        sc += 0.4 * ng
        if dtg is not None:
            sc += sw * (d0 - dtg[n])
        if dg[n] <= 2:
            sc += 1.5          # keep a ring around home
        return sc

    heads = []
    for s in S.mine:
        a = arm[s]
        if a < 2 or s == held:
            continue
        is_struct = s == g or s in S.my_castles
        if is_struct:
            # castles save their army; the general runs only under the rule above
            if not (s == g and g_run):
                continue
        if a >= 4:
            heads.append(s)
        for n in adj[s]:
            o = own[n]
            if o == 1:
                continue
            if o == 2:
                if a - 1 <= arm[n]:
                    continue
                sc = claim_score(n) + 4 + (40 if typ[n] == 3 else 0) + min(arm[n], 10) * 0.5
            else:
                sc = claim_score(n)
            # prefer spending small stacks, unless it is a run head
            if a == 2:
                sc += 1.0
            elif not is_struct and a >= 3:
                sc += 0.5 + min(a, 20) * 0.05
            if bscore is None or sc > bscore:
                bscore = sc
                best = (s, n)
    # A run stack may also walk through our own land to a better frontier point (toward the
    # candidate region): score = claim there minus a per-step cost.
    walk = None
    if heads and (scouting or best is None):
        heads.sort(key=lambda i: -arm[i])
        mp_ = PARAMS["WALK_PEN"]
        for h in heads[:4]:
            depth = {h: 0}
            first = {h: None}
            q = [h]
            for x in q:
                dx = depth[x]
                if dx >= 14:
                    continue
                for y in adj[x]:
                    if y in depth:
                        continue
                    if own[y] == 1:
                        depth[y] = dx + 1
                        first[y] = y if x == h else first[x]
                        q.append(y)
                    elif own[y] == 0 and dx >= 1:
                        sc = claim_score(y) - mp_ * dx + 0.5 + min(arm[h], 20) * 0.05
                        if bscore is None or sc > bscore:
                            bscore = sc
                            walk = (h, first[x])
                            best = None
    if walk is not None and best is None:
        h, nxt = walk
        return _mv(S, h, nxt, g_split if h == g else 0)
    if best is None:
        return None
    s, n = best
    return _mv(S, s, n, g_split if s == g else 0)


def _reposition(S, g_run=False, g_split=0):
    own, arm = S.own, S.arm
    g = S.myG
    held = S.plan["at"] if S.plan is not None and S.plan.get("kind") == "strike" else None
    heads = [i for i in S.mine if arm[i] >= 4 and i != g and i not in S.my_castles and i != held]
    if g_run:
        heads.append(g)
    if not heads:
        return None
    # multi-source BFS from neutral frontier cells
    front = [i for i in S.passable if own[i] == 0 and any(own[j] == 1 for j in S.adj[i])]
    if not front:
        return None
    d = {}
    q = []
    for f in front:
        d[f] = 0
        q.append(f)
    for x in q:
        for y in S.adj[x]:
            if y not in d and own[y] == 1:
                d[y] = d[x] + 1
                q.append(y)
    best = None
    bk = None
    for h in heads:
        if h not in d:
            continue
        k = (d[h], -arm[h])
        if bk is None or k < bk:
            bk, best = k, h
    if best is None:
        return None
    for y in S.adj[best]:
        if y in d and d[y] < d[best]:
            return _mv(S, best, y, g_split if best == g else 0)
    return None


def _idle(S):
    """Nothing better: gather army toward the general (future castle source)."""
    g = S.myG
    roots = [g]
    excl = None
    if S.plan is not None and S.plan.get("kind") == "strike" and S.plan.get("at") is not None:
        excl = {S.plan["at"]}
    act, gain, n = _gather(S, roots, PARAMS["GATHER_LAMBDA"], exclude=excl, frozen=_home_castles(S))
    if act is not None and gain >= 2:
        return act
    return None
