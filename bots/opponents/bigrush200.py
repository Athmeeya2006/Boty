"""Rusher test opponent: hoards on the general, then drives the stack at the most likely
enemy general location (same spawn-rule inference our bot uses), feeding reinforcements.
"""
RUSH_T = 200
FEED = 60

_S = {}


def _bfs(adj, N, sources):
    INF = 10 ** 6
    d = [INF] * N
    q = list(sources)
    for s in q:
        d[s] = 0
    for x in q:
        for y in adj[x]:
            if d[y] == INF:
                d[y] = d[x] + 1
                q.append(y)
    return d


def act(obs):
    H, W = obs["height"], obs["width"]
    N = H * W
    t = obs["turn"]
    typ = [v for row in obs["type"] for v in row]
    own = [v for row in obs["owner"] for v in row]
    a = [v for row in obs["army"] for v in row]
    if t == 0 or _S.get("hw") != (H, W):
        _S.clear()
        _S["hw"] = (H, W)
        wall = [x in (2, 5) for x in typ]
        adj = [[] for _ in range(N)]
        for i in range(N):
            if wall[i]:
                continue
            r, c = divmod(i, W)
            for y, ok in ((i - W, r > 0), (i + W, r < H - 1), (i - 1, c > 0), (i + 1, c < W - 1)):
                if ok and not wall[y]:
                    adj[i].append(y)
        _S["adj"] = adj
        g = next(i for i in range(N) if typ[i] == 4 and own[i] == 1)
        _S["g"] = g
        dg = _bfs(adj, N, [g])

        def room(x):
            d = _bfs(adj, N, [x])
            return sum(1 for v in d if 0 < v <= 7)
        rg = room(g)
        far = [i for i in range(N) if not wall[i] and 17 <= dg[i] < 10 ** 6]
        cands = [i for i in far if abs(room(i) - rg) <= 5] or far
        _S["cands"] = set(cands)
    adj, g = _S["adj"], _S["g"]
    vis = [x not in (0, 5) for x in typ]
    egen = [i for i in range(N) if typ[i] == 4 and own[i] == 2]
    if egen:
        _S["cands"] = {egen[0]}
    else:
        c2 = {c for c in _S["cands"] if not vis[c]}
        if c2:
            _S["cands"] = c2
    goal = list(_S["cands"])
    to_goal = _bfs(adj, N, goal)

    def step(x):
        best, bv = None, to_goal[x]
        for y in adj[x]:
            if to_goal[y] < bv:
                bv, best = to_goal[y], y
        return best

    def mv(x, y, split=0):
        r, c = divmod(x, W)
        d = 0 if y == x - W else 1 if y == x + W else 2 if y == x - 1 else 3
        return [0, r, c, d, split]

    # kill on sight
    for e in egen:
        for x in adj[e]:
            if own[x] == 1 and a[x] - 1 > a[e]:
                return mv(x, e)
    # drive the biggest non-general stack
    stacks = [i for i in range(N) if own[i] == 1 and i != g and a[i] >= 6]
    if stacks:
        s = max(stacks, key=lambda i: a[i])
        y = step(s)
        if y is not None and (own[y] != 2 or a[s] - 1 > a[y]):
            return mv(s, y)
    if (t >= RUSH_T and a[g] >= FEED) or a[g] >= 2 * FEED + 10:
        y = step(g)
        if y is not None:
            return mv(g, y)
    # small claims
    for x in range(N):
        if own[x] == 1 and x != g and a[x] >= 2:
            for y in adj[x]:
                if own[y] == 0:
                    return mv(x, y)
    return [1, 0, 0, 0, 0]
