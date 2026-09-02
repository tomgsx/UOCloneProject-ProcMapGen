"""Stage 8, validation: acceptance metrics for a generated map, next to Felucca's.

Input : land_id[x, y], land_z[x, y] (int8), the statics array, the client's
        TileData (needs UO_CLIENT_DIR) and the town sites.
Output: a dict of numbers, written as metrics.json and printed by report().

The metrics are the ones the rules were tuned against (docs/elevation.md,
docs/water-bodies.md, docs/vegetation-props.md): how much land is stretched,
how tall the steps are, whether every wet shore tile carries a water static,
and whether the world is walkable under the client's step rule.
"""
import numpy as np
from . import accel as ndimage  # exact-preserving parallel scipy.ndimage
from uo.tiledata import TileData, TileFlag

FELUCCA = {  # Felucca's values for the main continent, from the measurements in docs/
    "stretched_dry_frac": 0.31, "corner_p90": 8, "corner_p99": 23,
    "walkable_corner_p99": 6, "walkable_corner_max": 55,
    "wet_shore_with_static": 0.959, "dead_tree_frac": 0.0046,
}

def corner_diff(lz, land_mask):
    """Per tile, max minus min of the four corner heights of its quad, over `land_mask`."""
    z = lz.astype(np.int16)
    a, b, c, d = z[:-1, :-1], z[1:, :-1], z[:-1, 1:], z[1:, 1:]
    cd = np.max(np.stack([a, b, c, d]), 0) - np.min(np.stack([a, b, c, d]), 0)
    return cd[land_mask[:-1, :-1]]

def metrics(lid, lz, st, td=None):
    """Terrain and shoreline metrics (see FELUCCA for the reference values)."""
    td = td or TileData()
    W, H = lid.shape
    flags = td.land_flags[lid]
    wet = (flags & np.uint64(TileFlag.Wet)) != 0
    imp = (flags & np.uint64(TileFlag.Impassable)) != 0
    void = lid == 0x244
    valid = ~void
    dry = valid & ~wet & ~imp
    # water statics
    ws = (st["id"] >= 0x1796) & (st["id"] <= 0x17B2)
    has_ws = np.zeros((W, H), bool); has_ws[st["x"][ws], st["y"][ws]] = True
    wetzone = wet | has_ws
    shore_wet = wetzone & ndimage.binary_dilation(dry, np.ones((3, 3)))
    out = {}
    out["dry_tiles"] = int(dry.sum()); out["wet_tiles"] = int(wet.sum()); out["void_tiles"] = int(void.sum())
    cd = corner_diff(lz, valid & ~wet)
    out["stretched_frac(valid,non-water)"] = float((cd > 0).mean())
    out["corner_p90"] = int(np.percentile(cd, 90)); out["corner_p99"] = int(np.percentile(cd, 99))
    out["corner_p999"] = int(np.percentile(cd, 99.9)); out["corner_max"] = int(cd.max())
    cdw = corner_diff(lz, dry)
    out["walkable_corner_p99"] = int(np.percentile(cdw, 99)); out["walkable_corner_max"] = int(cdw.max())
    out["walkable_z0_frac"] = float((lz[dry] == 0).mean())
    out["wet_shore_tiles"] = int(shore_wet.sum())
    out["wet_shore_with_static"] = float(has_ws[shore_wet].mean()) if shore_wet.any() else 0.0
    cardinal = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)
    out["water_land_adjacent_to_dry"] = int((wet & ndimage.binary_dilation(dry, cardinal)).sum())
    # statics sanity
    sflags = td.static_flags[st["id"]]
    out["statics"] = int(len(st))
    sx, sy = st["x"], st["y"]
    lzs = lz[sx, sy].astype(np.int16)
    out["statics_below_land_by_5+"] = int(((lzs - st["z"]) >= 5).sum())  # hidden by CanDrawStatic (approximating AverageZ by z)
    names = np.array(td.static_names)
    nm = names[st["id"]]
    dead = np.array(["dead" in n.lower() or "stump" in n.lower() for n in np.unique(nm)])
    u, inv = np.unique(nm, return_inverse=True)
    out["dead_tree_frac"] = float(dead[inv].mean())
    # the map edge must stay water
    out["land_touching_edge"] = int(dry[0].sum() + dry[-1].sum() + dry[:, 0].sum() + dry[:, -1].sum())
    return out

def report(m):
    """The metrics as aligned text, with Felucca's value beside each one that has a reference."""
    lines = []
    for k, v in m.items():
        ref = FELUCCA.get(k)
        vs = f"{v:>14}" if isinstance(v, (int, float)) else str(v)
        lines.append(f"{k:40s} {vs}" + (f"   (Felucca {ref})" if ref is not None else ""))
    return "\n".join(lines)


def walkability(lid, lz, st, td=None, towns=None):
    """Walkability metrics: the walkable mask (passable land, no blocking static) and
    the fraction of cardinal steps the ClassicUO step rule refuses (docs/render-spec.md
    section 8), plus connectivity and which component each town lies in."""
    td = td or TileData()
    W, H = lid.shape
    flags = td.land_flags[lid]
    passable = ((flags & np.uint64(TileFlag.Impassable)) == 0) & (lid > 2)
    sfl = td.static_flags[st["id"]]; sh = td.static_height[st["id"]].astype(np.int16)
    blocking = ((sfl & np.uint64(TileFlag.Impassable)) != 0) & ((sfl & np.uint64(TileFlag.Surface)) == 0)
    lzs = lz[st["x"], st["y"]].astype(np.int16)
    # a static blocks when [z, z + h) intersects [land z, land z + 16)
    blk = blocking & (st["z"].astype(np.int16) + sh > lzs) & (st["z"].astype(np.int16) < lzs + 16) & (sh > 0)
    blocked = np.zeros((W, H), bool); blocked[st["x"][blk], st["y"][blk]] = True
    walk = passable & ~blocked
    # average z (CentrED/ClassicUO): corners top=(x,y) right=(x+1,y) left=(x,y+1) bottom=(x+1,y+1)
    z = lz.astype(np.int16)
    zt = z; zr = np.roll(z, -1, 0); zl = np.roll(z, -1, 1); zb = np.roll(z, (-1, -1), (0, 1))
    avg = np.where(np.abs(zt - zb) <= np.abs(zl - zr), (zt + zb) >> 1, (zl + zr) >> 1)
    # stepping east, the source edge average is (right + bottom) >> 1; stepping south, (left + bottom) >> 1
    edgeE = (zr + zb) >> 1; edgeS = (zl + zb) >> 1
    maxE = np.maximum(avg, edgeE) + 2; maxS = np.maximum(avg, edgeS) + 2
    okE = walk[:-1, :] & walk[1:, :]; okS = walk[:, :-1] & walk[:, 1:]
    blockE = okE & (avg[1:, :] > maxE[:-1, :]); blockS = okS & (avg[:, 1:] > maxS[:, :-1])
    # the reverse directions: a west step from x+1 to x, a north step from y+1 to y
    edgeW = (zt + zl) >> 1; edgeN = (zt + zr) >> 1
    blockW = okE & (avg[:-1, :] > (np.maximum(avg, edgeW) + 2)[1:, :]); blockN = okS & (avg[:, :-1] > (np.maximum(avg, edgeN) + 2)[:, 1:])
    out = {"walkable_tiles": int(walk.sum()),
           "step_blocked_frac_E": float(blockE.sum() / max(1, okE.sum())), "step_blocked_frac_S": float(blockS.sum() / max(1, okS.sum())),
           "step_blocked_frac_W": float(blockW.sum() / max(1, okE.sum())), "step_blocked_frac_N": float(blockN.sum() / max(1, okS.sum()))}
    # connectivity: 4-connected components of walkable tiles
    lab, n = ndimage.label(walk)
    sizes = np.bincount(lab.ravel()); sizes[0] = 0
    out["walk_components"] = int(n); out["largest_component_frac"] = float(sizes.max() / max(1, walk.sum()))
    if towns is not None:
        comps = [int(lab[x, y]) for x, y in towns]
        out["town_components"] = comps
    return out
