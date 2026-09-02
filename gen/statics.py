"""Stage 7, vegetation: trees, bushes, rocks and other natural statics.

Input : material[x, y], z[x, y] (integer land heights), wet and road masks, an
        exclusion mask, and the prop catalogue out/vegetation-props/props.json
        (measured on Felucca, docs/vegetation-props.md).
Output: a statics array (id, x, y, z, hue).

Vocabulary: a PROP is one placeable thing from the catalogue - a single static,
or a multi-part tree whose PARTS are (dx, dy, dz, id) offsets from an ANCHOR
tile. The catalogue groups props by the land material they were found on and
gives each a weight (how often Felucca uses it) and each material a density in
statics per 100 tiles.
"""
import json, numpy as np
from . import accel as ndimage  # exact-preserving parallel scipy.ndimage
from . import materials as M

# props whose name contains one of these are dungeon or decoration pieces, not landscape
BANNED_WORDS = ("stalagmite", "crystal", "bones", "skull", "spiderweb", "leaf litter", "hedge", "snow patch")
# Single-anchor props whose SPRITE is far wider than a tile: 0x0D36 "flowers (desert)"
# is 145 px, about 3 tiles of visual spill from one anchor, and nothing in placement
# can predict where that spill lands, so it overhangs open water and roads. 0x0D35
# "pipe cactus" (145 px) and 0x0D34 "morning glories" (131 px) are the same class;
# 0x0C98 "fan plant" (106 px) is borderline and stays.
BANNED_IDS = {0x0D36, 0x0D35, 0x0D34}
# which catalogue entry each material code draws from
MAT_CATALOGUE = {M.GRASS: "grass", M.FOREST: "forest", M.JUNGLE: "jungle", M.SAND: "sand", M.SNOW: "snow",
                 M.SWAMP: "swamp", M.SWAMP_RIM: "swamp", M.ROCK: "rock", M.DIRT: "dirt"}
TREE_NAME_FILTER = {  # material -> predicate on a tree prop's name: which species may grow there
    M.GRASS: lambda n: not any(w in n for w in ("palm", "banana", "cypress", "jungle", "Yew")),
    M.FOREST: lambda n: not any(w in n for w in ("palm", "banana", "cypress", "jungle", "Yew")),
    M.JUNGLE: lambda n: True,
    M.SAND: lambda n: "palm" in n,
    M.SNOW: lambda n: ("cedar" in n) or ("pine" in n),
    M.SWAMP: lambda n: "cypress" in n,
    M.SWAMP_RIM: lambda n: "cypress" in n,
    M.ROCK: lambda n: False,
    M.DIRT: lambda n: not any(w in n for w in ("palm", "banana", "cypress", "jungle", "Yew")),
}
KIND_FILTER = {  # material -> predicate on a prop's kind; materials not listed take everything but dead trees
    M.ROCK: lambda k: k == "rock",
    M.SAND: lambda k: k in ("cactus", "grass", "flower", "rock", "bush", "tree"),
    M.SNOW: lambda k: k in ("tree", "rock"),
    M.SWAMP: lambda k: k in ("reed", "other", "tree", "grass", "bush"),
    M.SWAMP_RIM: lambda k: k in ("reed", "other", "tree", "grass", "bush"),
}
# minimum spacing between tree anchors, in tiles, per material
TREE_SPACING = {M.FOREST: 2.0, M.JUNGLE: 1.5, M.GRASS: 2.5, M.SNOW: 1.2, M.SAND: 4.0, M.SWAMP: 2.5, M.SWAMP_RIM: 2.5, M.DIRT: 2.5}
# statics per 100 tiles where the catalogue's measured density is not wanted as is
DENSITY_OVERRIDE = {M.GRASS: 5.6, M.ROCK: 0.15, M.SNOW: 3.9, M.SWAMP: 9.0, M.SWAMP_RIM: 6.0, M.DIRT: 2.0}

class PropLibrary:
    """The prop catalogue, filtered per material."""
    def __init__(self, path):
        d = json.load(open(path))
        self.mats = d["materials"]
        self.ids = d["ids"]

    def props_for(self, mat):
        """(props allowed on this material, density in statics per 100 tiles)."""
        cat = MAT_CATALOGUE.get(mat)
        if cat is None: return [], 0.0
        entry = self.mats[cat]
        out = []
        kf = KIND_FILTER.get(mat, lambda k: k != "dead_tree")
        tf = TREE_NAME_FILTER.get(mat, lambda n: True)
        for p in entry["props"]:
            n = p["name"]; k = p["kind"]
            if p.get("anchor_id") in BANNED_IDS: continue
            if any(w in n.lower() for w in BANNED_WORDS): continue
            if not kf(k): continue
            if k in ("tree", "dead_tree") and not tf(n): continue
            if k == "dead_tree": continue
            out.append(p)
        dens = DENSITY_OVERRIDE.get(mat, entry["density_per_100"])
        return out, dens


def place_props(material, z, wet, road, rng, lib: PropLibrary, exclude_mask=None, road_clear_tree=2, water_clear=1):
    """Place vegetation on every dry tile of every material. Trees are spaced on a cell
    grid and need a flat footprint clear of water, roads (by `road_clear_tree` tiles) and
    other trees; smaller props are scattered uniformly. `exclude_mask` blocks tiles
    outright (plazas, bridges). Returns a statics structured array (id, x, y, z, hue)."""
    W, H = material.shape
    dry = ~wet
    near_water = ndimage.binary_dilation(wet, np.ones((2 * water_clear + 1,) * 2))
    near_road_tree = ndimage.binary_dilation(road, np.ones((2 * road_clear_tree + 1,) * 2))
    near_road_any = road
    if exclude_mask is None: exclude_mask = np.zeros((W, H), bool)
    zint = z.astype(np.int16)
    # flatness: all four corner tiles at the same z (safe for CanDrawStatic and for tree feet)
    flat = (zint == np.roll(zint, -1, 0)) & (zint == np.roll(zint, -1, 1)) & (zint == np.roll(zint, (-1, -1), (0, 1)))
    out_id, out_x, out_y, out_z = [], [], [], []
    occupied = np.zeros((W, H), bool)   # tree anchors and footprints
    for mat in np.unique(material):
        mat = int(mat)
        props, dens = lib.props_for(mat)
        if not props or dens <= 0: continue
        mask = (material == mat) & dry & ~exclude_mask
        area = int(mask.sum())
        if area == 0: continue
        trees = [p for p in props if p["kind"] == "tree"]
        others = [p for p in props if p["kind"] != "tree"]
        wt = np.array([p["weight"] for p in trees]); wo = np.array([p["weight"] for p in others])
        tree_frac = wt.sum() / (wt.sum() + wo.sum()) if len(trees) else 0.0
        n_total = dens * area / 100.0
        n_tree = int(n_total * tree_frac); n_other = int(n_total - n_tree)
        # ---- trees: one candidate per grid cell, so they keep their spacing
        if n_tree > 0:
            r = TREE_SPACING.get(mat, 2.5)
            cell = max(2, int(round(r * 1.25)))
            cx = np.arange(0, W, cell); cy = np.arange(0, H, cell)
            ncell = len(cx) * len(cy)
            # probability a cell gets a tree: the wanted count over the cells the material covers
            p_cell = min(1.0, n_tree / max(1, area / (cell * cell)))
            gx, gy = np.meshgrid(cx, cy, indexing="ij")
            # keep the cells whose centre is on this material
            sel = mask[np.minimum(gx + cell // 2, W - 1), np.minimum(gy + cell // 2, H - 1)]
            sel &= rng.random(gx.shape) < p_cell
            xs = gx[sel] + rng.integers(0, cell, int(sel.sum())); ys = gy[sel] + rng.integers(0, cell, int(sel.sum()))
            xs = np.minimum(xs, W - 1); ys = np.minimum(ys, H - 1)
            ok = mask[xs, ys] & flat[xs, ys] & ~near_water[xs, ys] & ~near_road_tree[xs, ys]
            xs, ys = xs[ok], ys[ok]
            choice = rng.choice(len(trees), size=len(xs), p=wt / wt.sum())
            for x, y, ci in zip(xs, ys, choice):
                p = trees[ci]
                parts = list(p["parts"])
                for v in p.get("optional_vines", []):
                    if rng.random() < v["p"]: parts += v["parts"]; break
                # every part must land on dry, level, unoccupied ground away from roads
                good = True
                for dx, dy, dz, pid in parts:
                    px, py = x + dx, y + dy
                    if not (0 <= px < W and 0 <= py < H): good = False; break
                    if not dry[px, py] or near_road_tree[px, py] or exclude_mask[px, py]: good = False; break
                    if zint[px, py] != zint[x, y]: good = False; break
                    if occupied[px, py] and (dx, dy) != (0, 0): good = False; break
                if not good or occupied[x, y]: continue
                for dx, dy, dz, pid in parts:
                    out_id.append(pid); out_x.append(x + dx); out_y.append(y + dy); out_z.append(int(zint[x, y]) + dz)
                    occupied[x + dx, y + dy] = True
        # ---- other props: uniform random over the material
        if n_other > 0 and len(others):
            idx = np.flatnonzero(mask.ravel())
            pick = rng.choice(idx, size=min(n_other, len(idx)), replace=True)
            xs, ys = pick // H, pick % H
            ok = ~occupied[xs, ys] & ~near_road_any[xs, ys] & (~near_water[xs, ys] | (mat == M.SWAMP))
            xs, ys = xs[ok], ys[ok]
            choice = rng.choice(len(others), size=len(xs), p=wo / wo.sum())
            for x, y, ci in zip(xs, ys, choice):
                p = others[ci]
                for dx, dy, dz, pid in p["parts"]:
                    px, py = x + dx, y + dy
                    if 0 <= px < W and 0 <= py < H and dry[px, py]:
                        out_id.append(pid); out_x.append(px); out_y.append(py); out_z.append(int(zint[x, y]) + dz)
    st = np.empty(len(out_id), dtype=[("id", "<u2"), ("x", "<u2"), ("y", "<u2"), ("z", "i1"), ("hue", "<u2")])
    st["id"] = out_id; st["x"] = out_x; st["y"] = out_y; st["z"] = np.clip(out_z, -128, 127); st["hue"] = 0
    return st
