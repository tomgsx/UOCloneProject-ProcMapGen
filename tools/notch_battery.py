"""Render a battery of small shore geometries and report unpainted pixels.

Usage:
    UO_CLIENT_DIR="/path/to/client" python3 tools/notch_battery.py [name-filter]

Each scene is a 19 x 19 wet mask (straight shores facing each way, stepped
banks, a lone dry tile, a 2 x 2 dry block, and the six bench islands from
docs/island-tests). The scene is encoded with the current shoreline rules,
rendered with tools/cedrender.py, and every pixel inside the drawn lozenge
that no land quad or static painted is counted. A correct coastline paints
every pixel: an unpainted cluster is a "wedge" (a quad the client folds open
between a sunk tile, a flat foot tile and a dry bank; see encode_water in
gen/water.py), and the report maps each cluster back to candidate tiles with
their land id, z, dry-neighbour mask and statics.

Writes bat-<scene>.png in the current directory for each scene.
"""
import os, sys
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import tools.cedrender as cr
from gen.water import encode_water, check_water, remove_wet_tips, fix_tips, dir_mask
from gen import materials as M
from PIL import Image
from scipy import ndimage as ndi

NSZ = 19

def scenes():
    n = NSZ
    X, Y = np.indices((n, n))
    out = {}
    out["east-straight"] = X < 9            # dry to the east
    out["west-straight"] = X >= 9
    out["north-straight"] = Y >= 9
    out["south-straight"] = Y < 9
    # river-like east bank with a step (convex corner poking west)
    out["step-east"] = ~((X >= 10) | ((X >= 8) & (Y >= 10)))
    # west bank with a step
    out["step-west"] = ~((X <= 8) | ((X <= 10) & (Y >= 10)))
    out["single-dry"] = ~((X == 9) & (Y == 9))
    out["dry-2x2"] = ~((abs(X - 9) <= 1) & (abs(Y - 9) <= 1) & (X >= 9) & (Y >= 9))
    # the bench islands
    for name in ("square", "diamond", "staircase2", "plus", "notch", "blob"):
        d = np.load(os.path.join(ROOT, "docs", "island-tests", f"{name}.npz"))
        out["bench-" + name] = d["wet"]
    return out

def build(wet):
    """Clean the mask as the pipeline does, then run the water rules over flat grass."""
    wet = fix_tips(remove_wet_tips(wet.copy()))
    mat = np.full(wet.shape, M.GRASS, np.uint8)
    mat[wet] = M.WATER
    lid = np.full(wet.shape, 0x3, np.uint16)
    z = np.zeros(wet.shape, np.int16)
    st = encode_water(wet, z, lid, np.random.default_rng(42), mat)
    return wet, lid, z, st

def render_cov(lid, z, st, w, h, path):
    """Render a scene and return the renderer's depth buffer, captured by intercepting
    the np.full call that creates it (its sentinel fill value is -1e9)."""
    lid = np.pad(lid, ((0, 2), (0, 2)), mode="edge")
    z = np.pad(z, ((0, 2), (0, 2)), mode="edge")
    sts = [(int(x), int(y), int(i), int(zz)) for x, y, i, zz in
           zip(st["x"], st["y"], st["id"], st["z"])]
    captured = []
    real_full = np.full
    def spy(shape, val, dtype=None):
        a = real_full(shape, val, dtype)
        if isinstance(val, float) and val == -1e9:
            captured.append(a)
        return a
    cr.np.full = spy
    try:
        cr.render(lid, z, sts, w, h, path)
    finally:
        cr.np.full = real_full
    return captured[0]

def lozenge_mask(w, h, H_, W_, pad_top=140):
    """Approximate interior of the drawn area: tile hull at z in [-20, 25]."""
    ox = h * 22 + 44; oy = pad_top
    gy, gx = np.mgrid[0:H_, 0:W_]
    a = (gx - ox) / 22.0
    inner = np.zeros((H_, W_), bool)
    for zz in (0,):
        b = (gy - oy + 4 * zz) / 22.0
        Xc = (a + b) / 2.0; Yc = (b - a) / 2.0
        inner |= (Xc > 1.2) & (Xc < w - 1.2) & (Yc > 1.2) & (Yc < h - 1.2)
    return inner

def tiles_for_pixel(px, py, w, h, pad_top=140):
    """Invert the projection for every z in -20..25: the tiles that could have painted a pixel."""
    ox = h * 22 + 44; oy = pad_top
    cands = set()
    for zz in range(-20, 26):
        a = (px - ox) / 22.0
        b = (py - oy + 4 * zz) / 22.0
        Xi, Yi = int(round((a + b) / 2.0)), int(round((b - a) / 2.0))
        if 0 <= Xi < w and 0 <= Yi < h:
            cands.add((Xi, Yi))
    return cands

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, wetmask in scenes().items():
        if only and only not in name:
            continue
        wet, lid, z, st = build(wetmask)
        w = h = NSZ
        path = f"bat-{name}.png"
        zbuf = render_cov(lid, z, st, w, h, path)
        H_, W_ = zbuf.shape
        gap = (zbuf == -1e9) & lozenge_mask(w, h, H_, W_)
        lab, ncomp = ndi.label(gap)
        sizes = np.bincount(lab.ravel())[1:]
        big = [int(s) for s in sizes if s >= 4]
        print(f"{name}: unpainted-inner px={int(gap.sum())} clusters>=4px={sorted(big, reverse=True)[:8]}")
        dmn = dir_mask(~wet)
        shown = 0
        for l in np.argsort(sizes)[::-1]:
            if sizes[l] < 4 or shown >= 3:
                break
            shown += 1
            ys, xs = np.where(lab == l + 1)
            cx, cy = int(xs.mean()), int(ys.mean())
            for (Xi, Yi) in sorted(tiles_for_pixel(cx, cy, w, h)):
                stat = [(hex(int(i)), int(zz)) for x2, y2, i, zz in
                        zip(st["x"], st["y"], st["id"], st["z"]) if (x2, y2) == (Xi, Yi)]
                print(f"    <{Xi},{Yi}> wet={bool(wet[Xi,Yi])} lid=0x{int(lid[Xi,Yi]):x} "
                      f"z={int(z[Xi,Yi])} dm=0x{int(dmn[Xi,Yi]):02x} st={stat}")
