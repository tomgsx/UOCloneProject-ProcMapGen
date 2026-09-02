"""Scan a rendered world window for solid-black pixel clusters and map them back to tiles.

An unpainted wedge along a shoreline (a quad the client folds open between a sunk
tile, a flat water-land tile and a dry bank; see encode_water in gen/water.py) shows
in the render as a solid black sliver. This tool renders a window of a generated
world with tools/cedrender.py, finds clusters of near-black pixels, and prints the
candidate tiles under each with their land id, z and statics. A clean coastline
window reports no clusters except tree-canopy shadows (dark pixels inside genuine
art, always over land tiles with vegetation nearby).

Usage:
    UO_CLIENT_DIR="/path/to/client" python3 tools/blackhunt.py <world_dir> <x> <y> <w> <h> <out.png>
"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.cedrender import load_mul_window, render
from PIL import Image
from scipy import ndimage as ndi

ROOT = sys.argv[1]
x0, y0, w, h = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
out = sys.argv[6]

lid, lz, sts = load_mul_window(ROOT, x0, y0, w, h)
render(lid, lz, sts, w, h, out)
img = np.asarray(Image.open(out).convert("RGB")).astype(int)

# the renderer's projection origin (tools/cedrender.py render())
pad_top = 140
ox = h * 22 + 44
oy = pad_top

black = img.sum(axis=2) < 12
lab, n = ndi.label(black)
sizes = np.bincount(lab.ravel())
print(f"window ({x0},{y0}) {w}x{h}: components >=6px:",
      sorted([int(s) for s in sizes[1:] if s >= 6], reverse=True)[:20])


def tiles_for_pixel(px, py):
    """Invert the isometric projection for every z in -20..25; returns the set of tiles
    that could have painted this pixel."""
    cands = set()
    for z in range(-20, 26):
        a = (px - ox) / 22.0          # X - Y
        b = (py - oy + 4 * z) / 22.0  # X + Y
        Xi, Yi = int(round((a + b) / 2.0)), int(round((b - a) / 2.0))
        if 0 <= Xi < w and 0 <= Yi < h:
            cands.add((Xi, Yi))
    return cands


reported = 0
for l in range(1, n + 1):
    if sizes[l] < 6 or sizes[l] > 4000:   # >4000 px = the background outside the lozenge
        continue
    ys, xs = np.where(lab == l)
    cands = tiles_for_pixel(int(xs.mean()), int(ys.mean()))
    if not cands:
        continue
    reported += 1
    if reported > 12:
        print("... more clusters not shown")
        break
    print(f"\ncluster {l}: {int(sizes[l])} px at img({int(xs.mean())},{int(ys.mean())})")
    for (Xi, Yi) in sorted(cands):
        stat = [(hex(t), z) for (sx, sy, t, z) in sts if sx == Xi and sy == Yi]
        print(f"  tile <{x0 + Xi},{y0 + Yi}> land 0x{int(lid[Xi, Yi]):x} "
              f"z={int(lz[Xi, Yi])} statics={stat}")
if reported == 0:
    print("no black clusters inside the window")
