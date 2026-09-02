"""Scan a generated world's coastline for unpainted pixels.

Usage:
    UO_CLIENT_DIR="/path/to/client" python3 tools/world_check.py <world_dir> [x y]

Renders 40 randomly sampled 24 x 24 coastline windows (dry tiles cardinally
adjacent to water, spread over the map) with tools/cedrender.py and reports
every cluster of 4 or more pixels inside the drawn lozenge that nothing
painted - the wedge defect described in gen/water.py. With x y, a 30 x 30
window at that tile is scanned first, which is handy for re-checking a spot
found in the editor. Writes wc-<tag>.png for each window into the current
directory.
"""
import sys
import numpy as np
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
import tools.cedrender as cr
from scipy import ndimage as ndi

if len(sys.argv) not in (2, 4):
    sys.exit(__doc__)
ROOT = sys.argv[1]
st = np.load(f"{ROOT}/gen_state.npz")
wet, z = st["wet"], st["z"]
W_, H_ = wet.shape

def render_cov(lid, lz, sts, w, h, path):
    """Render and return the renderer's depth buffer, captured by intercepting the
    np.full call that creates it (its sentinel fill value is -1e9)."""
    captured = []
    real_full = np.full
    def spy(shape, val, dtype=None):
        a = real_full(shape, val, dtype)
        if isinstance(val, float) and val == -1e9:
            captured.append(a)
        return a
    cr.np.full = spy
    try:
        cr.render(lid, lz, sts, w, h, path)
    finally:
        cr.np.full = real_full
    return captured[0]

def lozenge(w, h, H2, W2, pad_top=140):
    """Mask of the image pixels well inside the drawn tile area (at z 0)."""
    ox = h * 22 + 44; oy = pad_top
    gy, gx = np.mgrid[0:H2, 0:W2]
    a = (gx - ox) / 22.0
    b = (gy - oy) / 22.0
    Xc = (a + b) / 2.0; Yc = (b - a) / 2.0
    return (Xc > 1.5) & (Xc < w - 1.5) & (Yc > 1.5) & (Yc < h - 1.5)

def scan(x0, y0, w, h, tag):
    """Sizes of the unpainted clusters (>= 4 px) inside one window, largest first."""
    lid, lz, sts = cr.load_mul_window(ROOT, x0, y0, w, h)
    zbuf = render_cov(lid, lz, sts, w, h, f"wc-{tag}.png")
    gap = (zbuf == -1e9) & lozenge(w, h, *zbuf.shape)
    lab, n = ndi.label(gap)
    sizes = np.bincount(lab.ravel())[1:]
    big = sorted([int(s) for s in sizes if s >= 4], reverse=True)
    return big

# an optional spot to re-check first
if len(sys.argv) == 4:
    x, y = int(sys.argv[2]), int(sys.argv[3])
    print(f"window <{x},{y}>:", scan(x, y, 30, 30, "spot"))

# sample the coastline: dry tiles cardinally adjacent to wet, spread over the map
dry = ~wet
edge = dry & (np.roll(wet, 1, 0) | np.roll(wet, -1, 0) | np.roll(wet, 1, 1) | np.roll(wet, -1, 1))
xs, ys = np.nonzero(edge)
rng = np.random.default_rng(1)
picks = rng.choice(len(xs), size=40, replace=False)
worst = []
for i, p in enumerate(picks):
    x0, y0 = int(xs[p]) - 12, int(ys[p]) - 12
    x0 = max(2, min(W_ - 28, x0)); y0 = max(2, min(H_ - 28, y0))
    big = scan(x0, y0, 24, 24, f"c{i}")
    if big:
        worst.append(((x0, y0), big))
        print(f"  coast <{x0},{y0}>: {big}")
print(f"coast windows with clusters: {len(worst)}/40")
