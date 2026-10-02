"""Stdlib port of generals/agents/hunter_agent.py (test opponent).

Garrison the general, feed the surplus forward as one stack, kill the general on sight.
Goal: enemy general > nearest enemy land > farthest fog cell.
"""
GARRISON = 4


def _bfs(H, W, passable, sources):
    INF = H * W + 5
    d = [INF] * (H * W)
    q = []
    for s in sources:
        d[s] = 0
        q.append(s)
    for x in q:
        r, c = divmod(x, W)
        for y, ok in ((x - W, r > 0), (x + W, r < H - 1), (x - 1, c > 0), (x + 1, c < W - 1)):
            if ok and passable[y] and d[y] == INF:
                d[y] = d[x] + 1
                q.append(y)
    return d


def act(obs):
    H, W = obs["height"], obs["width"]
    typ = [v for row in obs["type"] for v in row]
    own = [v for row in obs["owner"] for v in row]
    a = [v for row in obs["army"] for v in row]
    N = H * W
    passable = [typ[i] not in (2, 5) and not (typ[i] == 3 and own[i] != 1) for i in range(N)]
    mine = [i for i in range(N) if own[i] == 1]
    gen = [i for i in mine if typ[i] == 4]
    if not gen:
        return [1, 0, 0, 0, 0]
    g = gen[0]
    from_gen = _bfs(H, W, passable, [g])
    INF = H * W + 5
    egen = [i for i in range(N) if own[i] == 2 and typ[i] == 4]
    enemy = [i for i in range(N) if own[i] == 2 and typ[i] != 3]
    if egen:
        goal = egen
    elif enemy:
        goal = enemy
    else:
        fog = [i for i in range(N) if typ[i] == 0 and passable[i] and from_gen[i] < INF]
        pool = fog or [i for i in range(N) if passable[i] and own[i] != 1 and from_gen[i] < INF]
        if not pool:
            return [1, 0, 0, 0, 0]
        m = max(from_gen[i] for i in pool)
        goal = [i for i in pool if from_gen[i] == m]
    to_goal = _bfs(H, W, passable, goal)

    def toward(x):
        r, c = divmod(x, W)
        best, bd, bv = None, None, to_goal[x]
        for d, (y, ok) in enumerate(((x - W, r > 0), (x + W, r < H - 1), (x - 1, c > 0), (x + 1, c < W - 1))):
            if ok and passable[y] and to_goal[y] < bv:
                bv, best, bd = to_goal[y], y, d
        return best, bd

    egen_army = sum(a[i] for i in egen)
    for x in mine:
        if a[x] > 1 and to_goal[x] == 1 and egen and a[x] - 1 > egen_army:
            y, d = toward(x)
            if y is not None:
                return [0, x // W, x % W, d, 0]
    if a[g] >= 2 * GARRISON:
        y, d = toward(g)
        if y is not None:
            return [0, g // W, g % W, d, 1]
    best, bd, ba = None, None, -1
    for x in mine:
        if x == g or a[x] <= 1:
            continue
        y, d = toward(x)
        if y is not None and a[x] > ba:
            ba, best, bd = a[x], x, d
    if best is not None:
        return [0, best // W, best % W, bd, 0]
    return [1, 0, 0, 0, 0]
