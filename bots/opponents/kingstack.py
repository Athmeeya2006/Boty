"""King-stack test opponent (independent design, stdlib only).

Economy: greedy expansion, castles built wherever a cell can afford one (usually next to the general).
Offense: every CYCLE turns it gathers its whole army into the general ("king stack") for GATHER turns,
then marches the stack at the enemy general if known, else at the nearest enemy land, else at the
farthest unexplored area. Defense: pulls the biggest nearby stacks home when a visible enemy stack near
the general beats it. Deathtouch: touches when adjacent after turn 800 and counter-attacks an adjacent
enemy stack from a third tile (falls back to the general itself, which is the common mistake).
"""
CYCLE = 110
GATHER = 45

_M = {}


def _bfs(adj, N, sources, block=None):
    INF = 10 ** 6
    d = [INF] * N
    q = list(sources)
    for s in q:
        d[s] = 0
    for x in q:
        for y in adj[x]:
            if d[y] == INF and (block is None or not block[y]):
                d[y] = d[x] + 1
                q.append(y)
    return d


def act(obs):
    try:
        return _act(obs)
    except Exception:
        return [1, 0, 0, 0, 0]


def _act(obs):
    H, W = obs["height"], obs["width"]
    N = H * W
    t = obs["turn"]
    typ = [v for row in obs["type"] for v in row]
    own = [v for row in obs["owner"] for v in row]
    a = [v for row in obs["army"] for v in row]
    if t == 0 or _M.get("hw") != (H, W):
        _M.clear()
        _M["hw"] = (H, W)
        wall = [x in (2, 5) for x in typ]
        adj = [[] for _ in range(N)]
        for i in range(N):
            if wall[i]:
                continue
            r, c = divmod(i, W)
            for y, ok in ((i - W, r > 0), (i + W, r < H - 1), (i - 1, c > 0), (i + 1, c < W - 1)):
                if ok and not wall[y]:
                    adj[i].append(y)
        _M["adj"] = adj
        _M["wall"] = wall
        _M["g"] = next(i for i in range(N) if typ[i] == 4 and own[i] == 1)
        _M["eg"] = None
        _M["seen"] = [False] * N
        _M["enemy_mem"] = set()
        _M["head"] = None
    adj, g = _M["adj"], _M["g"]
    for i in range(N):
        if typ[i] not in (0, 5):
            _M["seen"][i] = True
            if own[i] == 2:
                _M["enemy_mem"].add(i)
                if typ[i] == 4:
                    _M["eg"] = i
            else:
                _M["enemy_mem"].discard(i)
    eg = _M["eg"]
    mine = [i for i in range(N) if own[i] == 1]
    dg = _bfs(adj, N, [g])

    def mv(x, y, split=0):
        r, c = divmod(x, W)
        d = 0 if y == x - W else 1 if y == x + W else 2 if y == x - 1 else 3
        return [0, r, c, d, split]

    # 1. win now
    if eg is not None:
        for x in adj[eg]:
            if own[x] == 1 and a[x] >= 2 and (t >= 800 or (own[eg] == 2 and a[x] - 1 > a[eg])):
                return mv(x, eg)
    # 2. deathtouch defense
    if t >= 799:
        for x in adj[g]:
            if own[x] == 2 and a[x] >= 2:
                best = None
                for y in adj[x]:
                    if y != g and own[y] == 1 and a[y] >= a[x] and (best is None or a[y] > a[best]):
                        best = y
                if best is not None:
                    return mv(best, x)
                if a[g] >= 2:
                    return mv(g, x)
    # 3. defend against visible stacks near home
    threat = None
    for i in range(N):
        if own[i] == 2 and dg[i] <= 6 and a[i] > a[g] and (threat is None or a[i] > a[threat]):
            threat = i
    if threat is not None:
        best = None
        for i in mine:
            if i != g and a[i] >= 3 and dg[i] <= 5 and (best is None or a[i] > a[best]):
                best = i
        if best is not None:
            for y in adj[best]:
                if dg[y] < dg[best]:
                    return mv(best, y)
    # 4. castles: any cell that can pay, preferring near home
    structs = [i for i in mine if typ[i] in (3, 4)]
    if t < 700:
        best = None
        for i in mine:
            if typ[i] != 1 or a[i] < 35:
                continue
            r, c = divmod(i, W)
            cost = 35
            for sidx in structs:
                sr, sc = divmod(sidx, W)
                cost += max(0, 14 - 2 * (abs(sr - r) + abs(sc - c)))
            if a[i] >= cost and (best is None or dg[i] < dg[best]):
                best = i
        if best is not None:
            r, c = divmod(best, W)
            return [2, r, c, 0, 0]
    phase = t % CYCLE
    # 5. king stack march
    if t >= 100 and phase >= GATHER:
        head = _M.get("head")
        if head is None or own[head] != 1 or a[head] < 5:
            head = max(mine, key=lambda i: a[i])
        if a[head] >= 12:
            if eg is not None:
                goal = [eg]
            elif _M["enemy_mem"]:
                goal = list(_M["enemy_mem"])
            else:
                unseen = [i for i in range(N) if not _M["wall"][i] and not _M["seen"][i] and dg[i] < 10 ** 6]
                goal = unseen or [g]
                if unseen:
                    m = max(dg[i] for i in unseen)
                    goal = [i for i in unseen if dg[i] >= m - 3]
            to = _bfs(adj, N, goal)
            best = None
            for y in adj[head]:
                if to[y] < to[head] and (own[y] != 2 or a[head] - 1 > a[y]):
                    if best is None or (own[y] == 1 and a[y] > a[best]):
                        best = y
            if best is not None:
                _M["head"] = best
                return mv(head, best)
    # 6. gather phase: pull the farthest big cells toward the general
    if t >= 100 and phase < GATHER:
        best = None
        for i in mine:
            if i != g and a[i] >= 2 and typ[i] != 3:
                k = (dg[i], a[i])
                if best is None or k > best[0]:
                    best = (k, i)
        cast = [i for i in mine if typ[i] == 3 and a[i] >= 20]
        if cast and phase > GATHER // 2:
            i = max(cast, key=lambda x: a[x])
            for y in adj[i]:
                if dg[y] < dg[i] and own[y] == 1:
                    return mv(i, y)
        if best is not None:
            i = best[1]
            for y in adj[i]:
                if dg[y] < dg[i] and own[y] == 1:
                    return mv(i, y)
    # 7. expansion: any stack next to a neutral cell; the general sends runs of 10+
    best = None
    for i in mine:
        if a[i] < 2 or typ[i] == 3:
            continue
        if i == g and (a[i] < 10 or t >= 100):
            continue
        for y in adj[i]:
            if own[y] == 0 or (own[y] == 2 and a[i] - 1 > a[y]):
                k = (own[y] == 2, a[i])
                if best is None or k > best[0]:
                    best = (k, i, y)
    if best is not None:
        return mv(best[1], best[2])
    # walk stray stacks to the frontier
    front = [i for i in range(N) if own[i] == 0 and typ[i] == 1]
    if front:
        to = _bfs(adj, N, front)
        best = None
        for i in mine:
            if a[i] >= 4 and i != g and typ[i] != 3 and (best is None or a[i] > a[best]):
                best = i
        if best is not None:
            for y in adj[best]:
                if to[y] < to[best] and own[y] == 1:
                    return mv(best, y)
    return [1, 0, 0, 0, 0]
