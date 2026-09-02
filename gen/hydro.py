"""Stage 2, hydrology: rivers and extra lakes.

Input : land/wet/rock masks [x, y], z[x, y] float heights, the Config and the
        pipeline's random generator.
Output: river centrelines (full-resolution (x, y) lists) and bool masks of the
        tiles they wet, to be OR-ed into the wet mask.

Rivers run on the z 0 plains from springs at the foot of the hills to the sea,
because Britannia's water works the way the shoreline stage builds it: the
water surface is always at -5 over sunk -15 beds, so a river cannot climb or
descend. Routing is Dijkstra over a cost raster at quarter resolution (see
gen/routing.py); it stays serial on purpose, since each accepted river extends
the target set of the next.
"""
import numpy as np
from . import accel as ndimage  # exact-preserving parallel scipy.ndimage
from .noise import fbm
from .routing import build_graph, path_to_nearest, smooth_polyline, rasterize_polyline

def plan_rivers(cfg, land, wet, z, rock, rng, n_rivers=10, min_len=120):
    """Up to `n_rivers` rivers of at least `min_len` tiles. Returns (centrelines, river
    wet mask). Springs are drawn at random from low ground far from the sea, spaced
    450 tiles apart; each river follows the cheapest route to existing water and stops
    where it meets it, widening downstream."""
    W, H = land.shape
    s = 4
    z4 = z[::s, ::s]; land4 = land[::s, ::s]; wet4 = wet[::s, ::s]; rock4 = rock[::s, ::s]
    # cost: only the plains are cheap, hills expensive, rock and open sea blocked; noise for meander
    noise = fbm(z4.shape, cfg.seed + 31, 4, 60.0)
    cost = 1.0 + 2.5 * (noise + 0.5) + np.clip(z4, 0, None) * 1.5
    cost[rock4] = np.inf
    cost[wet4] = 0.5   # reaching water is the goal; cheap to follow
    cost[~land4 & ~wet4] = np.inf
    g = build_graph(cost.astype(np.float32))
    # springs: low ground (z 0..16) off the rock, more than 120 tiles from the sea, spaced 450 apart
    dsea = ndimage.distance_transform_edt(~wet4) * s
    cand = land4 & (z4 >= 0) & (z4 <= 16) & ~rock4 & (dsea > 120)
    xs, ys = np.nonzero(cand)
    order = rng.permutation(len(xs))
    springs = []
    for k in order:
        p = (int(xs[k]), int(ys[k]))
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 > (450 / s) ** 2 for q in springs):
            springs.append(p)
        if len(springs) >= n_rivers * 3: break
    rivers = []
    river_wet = np.zeros((W, H), bool)
    target = wet4.copy()
    for sp in springs:
        if len(rivers) >= n_rivers: break
        path = path_to_nearest(g, z4.shape, sp, target)
        if path is None or len(path) * s < min_len: continue
        pts = smooth_polyline(path, 2)
        full = rasterize_polyline(pts, (W, H), scale=s)
        # stop where the river reaches existing water
        cut = []
        for p in full:
            cut.append(p)
            if wet[p] or river_wet[p]: break
        if len(cut) < min_len: continue
        rivers.append(cut)
        # the width grows downstream: half-width from ~1.7 to ~3.7 tiles, with jitter
        n = len(cut)
        for i, (x, y) in enumerate(cut):
            hw = 1.7 + 2 * (i / n) ** 1.2 + 0.6 * rng.random()
            r = int(np.ceil(hw))
            xx, yy = np.meshgrid(np.arange(max(0, x - r), min(W, x + r + 1)), np.arange(max(0, y - r), min(H, y + r + 1)), indexing="ij")
            river_wet[xx, yy] |= ((xx - x) ** 2 + (yy - y) ** 2) <= hw * hw
        # later rivers may end in this one
        for (x, y) in cut[::s]:
            target[x // s, y // s] = True
    river_wet &= land
    return rivers, river_wet

def plan_lakes(cfg, land, wet, z, rock, rng, n_lakes=6):
    """Up to `n_lakes` extra lakes on flat plains (z 0) at least 60 tiles from other
    water and 400 apart: noisy ellipses of 10-28 tiles radius. Returns their wet mask."""
    W, H = land.shape
    dw = ndimage.distance_transform_edt(~wet)
    cand = land & (z <= 0) & ~rock & (dw > 60)
    lakes = np.zeros((W, H), bool)
    xs, ys = np.nonzero(cand[::8, ::8]); order = rng.permutation(len(xs)); placed = []
    for k in order:
        if len(placed) >= n_lakes: break
        x, y = int(xs[k]) * 8, int(ys[k]) * 8
        if any((x - px) ** 2 + (y - py) ** 2 < 400 ** 2 for px, py in placed): continue
        rx, ry = rng.uniform(10, 28), rng.uniform(10, 28)
        r = int(max(rx, ry) * 1.6)
        x0, x1 = max(0, x - r), min(W, x + r + 1); y0, y1 = max(0, y - r), min(H, y + r + 1)
        xx, yy = np.meshgrid(np.arange(x0, x1), np.arange(y0, y1), indexing="ij")
        nz = fbm((x1 - x0, y1 - y0), cfg.seed + 500 + len(placed), 3, 14.0)
        blob = (((xx - x) / rx) ** 2 + ((yy - y) / ry) ** 2) + 0.8 * nz < 1.0
        blob &= cand[x0:x1, y0:y1]
        if blob.sum() < 80: continue
        lakes[x0:x1, y0:y1] |= blob
        placed.append((x, y))
    # clean: open, then fill holes
    lakes = ndimage.binary_opening(lakes, np.ones((3, 3)))
    lakes = ndimage.binary_fill_holes(lakes)
    return lakes
