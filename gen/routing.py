"""Shortest paths on a cost raster, used by the river and road stages.

A raster cost[x, y] >= 0 (np.inf = blocked) becomes a sparse 8-connected graph
whose nodes are tiles (index x * H + y) and whose edge weight is the mean of the
two tiles' costs times the step length (1 or sqrt 2). Paths come back as ordered
(x, y) lists; smooth_polyline and rasterize_polyline turn a coarse path into a
smooth full-resolution centreline.

scipy's Dijkstra holds the GIL, so this module is the serial part of the
generator; callers keep the rasters at quarter resolution to make it cheap.
"""
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

def build_graph(cost):
    """The 8-connected graph of a cost raster (csr matrix, symmetric). Edges into or
    out of blocked (inf) tiles are omitted."""
    W, H = cost.shape
    n = W * H
    idx = np.arange(n).reshape(W, H)
    rows, cols, vals = [], [], []
    for dx, dy, ln in ((1, 0, 1.0), (0, 1, 1.0), (1, 1, 1.41421356), (1, -1, 1.41421356)):
        a = idx[max(0, -dx):W - max(0, dx), max(0, -dy):H - max(0, dy)]
        b = idx[max(0, dx):W - max(0, -dx), max(0, dy):H - max(0, -dy)]
        ca = cost[max(0, -dx):W - max(0, dx), max(0, -dy):H - max(0, dy)]
        cb = cost[max(0, dx):W - max(0, -dx), max(0, dy):H - max(0, -dy)]
        w = (ca + cb) * 0.5 * ln
        ok = np.isfinite(w)
        rows.append(a[ok].ravel()); cols.append(b[ok].ravel()); vals.append(w[ok].ravel())
    r = np.concatenate(rows); c = np.concatenate(cols); v = np.concatenate(vals)
    g = coo_matrix((np.concatenate([v, v]), (np.concatenate([r, c]), np.concatenate([c, r]))), shape=(n, n)).tocsr()
    return g

def shortest_path(graph, shape, src, dst):
    """The cheapest path from src to dst as a list of (x, y) including both ends, or
    None when dst is unreachable."""
    W, H = shape
    s = src[0] * H + src[1]; t = dst[0] * H + dst[1]
    dist, pred = dijkstra(graph, directed=False, indices=s, return_predecessors=True, limit=np.inf)
    if not np.isfinite(dist[t]): return None
    path = []; cur = t
    while cur != s and cur >= 0:
        path.append((cur // H, cur % H)); cur = pred[cur]
    path.append(src); path.reverse()
    return path

def dist_from(graph, shape, src):
    """Cost to every tile from src (float [W, H], inf where unreachable) and the
    predecessor array for walking paths back."""
    W, H = shape
    d, pred = dijkstra(graph, directed=False, indices=src[0] * H + src[1], return_predecessors=True)
    return d.reshape(W, H), pred

def path_to_nearest(graph, shape, src, target_mask):
    """The cheapest path from src to the nearest tile of target_mask (None if none is reachable)."""
    W, H = shape
    d, pred = dist_from(graph, shape, src)
    dd = np.where(target_mask, d, np.inf)
    if not np.isfinite(dd.min()): return None
    t = int(np.argmin(dd)); path = []; cur = t; s = src[0] * H + src[1]
    while cur != s and cur >= 0:
        path.append((cur // H, cur % H)); cur = pred[cur]
    path.append(src); path.reverse()
    return path

def smooth_polyline(pts, iters=3):
    """Chaikin corner cutting: each pass replaces every segment by its 1/4 and 3/4
    points, rounding the corners while keeping the end points."""
    p = np.asarray(pts, float)
    for _ in range(iters):
        q = p[:-1] * 0.75 + p[1:] * 0.25; r = p[:-1] * 0.25 + p[1:] * 0.75
        p = np.vstack([p[:1], np.stack([q, r], 1).reshape(-1, 2), p[-1:]])
    return p

def rasterize_polyline(pts, shape, scale=1.0):
    """8-connected raster of a polyline (points in grid units * scale). Returns the
    tiles as an ordered list of (x, y) with no repeats, clipped to `shape`."""
    pts = np.asarray(pts, float) * scale
    out = []
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        xs = np.round(np.linspace(x0, x1, n)).astype(int); ys = np.round(np.linspace(y0, y1, n)).astype(int)
        for x, y in zip(xs, ys):
            if 0 <= x < shape[0] and 0 <= y < shape[1] and (not out or out[-1] != (x, y)):
                out.append((int(x), int(y)))
    return out
