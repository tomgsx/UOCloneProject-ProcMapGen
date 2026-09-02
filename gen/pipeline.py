"""End-to-end map generation: every stage in its fixed order, then the MUL files.

Usage: python3 -m gen.pipeline --seed 7 --out /path/to/dir
       (needs UO_CLIENT_DIR pointing at a folder with tiledata.mul; the
       metrics stage at the end reads it)

Stages, all on full-resolution arrays indexed [x, y] of shape (W, H):
  1. macro     continent, lakes, hills, mountains, height map, biomes
  2. hydro     rivers and extra lakes, then the coast is cleaned up
  3. roads     towns, road network, road beds, plazas
  4. material  cleanup, buffers between materials that have no transition kit
  5. tiles     land ids: pure variants and transition pieces
  6. water     the shoreline anatomy (heights, ids, water statics)
  7. bridges   plank decks and rails over the straight crossings
  8. statics   vegetation
  9. write     map0.mul, staidx0.mul, statics0.mul, gen_state.npz, meta.json,
               overview.png; then metrics.json

One np.random.default_rng(seed) is threaded through the stages, so the ORDER of
random draws is part of the byte-identical contract (VERIFICATION.md): stages
are never reordered, and parallelism lives below the algorithms (gen/accel.py),
never across them.
"""
import os, sys, time, json, argparse
import numpy as np
from . import accel as ndimage  # exact-preserving parallel scipy.ndimage
from .config import Config
from . import macro, materials as M
from .hydro import plan_rivers, plan_lakes
from .roads import pick_towns, plan_roads, rasterize_roads, grade_roads, plan_decks, deck_apron, RUNUP, BRIDGE_REACH
from .tiles import Kits, assign_pure, decode_corners
from .water import encode_water, check_water, remove_wet_tips, fix_tips
from .statics import PropLibrary, place_props

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANS = os.path.join(ROOT, "out/transitions/transitions_main.json")
PURE = os.path.join(ROOT, "out/transitions/pure_variants_main.json")
PROPS = os.path.join(ROOT, "out/vegetation-props/props.json")

# material pairs that may touch directly (they have a transition kit, or look fine
# without one); any other pair gets a 2-tile buffer of another material between them
ALLOWED = {
    (M.GRASS, M.FOREST), (M.GRASS, M.JUNGLE), (M.GRASS, M.SAND), (M.GRASS, M.ROCK), (M.GRASS, M.SWAMP_RIM), (M.SWAMP, M.SWAMP_RIM), (M.GRASS, M.DIRT),
    (M.GRASS, M.ROAD), (M.FOREST, M.ROCK), (M.JUNGLE, M.DIRT), (M.SAND, M.ROCK), (M.SAND, M.DIRT),
    (M.SAND, M.ROAD), (M.SNOW, M.DIRT), (M.SNOW, M.ROAD), (M.SNOW, M.ROCK), (M.DIRT, M.ROCK), (M.ROAD, M.ROCK), (M.ROAD, M.DIRT),
}
BUFFER_WITH = {M.SNOW: M.DIRT}   # the buffer material per side; grass unless listed here

def log(msg, t0=[time.time()]):
    """Print a stage message with the seconds elapsed since the module loaded. The GUI
    parses these lines for its progress bar (gui/progress.py)."""
    print(f"[{time.time() - t0[0]:6.1f}s] {msg}", flush=True)

def enforce_adjacency(material, land, protect):
    """Insert 2-tile buffers between materials that have no transition kit. Modifies
    `material` in place; `protect` tiles are never changed. Returns (material, tiles changed)."""
    mats = [int(m) for m in np.unique(material) if m not in (M.WATER, M.LAKE)]
    k = np.ones((5, 5), bool)
    changed = 0
    for a in mats:
        for b in mats:
            if a >= b: continue
            if (a, b) in ALLOWED or (b, a) in ALLOWED: continue
            ma = material == a; mb = material == b
            if not (ma.any() and mb.any()): continue
            touch = ma & ndimage.binary_dilation(mb, k)
            if not touch.any(): continue
            buf = BUFFER_WITH.get(a, BUFFER_WITH.get(b, M.GRASS))
            # when the buffer material is one of the pair, only the other side converts;
            # otherwise the tiles of `a` near b and of `b` near a both become the buffer
            ta = touch & ~protect; tb = mb & ndimage.binary_dilation(ma, k) & ~protect
            if buf == a: material[tb] = buf; changed += int(tb.sum())
            elif buf == b: material[ta] = buf; changed += int(ta.sum())
            else:
                material[ta] = buf; material[tb] = buf; changed += int(ta.sum() + tb.sum())
    return material, changed

def run(cfg: Config, out_dir, render=True):
    """Generate a world into `out_dir` (created if needed). Returns the main arrays."""
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(cfg.seed)
    W, H = cfg.width, cfg.height
    log("continent")
    land, lake = macro.continent(cfg)
    log(f"  land {land.mean():.3f} lakes {int(lake.sum())}")
    hilly, rock, score = macro.terrain_classes(cfg, land)
    log(f"  hilly {hilly.mean():.3f} rock {rock.mean():.3f}")
    z = macro.terrace_dem(cfg, land, hilly, rock)
    log(f"  dem max {z.max():.0f}")
    material = macro.biomes(cfg, land, hilly, rock, z)
    material[lake] = M.WATER
    # ---- hydrology
    wet = ~land | lake
    log("rivers")
    rivers, river_wet = plan_rivers(cfg, land, wet, z, rock, rng, n_rivers=cfg.rivers)
    lakes2 = plan_lakes(cfg, land, wet | river_wet, z, rock, rng, n_lakes=cfg.lakes)
    wet = wet | river_wet | lakes2
    log(f"  rivers {len(rivers)} river tiles {int(river_wet.sum())} lake tiles {int(lakes2.sum())}")
    # no 1-tile spits or notches in the coast (they produce pockets and slabs in the shore quads)
    k3 = np.ones((3, 3), bool)
    wet = ndimage.binary_opening(wet, k3); wet = ndimage.binary_closing(wet, k3)
    wet = remove_wet_tips(wet)
    wet = fix_tips(wet)
    wet[:2] = True; wet[-2:] = True; wet[:, :2] = True; wet[:, -2:] = True
    material[wet] = M.WATER
    land = ~wet
    # rock must stay clear of the final water mask, then gets its height profile
    dw = ndimage.distance_transform_edt(~wet)
    rock = rock & (dw > 8)
    rock = ndimage.binary_opening(rock, np.ones((5, 5)))
    lab_r, nr = ndimage.label(rock); szr = np.bincount(lab_r.ravel()); keep_r = szr >= 400; keep_r[0] = False
    rock = keep_r[lab_r]
    material[(material == M.ROCK) & ~rock] = M.GRASS
    material[rock] = M.ROCK
    # coast fade: z -> 0 near any water, slope-limited beyond; then raise the rock masses on the capped ground
    cap = cfg.ramp_slope * np.clip(dw - 8, 0, None)   # flat coastal band (Felucca: the k=2 row is 68 % z=0)
    z = np.minimum(z, cap)
    z[wet] = 0
    z = macro.rock_profile(cfg, z, rock)
    # ---- towns and roads (on the float height map)
    log("towns/roads")
    towns = pick_towns(cfg, land, wet, np.round(z).astype(np.int16), material, rock, rng)
    log(f"  towns {towns}")
    roads, edges, road_stats = plan_roads(cfg, land, wet, np.round(z).astype(np.int16), material, rock, towns, rng)
    log(f"  roads {len(roads)} (crossings rerouted over land {road_stats['rerouted']}, links dropped {road_stats['dropped']})")
    core, centre = rasterize_roads(roads, (W, H), width=cfg.road_width, rng=rng, wet=wet)
    # the road meets each bridge at the deck's full width
    decks, _ = plan_decks(roads, wet)
    core |= deck_apron(decks, (W, H))
    core_dry = core & land
    # road bed grading before anything else
    z = grade_roads(z, core_dry, centre & land, roads)
    z = np.where(rock, z, np.minimum(z, cap))   # banks stay low after grading
    z[wet] = 0
    # town plazas: a dirt disc
    plaza = np.zeros((W, H), bool)
    for tx, ty in towns:
        xx, yy = np.meshgrid(np.arange(max(0, tx - 14), min(W, tx + 15)), np.arange(max(0, ty - 14), min(H, ty + 15)), indexing="ij")
        plaza[xx, yy] |= ((xx - tx) ** 2 + (yy - ty) ** 2) <= 13 ** 2
    plaza &= land
    material[plaza] = M.DIRT
    # road material, with a grass verge through forest, jungle and swamp
    verge = ndimage.binary_dilation(core_dry, np.ones((5, 5))) & ~core_dry & land
    conv = verge & np.isin(material, [M.FOREST, M.JUNGLE, M.SWAMP])
    material[conv] = M.GRASS
    material[core_dry] = M.ROAD
    mat_pre = material.copy()
    # ---- material cleanup
    log("material cleanup")
    protect = core_dry | wet | rock | plaza
    material = macro.clean_material(material, 3, protect=(M.WATER, M.ROAD, M.ROCK))
    material[wet] = M.WATER; material[core_dry] = M.ROAD; material[rock & land] = M.ROCK
    # rock material must match the rock mask (cleanup fills can leak rock onto flat ground)
    material[(material == M.ROCK) & ~rock] = M.GRASS
    material[rock & land] = M.ROCK
    # swamp: the dark core inside, a lighter rim ring 3 tiles wide
    sw = material == M.SWAMP
    if sw.any():
        din_sw = ndimage.distance_transform_cdt(sw, metric="chessboard")
        material[sw & (din_sw <= 3)] = M.SWAMP_RIM
    material, nbuf = enforce_adjacency(material, land, protect)
    material[wet] = M.WATER; material[core_dry] = M.ROAD
    # dry tiles that ended up labelled water (nearest-material fills) take the nearest dry material
    bad = land & (material == M.WATER)
    if bad.any():
        src = land & (material != M.WATER)
        idx = ndimage.nearest_indices(~src, bad)
        material[bad] = material[idx[0], idx[1]][bad]
    # The cleanup fills the notch where a road narrows into a bridge run-up, and the
    # relabel above hands a bank tile the nearest dry material - the road - so the road
    # would arrive a tile wide and off-centre at the deck. Inside the bridge zone the road
    # is exactly its core; stray road goes back to what it was before cleanup.
    k = 2 * BRIDGE_REACH + 1
    zone = ndimage.binary_dilation(centre & wet, np.ones((k, k)))
    stray = zone & land & (material == M.ROAD) & ~core_dry
    material[stray] = mat_pre[stray]
    still = stray & (material == M.WATER)
    if still.any():
        src = land & ~np.isin(material, [M.WATER, M.ROAD])
        idx = ndimage.nearest_indices(~src, still)
        material[still] = material[idx[0], idx[1]][still]
    log(f"  buffered {nbuf} tiles, relabelled {int(bad.sum())} dry water tiles")
    # ---- integer z
    zi = np.round(z).astype(np.int16)
    # ---- tiles
    log("tiles")
    kits = Kits(TRANS, PURE)
    land_id = assign_pure(material, kits, rng)
    land_id, stats, unk = decode_corners(material, land_id, kits, rng)
    if unk: log(f"  unkitted pairs: {{ {', '.join(f'{M.NAMES[a]}|{M.NAMES[b]}: {n}' for (a, b), n in unk.items())} }}")
    # ---- water encoding
    log("water")
    bank = core_dry & ndimage.binary_dilation(wet, np.ones((3, 3)))
    water_st = encode_water(wet, zi, land_id, rng, material, dry_overlay_exclude=bank)
    zi[bank] = 0
    log(f"  {check_water(wet, zi, land_id, water_st)}")
    # ---- bridges
    log("bridges")
    bridge_st, bridge_tiles, crooked = build_bridges(roads, core, wet, zi, rng)
    log(f"  bridge statics {len(bridge_st)}, crooked runs refused {crooked}")
    # ---- vegetation
    log("statics")
    lib = PropLibrary(PROPS)
    exclude = ndimage.binary_dilation(core_dry | plaza, np.ones((3, 3))) | bridge_tiles
    veg_st = place_props(material, zi, wet, core_dry | plaza, rng, lib, exclude_mask=exclude)
    log(f"  vegetation statics {len(veg_st)}")
    statics = np.concatenate([water_st, bridge_st, veg_st])
    zi8 = np.clip(zi, -128, 127).astype(np.int8)
    # ---- write
    log("write")
    from uo.map import write_map_mul, write_statics
    write_map_mul(os.path.join(out_dir, "map0.mul"), land_id, zi8)
    write_statics(os.path.join(out_dir, "staidx0.mul"), os.path.join(out_dir, "statics0.mul"), statics)
    np.savez_compressed(os.path.join(out_dir, "gen_state.npz"), material=material, z=zi8, land_id=land_id, wet=wet, core=core_dry,
                        towns=np.array(towns), rock=rock)
    json.dump({"towns": towns, "edges": edges, "rivers": [len(r) for r in rivers]}, open(os.path.join(out_dir, "meta.json"), "w"))
    macro.overview_png(material, zi, os.path.join(out_dir, "overview.png"), 8)
    # ---- metrics
    from .validate import metrics, report
    m = metrics(land_id, zi8, statics)
    from .validate import walkability
    m.update(walkability(land_id, zi8, statics, towns=towns))
    log("metrics:\n" + report(m))
    json.dump(m, open(os.path.join(out_dir, "metrics.json"), "w"), indent=1)
    return dict(material=material, z=zi8, land_id=land_id, wet=wet, statics=statics, towns=towns, roads=roads, rivers=rivers, core=core_dry)

def build_bridges(roads, core, wet, zi, rng):
    """Plank decks and stone rails over every deck plan_decks() finds. The layout matches
    Britannia's bridges (docs/roads-bridges.md): a full 5-wide plank rectangle over every
    column of the run, bank tiles included, at the highest bank z (never below -3); stone
    rails at deck z + 1 along both outer lines - a post-and-rail on the first tile and
    evenly ~4 apart, plain rail between, the family's corner post on the last tile.
    East-west 0x8F9 / 0x8FB / 0x8F7, north-south 0x8FA / 0x8FC / 0x8F8. Returns
    (statics, mask of deck tiles, crooked runs refused)."""
    W, H = wet.shape
    ids, xs, ys, zs = [], [], [], []
    tiles = np.zeros((W, H), bool)
    DECK = [0x7C9, 0x7CA, 0x7CB, 0x7CC]
    def put(px, py, tid, z):
        if 0 <= px < W and 0 <= py < H:
            ids.append(tid); xs.append(px); ys.append(py); zs.append(z)
    decks, skipped = plan_decks(roads, wet)
    for seg, ew in decks:
        zb = int(max(max(zi[x, y] for x, y in seg), -3))
        POST, RAIL, CORNER = (0x8F9, 0x8FB, 0x8F7) if ew else (0x8FA, 0x8FC, 0x8F8)
        L = len(seg)
        nseg = max(1, int(round((L - 1) / 4.0)))
        posts = {int(round(k * (L - 1) / nseg)) for k in range(nseg)}
        for idx, (x, y) in enumerate(seg):
            piece = CORNER if idx == L - 1 else (POST if idx in posts else RAIL)
            for o in (-2, -1, 0, 1, 2):
                px, py = (x, y + o) if ew else (x + o, y)
                if not (0 <= px < W and 0 <= py < H) or tiles[px, py]: continue
                tiles[px, py] = True
                put(px, py, DECK[rng.integers(0, 4)], zb)
                if abs(o) == 2:
                    put(px, py, piece, zb + 1)
    st = np.empty(len(ids), dtype=[("id", "<u2"), ("x", "<u2"), ("y", "<u2"), ("z", "i1"), ("hue", "<u2")])
    st["id"] = ids; st["x"] = xs; st["y"] = ys; st["z"] = zs; st["hue"] = 0
    return st, tiles, skipped

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=os.path.join(ROOT, "out/gen"))
    a = ap.parse_args()
    cfg = Config(seed=a.seed)
    run(cfg, a.out)
