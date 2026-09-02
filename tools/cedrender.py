"""A software renderer that reproduces CentrED#'s map view (docs/render-spec.md, sections 3-7).

Used by the shoreline tools (blackhunt, notch_battery, world_check, bench_publish)
to see a generated world the way the editor draws it, without running the editor.
Implements: the exact projection (22 px per tile, 4 px per z), AlwaysFlat land (Wet
flag or TexID 0), texmap-versus-art selection with the id-index validity quirk,
per-triangle UV mapping (art diamond or texmap square), texmapped-land lighting with
per-corner normals, a per-pixel world-z depth buffer, static billboards with the
folded depth key 4z + h - |u|, PriorityZ cell ordering, the CanDrawStatic hidden
rule, and the no-draw lists.

Needs a client install: UO_CLIENT_DIR must point at a folder with artLegacyMUL.uop,
texmaps.mul, texidx.mul and tiledata.mul. Importing this module loads them.
"""
import struct, sys, os
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from uo.art import ArtLoader
from uo.texmaps import Texmaps
from uo.tiledata import TileData, TileFlag, UO

art = ArtLoader(os.path.join(UO, "artLegacyMUL.uop"))
tex = Texmaps()
td = TileData()

# The static height byte, read straight from the file (offset 20 of each 41-byte
# static record; docs/render-spec.md section 9) as a cross-check on uo.tiledata.
def _static_heights():
    with open(os.path.join(UO, "tiledata.mul"), "rb") as f:
        d = f.read()
    LAND_TOTAL = 512 * (4 + 32 * 30)
    n = (len(d) - LAND_TOTAL) // (4 + 32 * 41)
    h = np.zeros(n * 32, np.uint8)
    off = LAND_TOTAL
    for g in range(n):
        off += 4
        for i in range(32):
            h[g * 32 + i] = d[off + 20]
            off += 41
    return h
STATIC_HEIGHT = _static_heights()

NODRAW_STATIC = {0x0001, 0x21BC, 0x63D3, 0x2198, 0x2199, 0x21A0, 0x21A1, 0x21A2, 0x21A3, 0x21A4}
LIGHT_DIR = np.array([0.0, 1.0, 1.0]) / np.sqrt(2.0)

def _corner_normal(z, x, y):
    """render-spec 6.2 closed form for the corner tile at (x,y) of a padded z array."""
    zt = z[x, y - 1]; zb = z[x, y + 1]; zl = z[x - 1, y]; zr = z[x + 1, y]
    n = np.array([4.0 * (zl - zr), 4.0 * (zt - zb), 62.225])
    return n / np.linalg.norm(n)

def _corner_forces_stretch(z, x, y):
    """True when any cardinal neighbour of corner (x, y) differs in z (the normals rule
    then draws the tile stretched even if its own four corners agree)."""
    own = z[x, y]
    return (z[x, y - 1] != own or z[x, y + 1] != own or z[x - 1, y] != own or z[x + 1, y] != own)

def _tri(zbuf, img, pts, uvs, zs, texture, lit, normals):
    """Rasterise one triangle with per-pixel world-z key, UV nearest sampling and
    optional texmap lighting. pts: 3x(sx,sy); zs: world z px; normals: 3x3 or None."""
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    bx0 = max(0, int(np.floor(min(xs)))); bx1 = min(img.shape[1], int(np.ceil(max(xs))) + 1)
    by0 = max(0, int(np.floor(min(ys)))); by1 = min(img.shape[0], int(np.ceil(max(ys))) + 1)
    if bx1 <= bx0 or by1 <= by0:
        return
    gy, gx = np.mgrid[by0:by1, bx0:bx1]
    gxc = gx + 0.5; gyc = gy + 0.5
    (x1, y1), (x2, y2), (x3, y3) = pts
    det = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    if abs(det) < 1e-9:
        return
    l1 = ((y2 - y3) * (gxc - x3) + (x3 - x2) * (gyc - y3)) / det
    l2 = ((y3 - y1) * (gxc - x3) + (x1 - x3) * (gyc - y3)) / det
    l3 = 1.0 - l1 - l2
    inside = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
    if not inside.any():
        return
    zpix = l1 * zs[0] + l2 * zs[1] + l3 * zs[2]
    u = l1 * uvs[0][0] + l2 * uvs[1][0] + l3 * uvs[2][0]
    v = l1 * uvs[0][1] + l2 * uvs[1][1] + l3 * uvs[2][1]
    th, tw = texture.shape[:2]
    ui = np.clip(u.astype(int), 0, tw - 1)
    vi = np.clip(v.astype(int), 0, th - 1)
    px = texture[vi, ui]
    ok = inside & (px[..., 3] > 0) & (zpix > zbuf[by0:by1, bx0:bx1])
    if not ok.any():
        return
    rgb = px[..., :3].astype(np.float32)
    if lit:
        n = (l1[..., None] * normals[0] + l2[..., None] * normals[1] + l3[..., None] * normals[2])
        n = n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-9)
        base = np.maximum(n @ LIGHT_DIR, 0.0) / 2.0 + 0.5
        light = np.clip(1.5 * base - 0.4267767, 0.0, 1.0)
        rgb = rgb * light[..., None]
    sub_img = img[by0:by1, bx0:bx1]
    sub_z = zbuf[by0:by1, bx0:bx1]
    sub_img[ok] = np.clip(rgb[ok], 0, 255).astype(np.uint8)
    sub_z[ok] = zpix[ok]

def render(lid, lz, sts, w, h, path, pad_top=140, pad_bottom=200):
    """lid/lz indexed [x,y], shape >= (w+2, h+2) (one row/col margin beyond the
    drawn w x h window, for corner z lookups). sts: (x, y, id, z) local coords."""
    lid = np.asarray(lid); lz = np.asarray(lz).astype(int)
    # pad z by 1 on each side for corner-normal lookups (clamp = own z at edges)
    zp = np.pad(lz, 1, mode="edge")
    W_ = (w + h) * 22 + 96
    H_ = (w + h) * 11 * 2 + pad_top + pad_bottom
    ox = h * 22 + 44; oy = pad_top
    img = np.zeros((H_, W_, 3), np.uint8)
    zbuf = np.full((H_, W_), -1e9, np.float32)

    wet_flag = np.uint64(TileFlag.Wet)
    for X in range(w):
        for Y in range(h):
            tid = int(lid[X, Y])
            if tid <= 2:
                continue
            flags = np.uint64(td.land_flags[tid])
            texid = int(td.land_texid[tid])
            always_flat = (texid == 0) or bool(flags & wet_flag)
            if always_flat:
                z00 = z10 = z01 = z11 = int(lz[X, Y])
            else:
                z00 = int(lz[X, Y]); z10 = int(lz[min(X + 1, lid.shape[0] - 1), Y])
                z01 = int(lz[X, min(Y + 1, lid.shape[1] - 1)])
                z11 = int(lz[min(X + 1, lid.shape[0] - 1), min(Y + 1, lid.shape[1] - 1)])
            stretched = not (z00 == z10 == z01 == z11)
            tm_valid = tex.valid(tid)          # the id-index quirk: validity at LAND ID
            art_img = art.land(tid)
            if tm_valid and not always_flat and not stretched:
                # normals rule can force stretching
                stretched = any(_corner_forces_stretch(zp, cx + 1, cy + 1)
                                for cx, cy in ((X, Y), (X + 1, Y), (X, Y + 1), (X + 1, Y + 1)))
            use_tm = (not always_flat) and tm_valid and (stretched or art_img is None)
            texture = tex.get(tid) if use_tm else art_img
            if texture is None:
                texture = art_img if art_img is not None else tex.get(tid)
                if texture is None:
                    continue
                use_tm = texture is not art_img
            Sx = ox + 22 * (X - Y); Sy = oy + 22 * (X + Y)
            v0 = (Sx, Sy - 44 - 4 * z00); v1 = (Sx + 22, Sy - 22 - 4 * z10)
            v2 = (Sx - 22, Sy - 22 - 4 * z01); v3 = (Sx, Sy - 4 * z11)
            zk = [4.0 * z00, 4.0 * z10, 4.0 * z01, 4.0 * z11]
            if use_tm:
                zk = [q - 0.01536 for q in zk]   # texmap depth bias (pushed away)
                tw = texture.shape[1]
                uv0, uv1, uv2, uv3 = (0, 0), (tw, 0), (0, tw), (tw, tw)
                nrm = [_corner_normal(zp, X + 1, Y + 1), _corner_normal(zp, X + 2, Y + 1),
                       _corner_normal(zp, X + 1, Y + 2), _corner_normal(zp, X + 2, Y + 2)]
            else:
                uv0, uv1, uv2, uv3 = (22, 0), (44, 22), (0, 22), (22, 44)
                nrm = [None] * 4
            _tri(zbuf, img, (v0, v1, v2), (uv0, uv1, uv2), (zk[0], zk[1], zk[2]), texture, use_tm,
                 (nrm[0], nrm[1], nrm[2]))
            _tri(zbuf, img, (v3, v2, v1), (uv3, uv2, uv1), (zk[3], zk[2], zk[1]), texture, use_tm,
                 (nrm[3], nrm[2], nrm[1]))

    # statics: per cell ascending PriorityZ; CellIndex bias count..1 descending
    by_cell = {}
    for (X, Y, tid, z) in sts:
        if 0 <= X < w and 0 <= Y < h and tid not in NODRAW_STATIC:
            by_cell.setdefault((X, Y), []).append((tid, z))
    for (X, Y), items in by_cell.items():
        def prio(it):
            tid, z = it
            bg = 1 if (np.uint64(td.static_flags[tid]) & np.uint64(TileFlag.Background)) else 0
            hh = 1 if STATIC_HEIGHT[tid] > 0 else 0
            return z - bg + hh
        items.sort(key=prio)
        # land AverageZ for the hidden rule
        tid_l = int(lid[X, Y])
        flags_l = np.uint64(td.land_flags[tid_l])
        if (int(td.land_texid[tid_l]) == 0) or bool(flags_l & np.uint64(TileFlag.Wet)):
            zt = zb = zl = zr = int(lz[X, Y])
        else:
            zt = int(lz[X, Y]); zr = int(lz[min(X + 1, lid.shape[0] - 1), Y])
            zl = int(lz[X, min(Y + 1, lid.shape[1] - 1)])
            zb = int(lz[min(X + 1, lid.shape[0] - 1), min(Y + 1, lid.shape[1] - 1)])
        avg = (zt + zb) >> 1 if abs(zt - zb) <= abs(zl - zr) else (zl + zr) >> 1
        n_items = len(items)
        for ci, (tid, z) in enumerate(items):
            if tid_l > 2 and avg >= prio((tid, z)) + 5:
                continue                       # CanDrawStatic hidden rule
            sprite = art.static(tid)
            if sprite is None:
                continue
            sh, sw = sprite.shape[:2]
            bcx = ox + 22 * (X - Y); bcy = oy + 22 * (X + Y) - 4 * z
            x0 = int(bcx - sw // 2); y0 = int(bcy - sh)
            xs0, ys0 = max(0, x0), max(0, y0)
            xs1, ys1 = min(W_, x0 + sw), min(H_, y0 + sh)
            if xs1 <= xs0 or ys1 <= ys0:
                continue
            sub = sprite[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]
            gy, gx = np.mgrid[ys0:ys1, xs0:xs1]
            ucol = (gx - bcx) + 0.5            # px right of centre column
            hrow = (bcy - gy) - 0.5            # px above bottom row
            bias = (n_items - ci) * 1e-4       # lowest priority pushed farthest away
            key = 4.0 * z + hrow - np.abs(ucol) - bias
            trans = bool(np.uint64(td.static_flags[tid]) & np.uint64(TileFlag.Translucent))
            ok = (sub[..., 3] > 0) & (key > zbuf[ys0:ys1, xs0:xs1])
            if not ok.any():
                continue
            rgb = sub[..., :3].astype(np.float32)
            if trans:
                rgb = rgb * 0.698 + img[ys0:ys1, xs0:xs1].astype(np.float32) * 0.302
            img[ys0:ys1, xs0:xs1][ok] = np.clip(rgb[ok], 0, 255).astype(np.uint8)
            zbuf[ys0:ys1, xs0:xs1][ok] = key[ok]

    Image.fromarray(img, "RGB").save(path)
    return path

def load_mul_window(root, x0, y0, w, h):
    """Read a w x h window (plus the 2-tile margin render() needs) of a world folder's
    map0.mul and its statics. Returns (lid, lz, statics as (x, y, id, z) local tuples)."""
    lid = np.zeros((w + 2, h + 2), np.uint16)
    lz = np.zeros((w + 2, h + 2), np.int16)
    with open(f"{root}/map0.mul", "rb") as f:
        for x in range(x0, x0 + w + 2):
            for y in range(y0, y0 + h + 2):
                blk = (x // 8) * 512 + y // 8
                cell = (y % 8) * 8 + x % 8
                f.seek(blk * 196 + 4 + cell * 3)
                b = f.read(3)
                lid[x - x0, y - y0] = b[0] | (b[1] << 8)
                lz[x - x0, y - y0] = struct.unpack("b", b[2:3])[0]
    sts = []
    with open(f"{root}/staidx0.mul", "rb") as fi, open(f"{root}/statics0.mul", "rb") as fs:
        for bx in range(x0 // 8, (x0 + w) // 8 + 1):
            for by in range(y0 // 8, (y0 + h) // 8 + 1):
                fi.seek((bx * 512 + by) * 12)
                off, ln, _ = struct.unpack("<IiI", fi.read(12))
                if off == 0xFFFFFFFF or ln <= 0:
                    continue
                fs.seek(off)
                data = fs.read(ln)
                for i in range(0, ln, 7):
                    tid, dx, dy, tz, hue = struct.unpack_from("<HBBbH", data, i)
                    ax, ay = bx * 8 + dx, by * 8 + dy
                    if x0 <= ax < x0 + w and y0 <= ay < y0 + h:
                        sts.append((ax - x0, ay - y0, tid, tz))
    return lid, lz, sts
