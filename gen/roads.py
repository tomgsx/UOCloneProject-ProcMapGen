"""Stage 3, towns and roads: town sites, the road network, cost-routed roads, road
beds, and the straight water crossings that later become bridges.

Input : land/wet/rock masks [x, y] bool, z[x, y] (int for planning, float for
        grading), material[x, y] (gen.materials codes), the Config and the
        pipeline's random generator.
Output: town sites as (x, y) tiles; roads as CENTRELINES, ordered lists of
        (x, y) tiles that are 8-connected; the road CORE mask (every tile the
        road surface covers); a graded z; and the DECK plans build_bridges()
        turns into planks and rails (gen/pipeline.py).

Vocabulary:

* CENTRELINE: the one-tile-wide path of a road. CORE: the centreline dilated to
  the road's width (rasterize_roads).
* WET RUN: a maximal stretch of a centreline over water. Wet runs separated by
  fewer than 6 dry tiles are treated as one CROSSING, so a braided channel gets
  one bridge, not several.
* CORRIDOR: the straight, axis-aligned replacement for a crossing - RUNUP + 2
  land tiles, the water, RUNUP + 2 land tiles - that straighten_crossings()
  splices into the road. The corridor ENDS are its first and last tiles.
* DECK: the tiles of the bridge itself, 5 wide, from the bank tile on one side
  to the bank tile on the other, grown outward (deck_extension) until all five
  tiles across each end stand on land. APRON: the APRON tiles beyond each deck
  end where the road keeps the deck's full 5-tile width. RUN-UP: the RUNUP
  straight, 3-wide land tiles beyond that, so road and deck read as one line.
* ANCHOR: a tile of the original road, backed off from the water, from which
  the APPROACH (a fresh land-only path to the corridor end) is routed.
  KEEP-OUT: the tiles beside the corridor an approach may not enter, so it can
  only leave the corridor end forward and never doubles back alongside the
  bridge. GUARD: the index of the previous corridor's end in the output, past
  which the next crossing may not cut back.
"""
import numpy as np
from . import accel as ndimage  # exact-preserving parallel scipy.ndimage
from scipy.sparse.csgraph import minimum_spanning_tree
from .noise import fbm
from .routing import build_graph, shortest_path, smooth_polyline, rasterize_polyline
from . import materials as M

def pick_towns(cfg, land, wet, z, material, rock, rng):
    """Town sites: flat grass/forest plains, ideally ~35 tiles from water, spaced by
    cfg.town_min_spacing. Returns up to cfg.towns sites as (x, y), best first."""
    W, H = land.shape
    s = 8
    flat = (z == 0)
    ok = land & flat & np.isin(material, [M.GRASS, M.FOREST]) & ~rock
    # a town needs a flat 41 x 41 area around it: erode the candidate mask
    ok_e = ndimage.binary_erosion(ok, np.ones((41, 41)))
    dw = ndimage.distance_transform_edt(~wet)
    score = np.where(ok_e, 1.0 / (1.0 + np.abs(dw - 35) / 40.0), 0)  # prefer ~35 tiles from water
    score = score * (0.7 + 0.6 * (fbm((W // s, H // s), cfg.seed + 41, 3, 40.0).repeat(s, 0).repeat(s, 1)[:W, :H] + 0.5))
    sc = score[::s, ::s]
    xs, ys = np.nonzero(sc > 0)
    order = np.argsort(-sc[xs, ys])
    towns = []
    for k in order:
        if len(towns) >= cfg.towns: break   # checked before the append, so a count of 0 places none
        x, y = int(xs[k]) * s, int(ys[k]) * s
        if all((x - tx) ** 2 + (y - ty) ** 2 >= cfg.town_min_spacing ** 2 for tx, ty in towns):
            towns.append((x, y))
    return towns

def plan_roads(cfg, land, wet, z, material, rock, towns, rng, extra_links=2):
    """The road network. Roads are routed at quarter resolution over a cost raster
    (plains cheap, slopes and swamp dear, rock and open sea blocked, narrow water
    crossable at a price), the towns are joined by a minimum spanning tree over their
    pairwise path costs plus `extra_links` shortcut links, and each link becomes a
    smoothed, wandered full-resolution centreline with straightened crossings.
    Returns (centrelines, edges as (i, j) town index pairs, stats)."""
    W, H = land.shape
    s = 4
    z4 = z[::s, ::s]; land4 = land[::s, ::s]; wet4 = wet[::s, ::s]; rock4 = rock[::s, ::s]; mat4 = material[::s, ::s]
    # slope at quarter resolution
    gx = np.abs(np.diff(z4, axis=0, append=z4[-1:])); gy = np.abs(np.diff(z4, axis=1, append=z4[:, -1:]))
    slope = np.maximum(gx, gy)
    noise = fbm(z4.shape, cfg.seed + 51, 4, 30.0)
    cost = 1.0 + 3.5 * (noise + 0.5) + 1.5 * slope + np.where(mat4 == M.FOREST, 0.6, 0) + np.where(mat4 == M.SWAMP, 6.0, 0) \
        + np.where(mat4 == M.JUNGLE, 1.0, 0) + np.where(mat4 == M.SNOW, 0.5, 0)
    # water: crossing is allowed but expensive (it becomes a bridge), and impossible
    # for wide water (more than 3 quarter-res tiles from land)
    dland4 = ndimage.distance_transform_edt(wet4)
    cost = np.where(wet4, np.where(dland4 <= 3, 14.0, np.inf), cost)
    cost[rock4] = np.inf
    cost[~land4 & ~wet4] = np.inf
    # keep a little off the coast ring
    dw4 = ndimage.distance_transform_edt(~wet4)
    cost += np.where((dw4 < 3) & ~wet4, 3.0, 0)
    g = build_graph(cost.astype(np.float32))
    pts4 = [(x // s, y // s) for x, y in towns]
    n = len(pts4)
    # pairwise path costs: one Dijkstra from each town
    from .routing import dist_from
    D = np.full((n, n), np.inf)
    for i, p in enumerate(pts4):
        d, _ = dist_from(g, z4.shape, p)
        for j, q in enumerate(pts4):
            D[i, j] = d[q]
    Dm = np.where(np.isfinite(D), D, 0)
    mst = minimum_spanning_tree(Dm).toarray()
    edges = set()
    for i in range(n):
        for j in range(n):
            if mst[i, j] > 0: edges.add((min(i, j), max(i, j)))
    # extra links: the cheapest pairs the tree does not already join
    cand = []
    for i in range(n):
        for j in range(i + 1, n):
            if (i, j) in edges or not np.isfinite(D[i, j]): continue
            cand.append((D[i, j], i, j))
    cand.sort()
    for _, i, j in cand[:extra_links]:
        edges.add((i, j))
    wfields = (fbm((W // 4, H // 4), cfg.seed + 61, 3, 70.0 / 4), fbm((W // 4, H // 4), cfg.seed + 62, 3, 24.0 / 4))
    roads = []
    stats = {"rerouted": 0, "dropped": 0}
    shore = shore_mask(wet)
    g_dry = None   # the same cost field with water impassable, built only if a crossing fails
    for i, j in sorted(edges):
        path = shortest_path(g, z4.shape, pts4[i], pts4[j])
        if path is None: continue
        pts = smooth_polyline(path, 2) * s
        pts = wander(pts, rng, fields=wfields)
        full = rasterize_polyline(pts, (W, H), scale=1.0)
        full, ok = straighten_crossings(full, wet, blocked=rock, shore=shore)
        if not ok:
            # A crossing that cannot be made straight is not bridged at all: try the same link
            # over land only, and drop it if the towns are separated by uncrossable water.
            if g_dry is None:
                g_dry = build_graph(np.where(wet4, np.inf, cost).astype(np.float32))
            path = shortest_path(g_dry, z4.shape, pts4[i], pts4[j])
            if path is not None:
                pts = wander(smooth_polyline(path, 2) * s, rng, fields=wfields)
                full, ok = straighten_crossings(rasterize_polyline(pts, (W, H), scale=1.0), wet, blocked=rock, shore=shore)
            if path is None or not ok:
                stats["dropped"] += 1
                continue
            stats["rerouted"] += 1
        roads.append(full)
    return roads, sorted(edges), stats

def rasterize_roads(roads, shape, width=3, rng=None, wet=None):
    """The road core mask and the centreline mask. `width` is the road's width in
    tiles at its narrowest - about a quarter of its length, by the noise below - and
    it runs two tiles wider elsewhere (so width 3 gives a road that is 3 or 5 wide)."""
    W, H = shape
    core = np.zeros(shape, bool)
    centre = np.zeros(shape, bool)
    for path in roads:
        for (x, y) in path: centre[x, y] = True
    # width: dilate the centreline with a disc whose radius drifts with noise. The three
    # radii were tuned for width 3 (1.5 = the 3-wide band on ~26 % of the length, 2 and
    # 2.5 = 5 wide, the latter with shoulders on bends); any other width shifts all three
    # by the same amount.
    d = ndimage.distance_transform_edt(~centre)
    wn = fbm(shape, 77, 2, 60.0) if rng is not None else np.zeros(shape, np.float32)
    r = np.where(wn > 0.15, 2.5, np.where(wn < -0.15, 1.5, 2.0))
    widen = (width - 3) / 2.0
    if widen:
        r = r + widen
    if wet is not None:
        # a bridge walkway is 3 wide; the road holds that width through the run-ups so
        # road and walkway read as one straight corridor
        k = 2 * BRIDGE_REACH + 1
        zone = ndimage.binary_dilation(centre & wet, np.ones((k, k)))
        r = np.where(zone, 1.5, r)
    core = d <= r
    return core, centre

def grade_roads(z, core, centre, roads, blend_radius=4, max_step=2):
    """Flatten the road bed. Along each road the bed z is the smoothed terrain profile
    limited to |dz| <= max_step per tile; road tiles take the bed z, and terrain within
    blend_radius blends toward it. Modifies z (float) in place and returns it."""
    W, H = z.shape
    bed = np.full(z.shape, np.nan, np.float32)
    for path in roads:
        zs = np.array([z[x, y] for x, y in path], np.float32)
        # moving average (window 15), then slope-limit forward and backward
        k = 15
        if len(zs) >= k:
            zs = np.convolve(np.pad(zs, (k // 2, k // 2), mode="edge"), np.ones(k) / k, mode="valid")
        for i in range(1, len(zs)): zs[i] = np.clip(zs[i], zs[i - 1] - max_step, zs[i - 1] + max_step)
        for i in range(len(zs) - 2, -1, -1): zs[i] = np.clip(zs[i], zs[i + 1] - max_step, zs[i + 1] + max_step)
        for (x, y), v in zip(path, zs): bed[x, y] = v
    has = ~np.isnan(bed)
    idx = ndimage.distance_transform_edt(~has, return_distances=False, return_indices=True)
    near = bed[idx[0], idx[1]]
    d = ndimage.distance_transform_edt(~core)
    w = np.clip(1.0 - d / blend_radius, 0, 1)
    z[:] = np.where(core, near, z * (1 - w) + near * w)
    return z


RUNUP = 4   # straight land tiles a road keeps on each side of a bridge
# How far a bridge can reach past the centre-line bank: the deck may grow up to RUNUP+2 tiles
# (deck_extension) and the straight corridor runs RUNUP+2 beyond that. The road holds deck
# width, and the approach anchors sit, this far from the water.
BRIDGE_REACH = 2 * (RUNUP + 2)
AHEAD_MIN = 3    # an approach anchor sits at least this far beyond its corridor end, outward
APRON = 2        # tiles beyond each deck end where the road is the deck's full 5-tile width

def _local_path(wet, a, b, margin=45, blocked=None, avoid=()):
    """Shortest land-only 8-connected path between a and b inside a local window (None if unreachable).
    `avoid`: extra (x,y) tiles treated as impassable (the endpoints themselves are always allowed)."""
    from .routing import build_graph, shortest_path
    W, H = wet.shape
    x0 = max(0, min(a[0], b[0]) - margin); x1 = min(W, max(a[0], b[0]) + margin + 1)
    y0 = max(0, min(a[1], b[1]) - margin); y1 = min(H, max(a[1], b[1]) + margin + 1)
    sub = wet[x0:x1, y0:y1]
    if blocked is not None: sub = sub | blocked[x0:x1, y0:y1]
    cost = np.where(sub, np.inf, 1.0).astype(np.float32)
    for (x, y) in avoid:
        if x0 <= x < x1 and y0 <= y < y1 and (x, y) not in (tuple(a), tuple(b)):
            cost[x - x0, y - y0] = np.inf
    g = build_graph(cost)
    p = shortest_path(g, cost.shape, (a[0] - x0, a[1] - y0), (b[0] - x0, b[1] - y0))
    if p is None: return None
    return [(x + x0, y + y0) for x, y in p]

def shore_mask(wet):
    """Water plus every dry tile touching it: the tiles that carry dropoff art and sunken bank z."""
    return ndimage.binary_dilation(wet, np.ones((3, 3)))

def deck_extension(shore, x, y, ew, step, limit=RUNUP + 2):
    """A deck is 5 wide, and a jagged bank can leave its outer columns over water - or on the
    sunken bank tile beside it, which shows as a hole next to the corner post. From the
    centre-line bank tile (x, y), count how many tiles the deck must extend outward along the
    axis (`step` = +1/-1) until the whole 5-wide band is clear of `shore` (water and anything
    touching it). 0 = already clear; None = not achievable within `limit`."""
    W, H = shore.shape
    for n in range(limit + 1):
        px, py = (x + step * n, y) if ew else (x, y + step * n)
        if not (2 <= px < W - 2 and 2 <= py < H - 2): return None
        band = shore[px, py - 2:py + 3] if ew else shore[px - 2:px + 3, py]
        if not band.any(): return n
    return None

def plan_decks(roads, wet):
    """The bridge decks the roads imply: for every axis-aligned wet run of a road (wet runs
    separated by < 6 dry tiles merge), the deck tiles from bank to bank grown by deck_extension
    until the whole 5-wide band is on land. Returns [(seg, ew)] with seg sorted along the axis;
    crooked runs are counted separately so the caller can refuse and log them."""
    W, H = wet.shape
    shore = shore_mask(wet)
    decks, crooked = [], 0
    for path in roads:
        n = len(path); i = 0
        while i < n:
            if not wet[path[i]]: i += 1; continue
            j = i
            while j < n and wet[path[j]]: j += 1
            while j < n:   # merge with following wet runs separated by short dry gaps
                k = j
                while k < n and not wet[path[k]] and k - j < 6: k += 1
                if k < n and wet[path[k]] and k - j < 6:
                    j = k
                    while j < n and wet[path[j]]: j += 1
                else: break
            if i == 0 or j >= n: i = j; continue
            (ax, ay), (bx, by) = path[i - 1], path[j]
            seg = path[i - 1:j + 1]
            ew = all(y == ay for _, y in seg)
            if not ew and not all(x == ax for x, _ in seg):
                crooked += 1; i = j; continue
            def colinear(p): return (p[1] == ay) if ew else (p[0] == ax)
            sa = (ax - path[i][0], ay - path[i][1])
            ea = deck_extension(shore, ax, ay, ew, sa[0] if ew else sa[1]) or 0
            head = [path[i - 1 - k] for k in range(1, ea + 1) if i - 1 - k >= 0 and colinear(path[i - 1 - k])]
            sb = (bx - path[j - 1][0], by - path[j - 1][1])
            eb = deck_extension(shore, bx, by, ew, sb[0] if ew else sb[1]) or 0
            tail = [path[j + k] for k in range(1, eb + 1) if j + k < n and colinear(path[j + k])]
            decks.append((sorted(head[::-1] + seg + tail), ew))
            i = j
    return decks, crooked

def deck_apron(decks, shape):
    """Road tiles the deck's full 5-tile width for APRON tiles beyond each deck end: the road
    meets the bridge at the post columns, then narrows to the 3-wide run-up."""
    W, H = shape
    apron = np.zeros(shape, bool)
    for seg, ew in decks:
        for end, step in ((seg[0], -1), (seg[-1], +1)):
            for k in range(1, APRON + 1):
                for o in (-2, -1, 0, 1, 2):
                    px, py = (end[0] + step * k, end[1] + o) if ew else (end[0] + o, end[1] + step * k)
                    if 0 <= px < W and 0 <= py < H: apron[px, py] = True
    return apron

def _smooth_approach(app, wet, blocked, keepout, corridor_end="last", hold=4):
    """A re-routed approach is a raw grid path (straight legs and 45-degree bends); the original
    roads were corner-cut smooth, so Chaikin-smooth it like them. The `hold` tiles at the
    corridor end stay as routed (a smoothed curve there drifts into the keep-out and would be
    rejected wholesale); the rest is thinned to every 4th tile, smoothed, and re-rasterised,
    unless a smoothed tile would land on water, rock or the keep-out, in which case the raw
    approach is kept."""
    if len(app) < hold + 8: return app
    if corridor_end == "last":
        body, tail = app[:len(app) - hold + 1], app[len(app) - hold + 1:]
    else:
        tail, body = app[:hold], app[hold - 1:]
    coarse = list(body[::4])
    if coarse[-1] != tuple(body[-1]): coarse.append(tuple(body[-1]))
    pts = smooth_polyline(np.asarray(coarse, float), 3)
    pts[0] = body[0]; pts[-1] = body[-1]
    sm = rasterize_polyline(pts, wet.shape, scale=1.0)
    if not sm or sm[0] != tuple(body[0]) or sm[-1] != tuple(body[-1]): return app
    for q in sm[1:-1]:
        if wet[q] or (blocked is not None and blocked[q]) or q in keepout: return app
    return (sm + list(tail)) if corridor_end == "last" else (list(tail) + sm[1:])

def _best_crossing(wet, a, b, max_len=60, search=25, runup=RUNUP, blocked=None, mid=None, shore=None):
    """Shortest straight axis-aligned water crossing near the midpoint of a-b, with `runup` straight land
    tiles beyond each bank. Returns the tiles from the near run-up end to the far run-up end (inclusive),
    or None when no row/column within `search` of the midpoint has a crossing <= max_len whose run-ups
    are on land (and off `blocked`). The corridor carries two extra straight tiles so the approach's
    3-wide band, from whatever direction it joins the corridor end, reaches none of the `runup` tiles."""
    W, H = wet.shape
    bad = wet if blocked is None else (wet | blocked)
    if shore is None: shore = shore_mask(wet)
    runup = runup + 2
    mx, my = mid if mid is not None else ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)
    best = None
    for ew in (True, False):
        for off in range(-search, search + 1):
            if ew:
                y = my + off
                if not (0 <= y < H): continue
                # find the wet span containing/nearest the midpoint on this row
                x = mx
                if not wet[x, y]:
                    # walk toward b until wet
                    stp = 1 if b[0] >= a[0] else -1
                    while 0 <= x < W and not wet[x, y] and abs(x - mx) < max_len: x += stp
                    if not (0 <= x < W) or not wet[x, y]: continue
                # the span joins channels separated by < 6 dry tiles, exactly as the wet runs of a
                # road are merged into one crossing - otherwise the deck (built from the merged run)
                # grows past the corridor the crossing reserved and eats the run-up
                xl = x
                while xl - 1 >= 0 and wet[max(0, xl - 6):xl, y].any(): xl -= 1
                xr = x
                while xr + 1 < W and wet[xr + 1:min(W, xr + 7), y].any(): xr += 1
                L = xr - xl + 1
                if L > max_len: continue
                # the deck may need to grow past the centre-line bank until its 5-wide band is dry;
                # the straight run-up is guaranteed beyond THAT end
                el = deck_extension(shore, xl - 1, y, True, -1); er = deck_extension(shore, xr + 1, y, True, +1)
                if el is None or er is None: continue
                lo, hi = xl - 1 - el - runup, xr + 1 + er + runup
                if lo < 0 or hi >= W: continue
                if bad[lo:xl, y].any() or bad[xr + 1:hi + 1, y].any(): continue
                seg = [(xx, y) for xx in range(lo, hi + 1)]
            else:
                x = mx + off
                if not (0 <= x < W): continue
                y = my
                if not wet[x, y]:
                    stp = 1 if b[1] >= a[1] else -1
                    while 0 <= y < H and not wet[x, y] and abs(y - my) < max_len: y += stp
                    if not (0 <= y < H) or not wet[x, y]: continue
                yl = y
                while yl - 1 >= 0 and wet[x, max(0, yl - 6):yl].any(): yl -= 1
                yr = y
                while yr + 1 < H and wet[x, yr + 1:min(H, yr + 7)].any(): yr += 1
                L = yr - yl + 1
                if L > max_len: continue
                el = deck_extension(shore, x, yl - 1, False, -1); er = deck_extension(shore, x, yr + 1, False, +1)
                if el is None or er is None: continue
                lo, hi = yl - 1 - el - runup, yr + 1 + er + runup
                if lo < 0 or hi >= H: continue
                if bad[x, lo:yl].any() or bad[x, yr + 1:hi + 1].any(): continue
                seg = [(x, yy) for yy in range(lo, hi + 1)]
            score = L + 0.15 * abs(off)
            # a crossing should run the way the road travels; the perpendicular orientation is a
            # fallback only (it strands the approaches on the wrong bank)
            if ew != (abs(b[0] - a[0]) >= abs(b[1] - a[1])): score += 30
            if best is None or score < best[0]: best = (score, seg)
    return best[1] if best else None

def straighten_crossings(path, wet, max_len=60, blocked=None, shore=None):
    """Replace every water crossing of a road path by: land approach -> straight land run-up -> one straight
    axis-aligned crossing -> straight land run-up -> land approach (approaches are re-routed over land).
    Returns (path, ok). ok is False when some crossing could not be straightened; the returned path then
    still contains that raw wet run and the caller must reroute or drop the road - a raw diagonal crossing
    is never bridged, because a bridge built over it would be a ladder of offset planks."""
    n = len(path); out = []; i = 0; ok = True
    if shore is None: shore = shore_mask(wet)
    guard = 0   # index in `out` of the previous crossing's corridor end: never cut back past it
    while i < n:
        if not wet[path[i]] or i == 0:
            out.append(path[i]); i += 1; continue
        j = i
        while j < n and wet[path[j]]: j += 1
        while j < n:   # merge following wet runs separated by < 6 dry tiles
            k = j
            while k < n and not wet[path[k]] and k - j < 6: k += 1
            if k < n and wet[path[k]] and k - j < 6:
                j = k
                while j < n and wet[path[j]]: j += 1
            else: break
        if j >= n: out.extend(path[i:]); ok = False; break
        # The approaches re-route from anchors backed off the water by RUNUP+2 tiles along the
        # original path (never through another wet run). Anchoring on the bank tile itself would
        # leave the old diagonal approach in the centreline right up to the water, so the road
        # core would widen and skew against the deck.
        back = 0
        while back < BRIDGE_REACH and len(out) - 2 - back >= guard and not wet[out[-2 - back]]: back += 1
        fwd = 0
        while fwd < BRIDGE_REACH and j + 1 + fwd < n and not wet[path[j + 1 + fwd]]: fwd += 1
        a = out[-1 - back]; b = path[j + fwd]
        # the crossing is searched around the midpoint of anchors RUNUP+2 tiles off the water,
        # which is where a hand-placed bridge sits; the deeper anchors above only decide where
        # the approaches are re-routed from
        a6 = out[-1 - min(back, RUNUP + 2)]; b6 = path[j + min(fwd, RUNUP + 2)]
        mid = ((a6[0] + b6[0]) // 2, (a6[1] + b6[1]) // 2)
        # A wandered road that merely clips a river bend leaves both anchors on the same bank; a
        # bridge there is pointless, and its far end may even be unreachable, which loses the
        # whole link. If a land route between the anchors exists at reasonable length, take it.
        orig_len = back + (j - i + 1) + fwd
        direct = _local_path(wet, a, b, blocked=blocked)
        if direct is not None and len(direct) <= 1.5 * orig_len + 8:
            del out[len(out) - back:]
            out.extend(direct[1:])
            i = j + fwd + 1
            continue
        seg = _best_crossing(wet, a, b, max_len, blocked=blocked, mid=mid, shore=shore)
        if seg is None:
            out.extend(path[i:j + 1]); i = j + 1; ok = False; continue
        # orient the segment so that BOTH anchors lie ahead of their corridor ends (a long crossing
        # over braided water can put the near anchor beside either end, and a backwards corridor
        # strands both approaches inside the keep-out, which also loses the link)
        def outward_score(sg):
            e0 = (sg[0][0] - sg[1][0], sg[0][1] - sg[1][1]); e1 = (sg[-1][0] - sg[-2][0], sg[-1][1] - sg[-2][1])
            return ((a[0] - sg[0][0]) * e0[0] + (a[1] - sg[0][1]) * e0[1]
                    + (b[0] - sg[-1][0]) * e1[0] + (b[1] - sg[-1][1]) * e1[1])
        if outward_score(seg[::-1]) > outward_score(seg): seg = seg[::-1]
        # An anchor behind the corridor end makes the approach double back in a V: walk each
        # anchor further along the original road until it lies AHEAD_MIN tiles beyond its
        # corridor end in the outward direction (never past water).
        d0 = (seg[0][0] - seg[1][0], seg[0][1] - seg[1][1]); d1 = (seg[-1][0] - seg[-2][0], seg[-1][1] - seg[-2][1])
        def ahead(p, s, d): return (p[0] - s[0]) * d[0] + (p[1] - s[1]) * d[1]
        back12, fwd12 = back, fwd
        while ahead(out[-1 - back], seg[0], d0) < AHEAD_MIN and back < 3 * BRIDGE_REACH \
                and len(out) - 2 - back >= guard and not wet[out[-2 - back]]:
            back += 1
        while ahead(path[j + fwd], seg[-1], d1) < AHEAD_MIN and fwd < 3 * BRIDGE_REACH \
                and j + 1 + fwd < n and not wet[path[j + 1 + fwd]]:
            fwd += 1
        # An approach may leave a corridor end only forward: everything within 2 tiles of the deck
        # and its checked run-up is off limits, so a road whose original line turned right after the
        # river cannot double back alongside the bridge. The two outermost corridor tiles at each
        # end stay free so the approach can depart.
        keepout = {(x + dx, y + dy) for (x, y) in seg[2:-2] for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)}
        # Where the old road zig-zags up to the river, the approach should start further back and
        # come in as one straight leg. Try far anchors first and keep the farthest that lies ahead
        # and is reachable by a nearly straight land path; otherwise the "ahead" anchor, then the
        # near one (a far anchor beyond a river loop the local window cannot route around must not
        # lose the link).
        def straight(pth, p, q):
            return pth is not None and len(pth) <= 1.3 * max(abs(p[0] - q[0]), abs(p[1] - q[1])) + 3
        app1 = None
        for bk in [d for d in (40, 32, 24, 16) if d > back] + ([back, back12] if back != back12 else [back]):
            if len(out) - 1 - bk < guard or any(wet[out[-1 - k]] for k in range(back, bk + 1)): continue
            cand = out[-1 - bk]
            if bk > back and ahead(cand, seg[0], d0) < AHEAD_MIN: continue
            pth = _local_path(wet, cand, seg[0], blocked=blocked, avoid=keepout)
            if pth is not None and (bk <= back or straight(pth, cand, seg[0])):
                app1 = pth; back = bk; break
        app2 = None
        for fw in [d for d in (40, 32, 24, 16) if d > fwd] + ([fwd, fwd12] if fwd != fwd12 else [fwd]):
            if j + fw >= n or any(wet[path[j + k]] for k in range(fwd, fw + 1)): continue
            cand = path[j + fw]
            if fw > fwd and ahead(cand, seg[-1], d1) < AHEAD_MIN: continue
            pth = _local_path(wet, seg[-1], cand, blocked=blocked, avoid=keepout)
            if pth is not None and (fw <= fwd or straight(pth, seg[-1], cand)):
                app2 = pth; fwd = fw; break
        if app1 is None:   # last resort: the near anchor without the keep-out
            back = back12; app1 = _local_path(wet, out[-1 - back], seg[0], blocked=blocked)
        if app2 is None:
            fwd = fwd12; app2 = _local_path(wet, seg[-1], path[j + fwd], blocked=blocked)
        if app1 is None or app2 is None:
            out.extend(path[i:j + 1]); i = j + 1; ok = False; continue
        # smooth each approach TOGETHER with the last JOINT tiles of the original road it hangs
        # off, so the corner at the junction rounds as well (one curve, not two legs); the joint
        # tiles must be dry and not already part of another crossing
        JOINT = 8
        pre_n = 0
        while pre_n < JOINT and len(out) - 2 - back - pre_n >= guard and not wet[out[-2 - back - pre_n]]: pre_n += 1
        pre = out[len(out) - 1 - back - pre_n:len(out) - 1 - back]
        post_n = 0
        while post_n < JOINT and j + fwd + 1 + post_n < n and not wet[path[j + fwd + 1 + post_n]]: post_n += 1
        post = path[j + fwd + 1:j + fwd + 1 + post_n]
        # a smoothed curve stays 3 tiles clear of the deck and checked run-up (one tile more than
        # the routing keep-out): a road passing 3 tiles from a run-up reads as a stray parallel lane
        keepout3 = {(x + dx, y + dy) for (x, y) in seg[2:-2] for dx in range(-3, 4) for dy in range(-3, 4)}
        app1 = _smooth_approach(list(pre) + list(app1), wet, blocked, keepout3, corridor_end="last")
        app2 = _smooth_approach(list(app2) + list(post), wet, blocked, keepout3, corridor_end="first")
        del out[len(out) - back - pre_n:]
        out.extend(app1[1:] if pre_n == 0 else app1)
        out.extend(seg[1:])
        guard = len(out) - 1
        out.extend(app2[1:])
        i = j + fwd + 1 + post_n
    res = [out[0]]
    for p_ in out[1:]:
        if p_ != res[-1]: res.append(p_)
    return res, ok

def wander(pts, rng, amp=(3.0, 1.5), wl=(70.0, 24.0), fields=None):
    """Gentle perpendicular wander. The offset is a function of POSITION (shared noise fields), so roads that
    share a segment (e.g. a common river crossing) receive identical offsets and stay merged."""
    pts = np.asarray(pts, float)
    if len(pts) < 3: return pts
    d = np.diff(pts, axis=0); seg = np.hypot(d[:, 0], d[:, 1]); sdist = np.concatenate([[0], np.cumsum(seg)])
    n = max(3, int(sdist[-1] / 4))
    ss = np.linspace(0, sdist[-1], n)
    x = np.interp(ss, sdist, pts[:, 0]); y = np.interp(ss, sdist, pts[:, 1])
    tx = np.gradient(x); ty = np.gradient(y); ln = np.hypot(tx, ty) + 1e-6; nx, ny = -ty / ln, tx / ln
    off = np.zeros(n)
    if fields is not None:
        for a, f in zip(amp, fields):
            fx = np.clip((x / 4).astype(int), 0, f.shape[0] - 1); fy = np.clip((y / 4).astype(int), 0, f.shape[1] - 1)
            off += a * 2.0 * f[fx, fy]
    else:
        for a, w in zip(amp, wl):
            off += a * np.sin(2 * np.pi * ss / w + rng.uniform(0, 2 * np.pi))
    fade = np.clip(np.minimum(ss, sdist[-1] - ss) / 30.0, 0, 1)
    off *= fade
    return np.stack([x + nx * off, y + ny * off], 1)
