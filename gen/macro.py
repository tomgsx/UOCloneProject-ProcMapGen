"""Stage 1, the macro layout: continent and lakes, hill and mountain masks, the
terraced height map, biomes, and the overview image.

Input : the Config (seed, shape and fraction settings).
Output: bool masks and float32/uint8 fields, all indexed [x, y] with shape
        (W, H) = (cfg.width, cfg.height). Heights are in map z units (one unit
        is 4 screen pixels in the client). The targets these rules aim at were
        measured on Felucca (docs/macro-structure.md, docs/elevation.md).

The expensive fields are built at quarter resolution and upsampled; only the
fine coastal roughness and the final morphology run at full size.
"""
import numpy as np
from . import accel as ndimage  # exact-preserving parallel scipy.ndimage
from .noise import fbm, ridged, warp, sample_warped, upsample
from .config import Config

def _ellipse_base(W, H, centre, radii):
    """1 at the ellipse centre, 0 on its edge, negative outside (centre and radii as
    fractions of W and H)."""
    cx, cy = centre[0] * W, centre[1] * H
    rx, ry = radii[0] * W, radii[1] * H
    X, Y = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32), indexing="ij")
    r = np.sqrt(((X - cx) / rx) ** 2 + ((Y - cy) / ry) ** 2)
    return 1.0 - r

def _edge_fade(W, H, margin):
    """0 within `margin` tiles of the map edge, rising to 1 over the next 200 tiles."""
    X, Y = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32), indexing="ij")
    d = np.minimum(np.minimum(X, W - 1 - X), np.minimum(Y, H - 1 - Y))
    return np.clip((d - margin) / 200.0, 0, 1)

def _top_threshold(values, fraction):
    """The score above which the top `fraction` of `values` lies. A fraction past 1
    (a sub-fraction larger than what it is drawn from) selects everything; an empty
    selection selects nothing - np.quantile would raise on either, and both are
    reachable from the settings form (mountains > hills, forest with nothing left).
    Inside [0, 1] the clip is the identity, so tuned worlds are untouched."""
    if len(values) == 0:
        return np.inf
    return np.quantile(values, float(np.clip(1.0 - fraction, 0.0, 1.0)))

def continent(cfg: Config):
    """The dry-land mask and the lake mask (bool [W, H]) at full resolution.

    The continent is an ellipse deformed by warped fractal noise, with extra
    island ellipses dropped into open ocean, faded out toward the map edge,
    smoothed by `coast_smooth`, and cleaned: landmasses below `min_island` go,
    enclosed water pockets become lakes when at least `min_lake_size` or are
    filled otherwise."""
    W, H = cfg.width, cfg.height
    # quarter-resolution shape field, then upsample and add fine coastal detail at full res
    w4, h4 = W // 4, H // 4
    base = _ellipse_base(w4, h4, cfg.centre, cfg.radii)
    n = fbm((w4, h4), cfg.seed + 1, 6, cfg.coast_wavelength / 4, gain=0.55)
    dy, dx = warp((w4, h4), cfg.seed + 2, strength=40.0, wavelength=500.0 / 4)
    n = sample_warped(n, dy, dx)
    field = base + cfg.coast_amp * 1.6 * n
    # islands: small rotated ellipses, each dropped where the field is clearly ocean
    rng = np.random.default_rng(cfg.seed + 3)
    X, Y = np.meshgrid(np.arange(w4, dtype=np.float32), np.arange(h4, dtype=np.float32), indexing="ij")
    for i in range(cfg.islands):
        for _ in range(50):
            ix, iy = rng.uniform(0.12, 0.88) * w4, rng.uniform(0.15, 0.85) * h4
            if field[int(ix), int(iy)] < -0.35: break
        rxi, ryi = rng.uniform(25, 70), rng.uniform(20, 60)
        ang = rng.uniform(0, np.pi)
        Xr = (X - ix) * np.cos(ang) + (Y - iy) * np.sin(ang); Yr = -(X - ix) * np.sin(ang) + (Y - iy) * np.cos(ang)
        ri = np.sqrt((Xr / rxi) ** 2 + (Yr / ryi) ** 2)
        isl = (1.0 - ri) + 0.8 * fbm((w4, h4), cfg.seed + 100 + i, 4, 60.0)
        field = np.maximum(field, isl - 0.15)
    field = upsample(field, 4)[:W, :H]
    if field.shape != (W, H):
        pad = np.full((W, H), -1.0, np.float32); pad[:field.shape[0], :field.shape[1]] = field; field = pad
    # fine coastal roughness (full res)
    fine = fbm((W, H), cfg.seed + 4, 3, 48.0, gain=0.5)
    field = field + cfg.coast_detail * fine
    field -= (1.0 - _edge_fade(W, H, cfg.margin)) * 4.0
    land = field > 0.05
    # coast smoothing: fill water inlets narrower than ~2r (closing), then trim
    # the matching thin land spits (opening at r//2). Runs before the islet /
    # lake logic so a pinched-off inlet correctly becomes a lake.
    r = int(cfg.coast_smooth)
    if r > 0:
        yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
        disk = (xx * xx + yy * yy) <= r * r
        land = ndimage.binary_closing(land, disk)
        r2 = max(1, r // 2)
        yy, xx = np.ogrid[-r2:r2 + 1, -r2:r2 + 1]
        land = ndimage.binary_opening(land, (xx * xx + yy * yy) <= r2 * r2)
    # remove tiny islets, keep holes as lakes if large enough, fill smaller holes
    lab, n = ndimage.label(land)
    sizes = np.bincount(lab.ravel())
    keep = sizes >= cfg.min_island; keep[0] = False
    land = keep[lab]
    holes = ~land
    lab, n = ndimage.label(holes)
    sizes = np.bincount(lab.ravel())
    # every enclosed pocket of water is a lake unless it is too small to be one, in
    # which case it is filled with land; the ocean touches the border and is neither
    border_labels = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    is_ocean = np.zeros(n + 1, bool); is_ocean[border_labels] = True
    lake = np.zeros(n + 1, bool); fill = np.zeros(n + 1, bool)
    for l in range(1, n + 1):
        if is_ocean[l]: continue
        if sizes[l] < cfg.min_lake_size: fill[l] = True
        else: lake[l] = True
    land = land | fill[lab]
    lake_mask = lake[lab]
    return land, lake_mask

def terrain_classes(cfg: Config, land):
    """Where hills and mountains go. Returns (hilly mask, rock mask, hill score field).
    Hills favour inland, rugged ground; mountains are ridged noise inside the hills."""
    W, H = cfg.width, cfg.height
    dist = ndimage.distance_transform_edt(land, sampling=1)  # distance to water
    inland = np.clip(dist / 350.0, 0, 1)
    relief = fbm((W // 4, H // 4), cfg.seed + 5, 5, 700.0 / 4, gain=0.55)
    relief = upsample(relief, 4)[:W, :H]
    score = relief + 0.6 * inland - 0.3
    # hills: the top `hill_fraction` of land by score
    thr_h = _top_threshold(score[land], cfg.hill_fraction)
    hilly = land & (score > thr_h)
    # mountains: ridged noise inside the hilly region, top fraction. mountain_fraction
    # is a share of ALL dry land, so inside the hilly share it is the ratio of the two;
    # a ratio past 1 (more mountain asked for than there is hill) makes every hill rock.
    rid = ridged((W // 4, H // 4), cfg.seed + 6, 5, 420.0 / 4)
    rid = upsample(rid, 4)[:W, :H]
    mscore = rid + 0.5 * (score - thr_h)
    thr_m = _top_threshold(mscore[hilly], cfg.mountain_fraction / max(cfg.hill_fraction, 1e-6))
    rock = hilly & (mscore > thr_m) & (dist > 12)
    # clean the rock: remove slivers, fill holes, minimum thickness ~5, minimum mass 400 tiles
    rock = ndimage.binary_opening(rock, np.ones((5, 5)))
    rock = ndimage.binary_closing(rock, np.ones((5, 5)))
    lab, n = ndimage.label(rock); sizes = np.bincount(lab.ravel()); keep = sizes >= 400; keep[0] = False
    rock = keep[lab]
    rock = ndimage.binary_fill_holes(rock)
    # hilly: soften the edges
    hilly = ndimage.binary_opening(hilly, np.ones((7, 7)))
    return hilly, rock, score

def terrace_dem(cfg: Config, land, hilly, rock):
    """The walkable height map (float32 [W, H]): flat plains at 0, terraces at the
    quantised `hill_levels` joined by ramps of `ramp_slope` z per tile (the upper
    envelope of a cone around each terrace), and ground rising toward the rock masses.
    Rock itself is raised later by rock_profile()."""
    W, H = cfg.width, cfg.height
    z = np.zeros((W, H), np.float32)
    # terrace level field inside the hilly regions
    tf = fbm((W // 4, H // 4), cfg.seed + 7, 4, 260.0 / 4, gain=0.5)
    tf = upsample(tf, 4)[:W, :H]
    tf = (tf - tf[hilly].min()) / (tf[hilly].max() - tf[hilly].min() + 1e-6) if hilly.any() else tf
    # distance from the hill edge, so terraces fade to 0 at the hill region boundary
    dedge = ndimage.distance_transform_edt(hilly)
    lvl_target = tf * np.clip(dedge / 25.0, 0, 1) * max(cfg.hill_levels) * 1.15
    levels = list(cfg.hill_levels)
    # mountains force the surrounding ground up a bit too
    rock_d = ndimage.distance_transform_edt(~rock)
    lvl_target = np.maximum(lvl_target, np.where(rock_d < 90, (1 - rock_d / 90.0) * 25.0, 0))
    # quantise to terrace levels, then ramp: z = max over levels l of (l - slope * dist(p, {target >= l}))
    for l in levels:
        region = hilly & (lvl_target >= l)
        region = ndimage.binary_opening(region, np.ones((7, 7)))
        if not region.any(): continue
        d = ndimage.distance_transform_edt(~region)
        z = np.maximum(z, l - cfg.ramp_slope * d)
    z = np.clip(z, 0, None)
    z[~land] = 0
    return z

def rock_profile(cfg: Config, z, rock):
    """Raise the rock masses above the surrounding ground with Britannia's foot profile
    (docs/elevation.md): steep for the first few tiles, then easing toward a 70 z
    plateau, with a small bump noise. Call after the water mask is final. Returns a
    new z array."""
    W, H = z.shape
    z = z.copy()
    if rock.any():
        din = ndimage.distance_transform_edt(rock)
        ground = z.copy()
        # the surrounding ground level propagated inward (nearest non-rock z); g_in is only
        # ever read where rock is set (base feeds zr, applied under np.where(rock, ...))
        idx = ndimage.nearest_indices(rock, rock)
        g_in = ground[idx[0], idx[1]]
        prof_d = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 24, 40], np.float32)
        prof_z = np.array([0, 2, 10, 18, 26, 33, 38, 42, 45, 48, 50, 54, 60, 70], np.float32)
        p = np.interp(din, prof_d, prof_z)
        base = g_in + p
        # the distance profile has creases along the medial axis; blur the interior (keep the foot exact)
        sm = ndimage.gaussian_filter(np.where(rock, base, 0).astype(np.float32), 5.0) / np.maximum(
            ndimage.gaussian_filter(rock.astype(np.float32), 5.0), 1e-3)
        wgt = np.clip((din - 2) / 8.0, 0, 1)
        base = base * (1 - wgt) + sm * wgt
        bump = fbm((W, H), cfg.seed + 8, 4, 14.0) * 6.0
        zr = base + np.where(din > 2, bump, bump * 0.3)
        z = np.where(rock, zr, z)
    return z

# Temperature profiles (Config.temperature_profile): where the cold ground lies.
# Each profile's zones are its own settings, and PROFILE_HANDLES lists them in
# top-to-bottom order as (setting, index) pairs: the boundaries a user can move.
TEMPERATURE_PROFILES = ("north", "poles")
PROFILE_HANDLES = {
    "north": (("north_zones", 0), ("north_zones", 1)),
    "poles": (("poles_cold", 0), ("poles_heat", 0), ("poles_heat", 1), ("poles_cold", 1)),
}

def _ramp(lat, cold_at, hot_at, cold_above):
    """1 at `cold_at`, 0 at `hot_at`, linear between and clipped outside, in either
    direction; a step at `hot_at` when the two coincide, cold on the side
    `cold_above` names."""
    span = hot_at - cold_at
    if span == 0:
        return ((lat < hot_at) if cold_above else (lat > hot_at)).astype(np.float32)
    return np.clip((hot_at - lat) / span, 0, 1).astype(np.float32)

def coldness(cfg: Config, lat):
    """How cold each row is before noise, 0 warm to 1 cold, from the temperature
    profile and its zones. "north": full cold from the top edge down to the first of
    `north_zones`, full heat from the second down to the bottom edge, a steady change
    between (the defaults 0 and 1 make it one gradient). "poles": full cold above the
    first of `poles_cold` and below the second, full heat between the two of
    `poles_heat`, steady changes between. `lat` is the latitude per tile, 0 at the
    top edge and 1 at the bottom."""
    if cfg.temperature_profile == "poles":
        cold_to, cold_from = cfg.poles_cold
        hot_from, hot_to = cfg.poles_heat
        upper = _ramp(lat, cold_to, hot_from, cold_above=True)
        lower = _ramp(lat, cold_from, hot_to, cold_above=False)
        return np.maximum(upper, lower)
    cold_to, hot_from = cfg.north_zones
    return _ramp(lat, cold_to, hot_from, cold_above=True)

# Each biome is fenced into its band (Config.<name>_band): the part of the map, top
# and bottom as fractions of the map height, outside which it never forms. Inside
# the band its front does not follow the fence's row: it stands in from the fence
# by a depth that varies along it, touching the fence at its furthest points and
# withdrawing into bays elsewhere. Broad noise shapes the bays a thousand tiles
# across, bay-sized noise adds inlets and tongues, and fine noise frays the front.
# The depth fades out toward the map edges, so an edge at 0 or 1 is exactly the map
# edge and costs nothing.
BAND_WANDER = 0.38    # the broad shape of the front, as a fraction of the map height
BAND_BAYS = 0.11      # bays and tongues a few hundred tiles across, same unit
BAND_RAGGED = 0.045   # the fine fraying, same unit
BAND_INSET = 0.35     # how much of that shape becomes depth in from the fence
BAND_DEPTH_SHARE = 0.45   # the most of its band's height a front may stand in
BAND_FRAY_SEED = 17   # seed offset of the fraying noise, shared by every edge
# The seed offsets of the (broad, bays) noise for each biome's (top, bottom) edge,
# distinct so that no two fronts coincide, in the order the biomes are placed.
BAND_SEEDS = {
    "snow": ((200, 201), (15, 16)),
    "desert": ((202, 203), (204, 205)),
    "jungle": ((206, 207), (208, 209)),
    "forest": ((210, 211), (212, 213)),
    "swamp": ((214, 215), (216, 217)),
}
BIOME_BANDS = tuple(BAND_SEEDS)
# The material code each biome paints (gen.materials).
BIOME_MATERIAL = {"snow": 5, "desert": 4, "jungle": 3, "forest": 2, "swamp": 6}

def band_edge(cfg: Config, value, seeds, fray, inward, limit=1.0):
    """The front along one fence of a band, as a latitude per tile (float32 [W, H]):
    the fence at `value`, moved into the band (`inward` is +1 for a top fence, -1 for
    a bottom one) by a depth that is never negative and is zero at the front's
    furthest point, so the front touches the fence but never crosses it. The depth
    is scaled down, keeping its shape, so that it never exceeds `limit` (a share of
    the band's height, so a narrow band keeps an open middle). `seeds` are the seed
    offsets of the broad and the bay noise; `fray` is the fine noise every edge
    shares."""
    W, H = cfg.width, cfg.height
    broad = upsample(fbm((W // 4, H // 4), cfg.seed + seeds[0], 4, 1600.0 / 4), 4)[:W, :H]
    bays = upsample(fbm((W // 4, H // 4), cfg.seed + seeds[1], 3, 300.0 / 4), 4)[:W, :H]
    swing = 4.0 * value * (1.0 - value)   # 1 at the middle of the map, 0 at either edge
    shape = BAND_WANDER * broad + BAND_BAYS * bays + BAND_RAGGED * fray
    depth = swing * BAND_INSET * (shape.max() - shape)
    deepest = float(depth.max())
    if deepest > limit:
        depth = depth * (limit / deepest)
    return (value + inward * depth).astype(np.float32)

def band_mask(cfg: Config, name, lat, cache=None):
    """Where the biome `name` is allowed by its band: bool [W, H], never outside the
    band and standing in from each fence by the front's depth. `lat` is the latitude
    per tile (0 at the top edge, 1 at the bottom). `cache` is a dict the caller keeps
    across biomes so the fraying noise is built once."""
    top, bottom = getattr(cfg, f"{name}_band")
    mask = np.ones(lat.shape, bool)
    if top <= 0.0 and bottom >= 1.0:
        return mask
    if cache is None:
        cache = {}
    fray = cache.get("fray")
    if fray is None:
        fray = cache["fray"] = fbm((cfg.width, cfg.height), cfg.seed + BAND_FRAY_SEED, 3, 50.0)
    top_seeds, bottom_seeds = BAND_SEEDS[name]
    limit = BAND_DEPTH_SHARE * max(bottom - top, 0.0)
    if top > 0.0:
        mask &= lat >= band_edge(cfg, top, top_seeds, fray, inward=1.0, limit=limit)
    if bottom < 1.0:
        mask &= lat < band_edge(cfg, bottom, bottom_seeds, fray, inward=-1.0, limit=limit)
    return mask

def biomes(cfg: Config, land, hilly, rock, z):
    """The material map (uint8 [W, H], gen.materials codes): 0 water, 1 grass, 2 forest,
    3 jungle, 4 sand, 5 snow, 6 swamp, 7 rock. Biomes are chosen by temperature (the
    profile's coldness plus noise) and moisture (noise), each as the top fraction of
    dry land by its own score, in the order snow, desert, jungle, forest, swamp; grass
    is what remains. Each biome is also fenced into its band (`band_mask`) and stands
    in from the fence, so its share can come out below its fraction."""
    W, H = cfg.width, cfg.height
    lat = np.broadcast_to((np.arange(H, dtype=np.float32) / H)[None, :], (W, H))   # 0 north .. 1 south
    temp = -coldness(cfg, lat) + fbm((W // 4, H // 4), cfg.seed + 9, 4, 900.0 / 4).repeat(4, 0).repeat(4, 1)[:W, :H] * 0.5
    # temp is low where the profile is cold; moisture comes from noise
    moist = fbm((W // 4, H // 4), cfg.seed + 10, 5, 600.0 / 4, gain=0.55)
    moist = upsample(moist, 4)[:W, :H]
    fine = fbm((W, H), cfg.seed + 11, 3, 40.0) * 0.12
    moist = moist + fine
    m = np.ones((W, H), np.uint8)  # grass
    dry = land
    bands = {}
    allowed = lambda name: band_mask(cfg, name, lat, bands)
    # snow: the coldest ground
    snow_score = -temp + 0.3 * moist
    thr = _top_threshold(snow_score[dry], cfg.snow_fraction)
    snow = dry & (snow_score > thr) & allowed("snow")
    snow = ndimage.binary_closing(snow, np.ones((9, 9))) & dry
    snow = ndimage.binary_fill_holes(snow) & dry
    lab_s, ns = ndimage.label(snow); sz = np.bincount(lab_s.ravel()); keep = sz >= 4000; keep[0] = False
    snow = keep[lab_s]
    # desert: warm and dry
    des_score = temp - moist + fine
    thr = _top_threshold(des_score[dry], cfg.desert_fraction)
    desert = dry & (des_score > thr) & ~snow & allowed("desert")
    # jungle: warm and wet
    jun_score = temp + moist
    thr = _top_threshold(jun_score[dry], cfg.jungle_fraction)
    jungle = dry & (jun_score > thr) & ~snow & ~desert & allowed("jungle")
    # forest: moist, a share of whatever the three biomes above left
    f_score = moist + 0.15 * fbm((W, H), cfg.seed + 12, 2, 90.0)
    thr = _top_threshold(f_score[dry & ~snow & ~desert & ~jungle], cfg.forest_fraction)
    forest = dry & (f_score > thr) & ~snow & ~desert & ~jungle & allowed("forest")
    # swamp: a few big flat inland patches (Britannia has 3 patches of 15-35k tiles), from low-frequency blobs
    dwat = ndimage.distance_transform_edt(land)
    swamp_field = fbm((W // 4, H // 4), cfg.seed + 13, 3, 900.0 / 4)
    swamp_field = upsample(swamp_field, 4)[:W, :H] + 0.25 * fbm((W, H), cfg.seed + 14, 3, 60.0)
    cand = dry & (z <= 0.5) & ~hilly & ~snow & ~desert & (dwat > 25) & allowed("swamp")
    # the fraction is of all dry land, taken from the qualifying share only
    thr = _top_threshold(swamp_field[cand], cfg.swamp_fraction / max(cand.sum() / dry.sum(), 1e-3))
    swamp = cand & (swamp_field > thr)
    swamp = ndimage.binary_opening(swamp, np.ones((9, 9)))
    lab_w, nw = ndimage.label(swamp); szw = np.bincount(lab_w.ravel()); keepw = szw >= 5000; keepw[0] = False
    swamp = keepw[lab_w]
    m[forest] = 2; m[jungle] = 3; m[desert] = 4; m[snow] = 5; m[swamp] = 6
    m[rock] = 7
    m[~land] = 0
    return m

def clean_material(m, min_width=3, protect=(0, 7), min_area=60):
    """Morphological cleanup so every biome patch is at least `min_width` wide, has no 1-tile fingers,
    and no patch is smaller than `min_area` tiles. Removed tiles take the nearest surviving
    material; `protect` materials are left as they are."""
    k = np.ones((min_width, min_width), bool)
    out = m.copy()
    for mat in np.unique(m):
        if mat in protect: continue
        mask = out == mat
        opened = ndimage.binary_opening(mask, k)
        lab_, n_ = ndimage.label(opened); sz_ = np.bincount(lab_.ravel()); big_ = sz_ >= min_area; big_[0] = False
        opened = big_[lab_]
        removed = mask & ~opened
        if removed.any():
            # reassign removed tiles to the nearest other material
            idx = ndimage.nearest_indices(removed, removed)
            out[removed] = out[idx[0], idx[1]][removed]
    return out

# The overview's colour per material code, and its tiles per pixel.
OVERVIEW_PALETTE = {0: (20, 60, 120), 1: (80, 140, 60), 2: (40, 90, 40), 3: (30, 110, 70), 4: (210, 190, 120),
                    5: (235, 235, 240), 6: (70, 90, 50), 7: (120, 115, 110), 8: (140, 100, 60), 9: (170, 130, 90), 10: (40, 70, 130)}
OVERVIEW_SCALE = 8

def overview_png(m, z, path, scale=OVERVIEW_SCALE):
    """The overview image: one pixel per `scale` tiles, the material palette shaded by
    slope. This is the generator's own drawing, not client art."""
    from PIL import Image
    pal = OVERVIEW_PALETTE
    sm = m[::scale, ::scale]; sz = z[::scale, ::scale]
    img = np.zeros(sm.shape + (3,), np.uint8)
    for k, c in pal.items(): img[sm == k] = c
    shade = np.clip(1.0 + (sz - np.roll(sz, 1, 0) - np.roll(sz, 1, 1)) * 0.02, 0.6, 1.4)
    img = np.clip(img * shade[..., None], 0, 255).astype(np.uint8)
    Image.fromarray(img.transpose(1, 0, 2)).save(path)
