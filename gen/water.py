"""Stage 5, the shoreline: turn a wet mask into Britannia's exact coast anatomy.

The rules here were measured on the real Felucca map (docs/water-bodies.md) and
reproduce how its shores are built: the water is not a flat plane but a trench
of sunk land tiles with water statics floating above it, and every tile within
a few steps of dry land carries a specific land id and height that depends on
which of its corners are wet.

Input : wet[x, y] bool    ocean + lakes + rivers, all in the "sunk" style
        material[x, y]    gen.materials codes (decides the beach family)
        z[x, y] int16     dry-terrain heights, modified in place
        land_id[x, y]     uint16 land ids already holding the dry materials,
                          modified in place
Output: the water statics (structured array id, x, y, z, hue), all at SEA_Z
        except the invisible blockers, which sit at the tile's own z.

Vocabulary used throughout this module:

* A land tile (x, y) is drawn as a QUAD whose four corners take the z of
  (x, y), (x+1, y), (x, y+1) and (x+1, y+1). The client stretches the quad
  between those heights, so a tile's look depends on its three neighbours.
* CORNER PATTERN c: four bits saying which corners of the tile's quad are wet,
  own=1 (x, y), E=2 (x+1, y), S=4 (x, y+1), D=8 (x+1, y+1). c = 0 is fully
  dry, c = 15 fully wet, and 1..14 are MIXED quads, which take "dropoff" art
  from a beach FAMILY (grass, sand, snow or dirt) keyed by the pattern.
* DIRECTION MASK: eight bits over the 8-neighbours, in CentrED's order,
  N=1 (0,-1) R=2 (1,-1) E=4 (1,0) D=8 (1,1) S=16 (0,1) L=32 (-1,1) W=64 (-1,0)
  U=128 (-1,-1). `wm` is the mask of wet neighbours, `dm` of dry ones.
* SUNK tile: a wet tile whose land sits at TRENCH_Z (-15) with a water static
  at SEA_Z (-5) above it, the construction 96 % of Felucca's water uses.
* WATER-LAND: the flat water land ids 0xA8-0xAB at SEA_Z with no static. They
  are AlwaysFlat in the client, so a water-land tile never stretches.
* SHELF: a sunk tile that touches both dry land and water-land. It is raised to
  SHELF_Z (-8) so the client does not fold its quad open (see encode_water).
* SIDE BANK: a dry tile whose N or W neighbour is wet. It forms the right or
  left corner of the wet quad behind it and sits just above the water line.
  FRONT BANK: any other dry tile touching water.
* OBJECT WATER: the six opaque 44 x 44 water statics 0x1797-0x179C (OBJW).
  FOAM: the waterline statics 0x179D-0x17B2, in three coverage classes -
  full diamonds with the foam baked in (0x17A9/0x17AB/0x17AA/0x17AC), strips
  (0x179F/0x17A0/0x17A3/0x17A4) and small curls (0x17A5/0x17B2/0x17A8/0x17B0/
  0x17AD/0x17AE) that expose whatever land art lies beneath them.
* RING k: for fully wet tiles, the chessboard distance to the nearest dry tile.
  Rings 1-3 carry seafloor ids that face the land, 4-6 deep seafloor, 7 a
  mix, and 8+ water-land.
"""
import numpy as np
from . import accel as ndimage  # exact-preserving parallel scipy.ndimage

OBJW = np.array([0x1797, 0x1798, 0x1799, 0x179A, 0x179B, 0x179C], np.uint16)
WATER_LAND = np.array([0xA8, 0xA9, 0xAA, 0xAB], np.uint16)
N, R, E, D, S, L, W, U = 1, 2, 4, 8, 16, 32, 64, 128
DIR_OFF = {N: (0, -1), R: (1, -1), E: (1, 0), D: (1, 1), S: (0, 1), L: (-1, 1), W: (-1, 0), U: (-1, -1)}
SEA_Z, TRENCH_Z = -5, -15
SHELF_Z = -8    # sunk tiles that touch both dry land and surface water (see encode_water)

def shift(a, dx, dy, fill=False):
    """out[x, y] = a[x + dx, y + dy], with `fill` where that falls outside the array."""
    out = np.full_like(a, fill)
    W_, H_ = a.shape
    xs = slice(max(0, -dx), min(W_, W_ - dx)); ys = slice(max(0, -dy), min(H_, H_ - dy))
    xd = slice(max(0, dx), min(W_, W_ + dx)); yd = slice(max(0, dy), min(H_, H_ + dy))
    out[xs, ys] = a[xd, yd]
    return out

def dir_mask(mask):
    """Direction mask per tile: which of the 8 neighbours have `mask` set (bits N..U above)."""
    m = np.zeros(mask.shape, np.uint8)
    for bit, (dx, dy) in DIR_OFF.items():
        m |= (shift(mask, dx, dy).astype(np.uint8) * bit).astype(np.uint8)
    return m

def _choose(rng, where, options, probs=None):
    """One random pick from `options` for every True cell of `where`."""
    n = int(where.sum())
    if probs is not None:
        probs = np.asarray(probs, float); probs = probs / probs.sum()
    return rng.choice(np.asarray(options), size=n, p=probs)

MAT_SAND, MAT_SNOW, MAT_DIRT = 4, 5, 8
# Height distribution of side banks: Felucca's side banks sit at -4..0, mostly -3..-2.
SIDE_Z = ([-4, -3, -2, -1, 0], [0.10, 0.30, 0.30, 0.20, 0.10])

# Dropoff families: the land id a mixed quad takes, keyed by its corner pattern
# (own=1, E=2, S=4, D=8), as (ids, relative weights or None for uniform). Every
# id in these families is Impassable in the client's tiledata, so a mixed quad
# is never walkable ground - a player cannot step off the beach into the trench.
FAM_GRASS = {
    1: ([0x20], None), 2: ([0x1F], None), 3: ([0x24, 0x28], [0.76, 0.24]),
    4: ([0x1E], None), 5: ([0x22, 0x26], [0.76, 0.24]), 6: ([0x1C], None),
    7: ([0x1C], None), 8: ([0x1D], None), 9: ([0x20], None),
    10: ([0x23, 0x27], [0.76, 0.24]), 11: ([0x1A], None),
    12: ([0x21, 0x25], [0.76, 0.24]), 13: ([0x1B], None), 14: ([0x1C], None),
}
# The sand-topped counterpart of the grass-lipped family: the same orientations
# in the same order at a constant id offset, and every piece is Impassable too.
FAM_SAND = {
    pat: ([int(tid) + 0x19F for tid in ids], probs)
    for pat, (ids, probs) in FAM_GRASS.items()
}
FAM_SNOW = {
    1: ([0x17F], None), 2: ([0x17E], None), 3: ([0x184], None),
    4: ([0x17D], None), 5: ([0x181], None), 6: ([0x17C], None),
    7: ([0x179], None), 8: ([0x17C], None), 9: ([0x17C], None),
    10: ([0x182, 0x185], [0.76, 0.24]), 11: ([0x17B], None),
    12: ([0x180], None), 13: ([0x17A], None), 14: ([0x17C], None),
}
FAM_DIRT = {
    1: ([0xA0], None), 2: ([0xA1, 0x8D], [0.76, 0.24]),
    3: ([0x92, 0x99], [0.76, 0.24]), 4: ([0xA2, 0x91], [0.76, 0.24]),
    5: ([0x8F, 0x98, 0x96], [0.731, 0.188, 0.082]), 6: ([0x95], None),
    7: ([0x95], None), 8: ([0xA3, 0x95], [0.776, 0.224]),
    9: ([0xA3], None), 10: ([0x8E, 0x8D, 0x9B], [0.465, 0.349, 0.185]),
    11: ([0x8D], None), 12: ([0x93, 0x91, 0x9A], [0.472, 0.369, 0.159]),
    13: ([0x91], None), 14: ([0x95], None),
}

# Wet mixed quads whose static is decided by the corner pattern alone: they
# take object water. (Patterns 3, 5, 11 and 13 depend on the wet context
# instead and are handled inline in encode_water.)
WET_STATIC_RULES = {
    1: (OBJW, None),
    7: (OBJW, None),
    9: (OBJW, None),
}
# Foam on DRY mixed quads. The key is the corner pattern; the value maps a set
# of required wet-neighbour bits to (static ids, relative weights, placement
# probability). A rule fires when `wm` contains ALL its required bits - a
# superset match, not an exact one - because exact matching left bare wedges
# at staircase steps whose wet mask carries an extra bit or two. The contexts
# that used to produce floating foam (a mask missing one of the three cardinal
# bits, e.g. S|L without W) still never match. The west-facing family is 0x17B2
# alone: 0x17A5 is invisible in the client, and a placement chance below 1
# leaves gaps in the waterline.
DRY_OVERLAY_RULES = {
    2: {N | R | E: ([0x17A8, 0x17B0], None, 1.0)},
    4: {S | L | W: ([0x17B2], None, 1.0)},
    10: {N | R | E: ([0x17A8, 0x17B0], None, 1.0)},
    12: {S | L | W: ([0x17B2], None, 1.0)},
    # Patterns 6 and 14 are step tips and occur on both banks: east-side tips
    # carry the E-corner curls, west-side tips (full S|L|W context) carry
    # 0x17B2 like their pattern-4 neighbours.
    6: {N | R | E: ([0x17A8, 0x17B0], None, 1.0),
        S | L | W: ([0x17B2], None, 1.0)},
    14: {N | R | E: ([0x17A8, 0x17B0], None, 1.0),
         S | L | W: ([0x17B2], None, 1.0)},
}
SNOW_BLOCK_PATTERNS = (7, 11, 13)
INVISIBLE_BLOCKER = 0x2199

def remove_wet_tips(wet, max_iter=20):
    """Dry out one-tile water spikes: wet tiles with dry land on 3 or 4 cardinal sides.
    No shoreline piece fits such a tile, so the coast must not contain one."""
    wet = wet.copy()
    for _ in range(max_iter):
        d = ~wet
        n = shift(d, 0, -1).astype(np.int8) + shift(d, 1, 0).astype(np.int8) + shift(d, 0, 1).astype(np.int8) + shift(d, -1, 0).astype(np.int8)
        tips = wet & (n >= 3)
        if not tips.any(): break
        wet &= ~tips
    return wet

def fix_tips(wet, max_iter=40):
    """Flood dry tiles whose E and S neighbours are wet but whose D neighbour is dry.
    A valid convex corner has E, S and D all wet; this E+S-only shape has no piece in
    any family, so the tile joins the water instead."""
    wet = wet.copy()
    for _ in range(max_iter):
        east = shift(wet, 1, 0, fill=True)
        south = shift(wet, 0, 1, fill=True)
        diagonal = shift(wet, 1, 1, fill=True)
        tips = ~wet & east & south & ~diagonal
        if not tips.any(): break
        wet |= tips
    return wet

def encode_water(wet, z, land_id, rng, material=None, dry_shore_z_dist=None, dry_overlay_exclude=None):
    """Apply the coast anatomy to a wet mask.

    Modifies `z` (int16) and `land_id` (uint16) in place and returns the water
    statics. `material` picks the beach family per tile; without it every shore
    is grass. `dry_overlay_exclude` marks dry tiles that must not receive foam
    (the pipeline passes road tiles on the bank, which it flattens to z 0).
    `dry_shore_z_dist` is accepted for compatibility and unused.

    The passes, in order:
    1. Heights: wet tiles sink to TRENCH_Z; dry tiles touching water take the
       measured bank heights for their corner pattern.
    2. Land ids of mixed quads from the beach family, with an invisible blocker
       on the snow pieces that are not Impassable.
    3. Statics on wet mixed quads, chosen by corner pattern and wet context.
    4. Foam on dry mixed quads (DRY_OVERLAY_RULES).
    5. Fully wet quads by ring distance: seafloor ids facing the land, then
       deep seafloor, then water-land.
    6. The shelf: sunk tiles between dry land and water-land rise to SHELF_Z,
       and the banks reading such a shelf are clamped so no quad folds open.
    """
    Wd, Hd = wet.shape
    dry = ~wet
    # ---------------- heights: wet tiles and the dry tiles beside them
    z[wet] = TRENCH_Z
    # Felucca's bank heights, by where the water is relative to the tile:
    # - a dry tile whose N or W neighbour is wet is the right/left corner of that
    #   wet quad and sits just above the water at -4..-2 (the water line runs
    #   along the quad's horizontal diagonal);
    # - a dry tile whose only wet neighbour is diagonally behind it (U) is a small
    #   bank at +1..+3;
    # - dry tiles with water only in front (E/S/D/R/L) sit at -3..+1.
    # The draws are ranked by a smooth noise field rather than taken independently,
    # so neighbouring bank tiles get similar heights and a row reads as one bank.
    from .noise import fbm
    nz = fbm(wet.shape, int(rng.integers(1 << 30)), 3, 10.0) + 0.15 * rng.random(wet.shape)
    wN = shift(wet, 0, -1); wW = shift(wet, -1, 0); wU = shift(wet, -1, -1)
    wE_ = shift(wet, 1, 0, fill=True); wS_ = shift(wet, 0, 1, fill=True); wD_ = shift(wet, 1, 1, fill=True)
    adj = dry & ndimage.binary_dilation(wet, np.ones((3, 3)))
    side = adj & (wN | wW)                       # tile is the R/L corner of a wet quad behind it
    pat = wE_ * 2 + wS_ * 4 + wD_ * 8            # wet corners of the tile's own quad
    def draw(mask, vals, probs, raise_to=False):
        """Assign heights from a distribution to `mask`, ranked by the noise field.
        `raise_to` lets low ground (z <= 3) rise to the drawn value; otherwise the
        draw can only lower a tile."""
        if not mask.any(): return
        probs = np.asarray(probs, float); probs = probs / probs.sum(); cdf = np.cumsum(probs)
        ranks = np.argsort(np.argsort(nz[mask])) / max(1, int(mask.sum()) - 1)
        v = np.asarray(vals)[np.minimum(np.searchsorted(cdf, ranks), len(vals) - 1)]
        z[mask] = np.where(z[mask] <= 3, v, z[mask]) if raise_to else np.minimum(z[mask], v)
    front = adj & ~side
    draw(front & (pat == 14), [0, 1, 2], [0.4, 0.35, 0.25], raise_to=True)          # cliff tips (Felucca's 0x1C)
    draw(front & ((pat == 10) | (pat == 12)), [-2, -1, 0, 1], [0.3, 0.3, 0.25, 0.15], raise_to=True)
    draw(front & (pat == 8), [0, 1, 2], [0.45, 0.35, 0.2], raise_to=True)           # only D wet (0x1D)
    draw(front & ((pat == 2) | (pat == 4) | (pat == 6)), [-3, -2, -1], [0.35, 0.40, 0.25])
    draw(front & (pat == 0), [1, 2, 3], [0.35, 0.4, 0.25], raise_to=True)          # only U wet: a small bank
    draw(side, SIDE_Z[0], SIDE_Z[1])
    # A side bank's z is the corner the wet quads behind it stretch up to, and
    # the foam statics all sit at -5 with limited sprite height. Above -3 the
    # stretched beach quad out-draws the foam and the waterline shows a bare
    # sharp point; lowering the bank to -3 puts the foam back on both adjacent
    # corners. The clamp makes the draw honour Felucca's -4..-2 side banks.
    z[side] = np.minimum(z[side], -3)
    z[adj] = np.minimum(z[adj], 2)
    # ---------------- corner pattern of every tile
    wE = shift(wet, 1, 0, fill=True); wS = shift(wet, 0, 1, fill=True); wD = shift(wet, 1, 1, fill=True)
    corner = (wet.astype(np.uint8) | (wE.astype(np.uint8) << 1) | (wS.astype(np.uint8) << 2) | (wD.astype(np.uint8) << 3))
    sid = np.zeros(wet.shape, np.uint16)   # water static id per tile (0 = none); all at z=-5
    def setid(mask, ids, probs=None):
        if mask.any(): land_id[mask] = _choose(rng, mask, ids, probs)
    def setstatic(mask, ids, probs=None):
        if mask.any(): sid[mask] = _choose(rng, mask, ids, probs)
    # ---- mixed quads: the family follows the beach material - the tile's own
    # material when it is dry, that of the nearest dry tile when it is wet
    if material is None:
        fam_code = np.zeros(wet.shape, np.uint8)
    else:
        # fam_code is only read where c is a mixed pattern (the FAM_* keys are 1..14
        # and SNOW_BLOCK_PATTERNS lie among them), i.e. within a couple of tiles
        # of dry ground, so the nearest-dry lookup is restricted to those tiles
        idx0 = ndimage.nearest_indices(wet, (corner != 0) & (corner != 15))
        mat_near = material[idx0[0], idx0[1]]
        fam_code = np.zeros(wet.shape, np.uint8)
        fam_code[mat_near == MAT_SAND] = 1; fam_code[mat_near == MAT_SNOW] = 2; fam_code[mat_near == MAT_DIRT] = 3
    c = corner
    for fcode, fam in ((0, FAM_GRASS), (1, FAM_SAND), (2, FAM_SNOW), (3, FAM_DIRT)):
        for pat, (ids, p) in fam.items():
            m = (c == pat) & (fam_code == fcode)
            setid(m, ids, p)
    # Felucca's correctly oriented snow corner pieces are not flagged
    # Impassable. Pair them with an invisible blocking static on sunk wet
    # corners so they keep their art without opening a walkable dropoff.
    snow_block = wet & (fam_code == 2) & np.isin(c, SNOW_BLOCK_PATTERNS)
    # Wet sunk tiles always need water at -5. Dry foam sits on shore-quad tiles
    # up to z = 0: Felucca's grass river banks keep z 0 and still carry their
    # curls in 78-93 % of matching contexts; the quad slopes down to the water,
    # so the -5 static stays visible.
    for pat, (ids, probs) in WET_STATIC_RULES.items():
        setstatic(wet & (c == pat), ids, probs)
    # Patterns 11 and 13 each occur in three geometrically different shoreline
    # contexts. Their aggregate Felucca counts look probabilistic, but
    # conditioning on the 8-neighbour wet mask makes the art orientation
    # deterministic. Collapsing them into one distribution produced floating
    # half-diamond foam sprites on side-facing coasts.
    wm = dir_mask(wet)
    # Mixed quads whose wet context contains the full straight-shoreline set take
    # the straight waterline foam - a SUPERSET match, not an exact one. Felucca's
    # exact contexts use the corner arcs (0x17A9/0x17AB) and stacked curls
    # (0x17AD/0x17AE) there, but those pieces read as detached wisps on narrow
    # rivers: the arc art floats off the cliff foot, and the cliff-foot ring
    # tiles that carry Felucca's connecting foam skirt on broad coasts are
    # themselves mixed quads here (the opposite bank pollutes their corner
    # pattern), so the skirt never appears. Straight foam on every shore-touching
    # mixed tile gives a continuous waterline, and the superset match is what
    # dresses the narrow-river foot tiles too.
    # Coverage class matters more than orientation (see the module docstring):
    # full diamonds can replace object water outright; strips need watery land
    # art beneath them; curls expose the land art if placed alone on a wet tile.
    # - Exact straight contexts take Felucca's straight strips (the family's
    #   dropoff art beneath is watery there).
    # - Staircase-run tiles take the full arc pieces, SOLO. Felucca's own answer
    #   for these contexts is the arc 70 %+ of the time, and every curl stacked
    #   on top of it (0x17AD/0x17AE, 0x17A5/0x17B2, 0x17A8/0x17B0) reads as a
    #   smudge over the arc's own baked-in foam, while every partial-coverage
    #   alternative exposes seafloor through the transparency. The arc IS the
    #   dressing.
    # - Foot classes, straight vertical shores and tips stay plain object water,
    #   as in Britannia.
    m3 = wet & (c == 3)
    setstatic(m3 & (wm == (N | R | E)), [0x17A3, 0x17A4])
    setstatic(m3 & (wm == (N | R | E | U)), [0x17AB])
    setstatic(m3 & (sid == 0), OBJW)
    m5 = wet & (c == 5)
    setstatic(m5 & (wm == (S | L | W)), [0x179F, 0x17A0])
    setstatic(m5 & (wm == (S | L | W | U)), [0x17A9])
    setstatic(m5 & (sid == 0), OBJW)
    m11 = wet & (c == 11)
    setstatic(m11 & (wm == (N | R | E | D)), [0x17A3, 0x17A4])
    setstatic(m11 & (wm == (N | R | E | D | U)), [0x17AB])
    setstatic(m11 & (wm == (N | R | E | D | L | W | U)), [0x17AB])   # dry to the S only (bench: island scenes)
    setstatic(m11 & (sid == 0), OBJW)
    m13 = wet & (c == 13)
    setstatic(m13 & (wm == (D | S | L | W)), [0x179F, 0x17A0])
    setstatic(m13 & (wm == (D | S | L | W | U)), [0x17A9])
    setstatic(m13 & (wm == (N | R | D | S | L | W | U)), [0x17A9])   # dry to the E only (bench: island scenes)
    setstatic(m13 & (sid == 0), OBJW)
    # Foot-class land: on these tiles the family's dropoff art drapes its sand
    # out over open water at convex corners, where the eye expects solid water.
    # Felucca's own plurality here is water-land (~40 % on the two-dry variants)
    # and deep seafloor 0x64 on the single-dry variants - both AlwaysFlat and
    # dark, so nothing pokes through. Their dry contact is only ever S/E/L/R,
    # never N/W, which check_water still forbids for water-land.
    # Felucca's corner table puts a mixed tile that takes water-land at z -5,
    # not -15: AlwaysFlat at the water plane, so the flat diamond tiles
    # seamlessly with the surrounding -5 water statics. Leaving it sunk opens a
    # hole at convex corners.
    foot11 = m11 & (wm == (N | R | E | D | W | U))
    setid(foot11, WATER_LAND); z[foot11] = SEA_Z
    setid(m11 & (wm == (N | R | E | D | L | W | U)), [0x64])
    foot13 = m13 & (wm == (N | D | S | L | W | U))
    setid(foot13, WATER_LAND); z[foot13] = SEA_Z
    setid(m13 & (wm == (N | R | D | S | L | W | U)), [0x64])
    dm = dir_mask(dry)
    for pat, contexts in DRY_OVERLAY_RULES.items():
        for wet_mask, (ids, probs, chance) in contexts.items():
            eligible = dry & (c == pat) & ((wm & wet_mask) == wet_mask) & (z <= 0)
            if dry_overlay_exclude is not None:
                eligible &= ~dry_overlay_exclude
            chosen = eligible & (rng.random(wet.shape) < chance)
            setstatic(chosen, ids, probs)
    # ---- fully wet quads: by ring distance to dry land
    allwet = wet & (c == 15)
    k = ndimage.distance_transform_cdt(wet, metric="chessboard")  # chessboard distance to the nearest dry tile
    k1 = allwet & (k == 1)
    def has(bits): return (dm & bits) == bits
    def only(bits): return dm == bits
    # Diagonal-only contacts are PLAIN OPEN WATER, built exactly like mid-ocean
    # (deep seafloor 0x64/0x65 at -15 under an object-water static at -5).
    # Every other treatment of these tiles fails in the client: sandy seafloor
    # smears sand, sunk water-land opens holes, arcs add foam where there is no
    # shore, and bare flat water-land at -5 has no static, so the cursor reads
    # LAND and its flat diamond edge draws a hairline against the foam quad. The
    # deep-ocean recipe is indistinguishable from the surrounding water by
    # definition.
    diag = k1 & (only(R) | only(L))
    setid(diag, [0x64, 0x65], [0.99, 0.01])
    setstatic(diag, OBJW)
    done0 = diag
    rules = [  # (condition on the dry mask, land ids, probs, static ids, probs) - first match wins
        (has(L | W | U) & ~has(N), [0x53, 0x4F], [0.87, 0.13], [0x17A3, 0x17A4], None),
        (has(N | R | U) & ~has(W), [0x50, 0x4D], [0.87, 0.13], [0x179F, 0x17A0], None),
        (has(N | W | U), [0x4C], None, [0x17AF, 0x17A6], None),
        (only(W | U), [0x53], None, [0x17A3, 0x17A4], None),
        (only(N | U), [0x50], None, [0x179F, 0x17A0], None),
        (only(U), [0x54], None, [0x17AC], None),

        (only(L | W) | only(W), [0x4F, 0x53], [0.5, 0.5], [0x17AB], None),
        (only(N | R) | only(N), [0x4D, 0x50], [0.5, 0.5], [0x17A9], None),
        (has(U), [0x4C], None, [0x17AF, 0x17A6], None),
        (has(W), [0x53], None, [0x17A3, 0x17A4], None),
        (has(N), [0x50], None, [0x179F, 0x17A0], None),
    ]
    done = np.zeros(wet.shape, bool) | done0
    for cond, ids, p, sids, sp in rules:
        m = k1 & cond & ~done
        setid(m, ids, p); setstatic(m, sids, sp); done |= m
    m = k1 & ~done; setid(m, [0x64]); setstatic(m, OBJW)
    # rings 2 and 3: the seafloor id faces the nearest dry tile (Euclidean).
    # The nearest-dry lookup is only read on the k == 2 and k == 3 rings.
    idx = ndimage.nearest_indices(wet, allwet & (k == 2) | (allwet & (k == 3)))
    X, Y = np.meshgrid(np.arange(Wd), np.arange(Hd), indexing="ij")
    ddx = np.sign(idx[0] - X); ddy = np.sign(idx[1] - Y)
    def dirsel(dx, dy): return (ddx == dx) & (ddy == dy)
    k2 = allwet & (k == 2)
    for (dx, dy), ids in {(-1, 0): [0x5F], (1, 0): [0x51], (0, -1): [0x5C], (0, 1): [0x52], (-1, -1): [0x60],
                          (1, 1): [0x56], (1, -1): [0x55, 0x59], (-1, 1): [0x57, 0x5B]}.items():
        m = k2 & dirsel(dx, dy); setid(m, ids); setstatic(m, OBJW)
    m = k2 & (sid == 0); setid(m, [0x64]); setstatic(m, OBJW)
    k3 = allwet & (k == 3)
    for (dx, dy), ids in {(1, 0): [0x5D], (0, 1): [0x5E], (1, -1): [0x61], (-1, 1): [0x63], (1, 1): [0x5A, 0x62]}.items():
        m = k3 & dirsel(dx, dy); setid(m, ids); setstatic(m, OBJW)
    m = k3 & (sid == 0); setid(m, [0x64]); setstatic(m, OBJW)
    deep = allwet & (k >= 4) & (k <= 6)
    setid(deep, [0x64, 0x65], [0.99, 0.01]); setstatic(deep, OBJW)
    k7 = allwet & (k == 7)
    coin = rng.random(wet.shape) < 0.55
    m = k7 & ~coin; setid(m, [0x64]); setstatic(m, OBJW)
    wl = (allwet & (k >= 8)) | (k7 & coin)
    setid(wl, WATER_LAND); z[wl] = SEA_Z
    # The wedge: the client folds a quad whose E/S/D corner reads more than
    # ~5 z above its own z, and between that fold, a flat foot tile at -5 and a
    # dry bank the wedge is unpainted background (it shows as a solid black
    # sliver along the shore). It cannot be painted from below either, because
    # CanDrawStatic hides a static sitting 5 or more below the land average. So
    # the trench STEPS at these junctions: a sunk tile touching both dry land
    # and water-land sits on a -8 shelf, close enough that no quad folds open.
    # Only z changes here; the art, statics, dropoff drapes and the foot recipe
    # stay as they are, because the sunk drape under the foam is what hides the
    # seafloor.
    surface = wet & (z == SEA_Z)
    shelf = (wet & (z == TRENCH_Z)
             & ndimage.binary_dilation(dry, np.ones((3, 3)))
             & ndimage.binary_dilation(surface, np.ones((3, 3))))
    z[shelf] = SHELF_Z
    # A shelf quad still folds if a dry corner it reads (its E/S/D neighbour)
    # sits more than 5 z above the shelf. Desert banks draw at 0..+2 and, unlike
    # the banks in every drape-covered case, have no deep corner of their own to
    # drape over the gap. Clamp them to SHELF_Z + 5 = -3, inside the -4..0 range
    # the bank draws already use.
    bank = dry & (shift(shelf, -1, 0) | shift(shelf, 0, -1) | shift(shelf, -1, -1))
    z[bank] = np.minimum(z[bank], SHELF_Z + 5)
    # ---------------- build the statics array
    xs, ys = np.nonzero(sid)
    bx, by = np.nonzero(snow_block)
    dtype = [("id", "<u2"), ("x", "<u2"), ("y", "<u2"), ("z", "i1"), ("hue", "<u2")]
    st = np.empty(len(xs) + len(bx), dtype=dtype)
    nwater = len(xs)
    st["id"][:nwater] = sid[xs, ys]; st["x"][:nwater] = xs; st["y"][:nwater] = ys
    st["z"][:nwater] = SEA_Z; st["hue"][:nwater] = 0
    st["id"][nwater:] = INVISIBLE_BLOCKER; st["x"][nwater:] = bx; st["y"][nwater:] = by
    st["z"][nwater:] = z[bx, by]; st["hue"][nwater:] = 0
    return st

def check_water(wet, z, land_id, st):
    """Invariants of an encoded shoreline, as counts of violations (all should be 0):
    every sunk (-15) tile carries a water static; no water-land tile has dry land to
    its N or W; no sunk tile touches both dry land and surface water (the wedge
    shape encode_water lifts onto the shelf). Also reports the water static count."""
    water_static = (st["id"] >= 0x1796) & (st["id"] <= 0x17B2)
    has = np.zeros(wet.shape, bool); has[st["x"][water_static], st["y"][water_static]] = True
    sunk = wet & (z == TRENCH_Z)
    missing = sunk & ~has
    wl = np.isin(land_id, WATER_LAND)
    dry = ~wet
    cardinal = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)
    wE = shift(wet, 1, 0, fill=True)
    wS = shift(wet, 0, 1, fill=True)
    wD = shift(wet, 1, 1, fill=True)
    corner = wet.astype(np.uint8) | (wE.astype(np.uint8) << 1) | (wS.astype(np.uint8) << 2) | (wD.astype(np.uint8) << 3)
    intentional_surface = corner == 15
    # Water-land with dry to the N or W is the visually broken case (the
    # stretched neighbour quad opens a gap on the visible side); Felucca itself
    # has 62k water-land tiles cardinally adjacent to dry land, so S/E
    # adjacency (the foot classes) is allowed.
    nw_dry = shift(dry, 0, -1) | shift(dry, -1, 0)
    wl_adj = wl & nw_dry & ~intentional_surface
    # The wedge shape: a trench-z tile touching both dry land and surface
    # water. encode_water puts every one of these on the -8 shelf; none may
    # survive.
    surface = wet & (z == -5)
    wedge = (sunk & ndimage.binary_dilation(dry, np.ones((3, 3)))
             & ndimage.binary_dilation(surface, np.ones((3, 3))))
    return {"sunk_without_static": int(missing.sum()), "waterland_adjacent_dry": int(wl_adj.sum()),
            "wedge_shapes": int(wedge.sum()),
            "water_statics": int(water_static.sum())}
