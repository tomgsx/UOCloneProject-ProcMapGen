# How the app works

A desktop GUI that generates complete, playable Ultima Online worlds —
`map0.mul`, `staidx0.mul`, `statics0.mul` (Felucca-sized, 896×512 blocks =
7168×4096 tiles) — from a seed and a handful of sliders, using rules measured
from the real Felucca map (the measurements live in `docs/`).

## The layers

```
gui/     PySide6 desktop app + child-process orchestration
gen/     the generator: pure NumPy/SciPy, no Qt         ← all the interesting parts
uo/      UO file formats: readers (tiledata/art/map) and .mul writers
tools/   scripts for looking at a generated world (need the client's art)
tests/   the unit tests (python3 -m unittest discover -s tests)
docs/    the Felucca measurements the rules were tuned against (docs/README.md)
out/     the data tables the generator loads (transition kits, prop catalogue)
```

- `gen/` never imports Qt, so the whole generator runs headless
  (`python3 -m gen.pipeline`, or the frozen binary's `--headless-*` flags).
- `uo/` needs a legally obtained UO installation (the Classic Client from
  https://uo.com/client-download/) for `tiledata.mul` only (passed via the
  `UO_CLIENT_DIR` environment variable); no proprietary assets are bundled or
  written.
- Every module starts with a docstring saying what it reads and writes and
  the terms it uses; the ones in `gen/water.py` and `gen/roads.py` define the
  vocabulary (corner pattern, sunk tile, shelf, deck, apron, run-up).

## The GUI process model

`gui/app.py` (`MainWindow`) never generates anything itself. Generate
Preview / Generate World spawn a **child process** (`multiprocessing`, spawn
context — identical semantics on Linux and Windows) running an entry point in
`gui/tasks.py`. The child streams `("log", …)` / `("progress", …)` events
back over a queue; the GUI polls it on a timer, so the window stays live and
**Cancel** simply terminates the child.

A world is written into `<output>/seed_<seed>_<timestamp>.partial/` and
renamed to its final name only on success; a cancelled run is retained with a
`.cancelled` suffix for diagnostics, so a completed-looking folder is always a
complete world. `gui/paths.py` resolves everything relative to the executable
(`portable-settings.json`, default `output/`), which is what makes the folder
portable. Presets are plain JSON via `gui/config_io.py`; every tunable lives
in one dataclass, `gen/config.py`, and its label, group, tooltip and range in
one `Setting` table in `gui/config_io.py` - the form's boxes, the tooltip's
quoted range and the validator all read that one record. Presets written by
older releases still load: retired keys (`sea_z`, `trench_z`) are dropped and
`lake_hole_range` becomes `min_lake_size`.

The preview runs only the macro stages (continent → terrain → DEM → biomes)
and renders `overview.png`; rivers, roads, shore detail and statics appear in
full generation.

## The generation pipeline

`gen/pipeline.py` runs the stages in a fixed order, all operating on
full-resolution NumPy arrays indexed `[x, y]` (shape 7168×4096):

1. **macro** (`macro.py`) — continent mask from warped fBm over an ellipse
   plus islands; lakes from landmass holes; hill/mountain classes; a terraced
   DEM with ramp-slope cones; biome fields (forest/jungle/desert/snow/swamp)
   by moisture + temperature (a profile along the map's height, plus noise),
   each fenced into its latitude band, its front standing in from the fence
   by a varying depth.
2. **hydro** (`hydro.py`) — rivers routed with Dijkstra over a cost raster
   (plains cheap, hills dear, rock blocked) from hill-foot springs to the
   sea, widening downstream; extra lakes.
3. **roads** (`roads.py`, `routing.py`) — town sites scored and spaced, MST
   over pairwise Dijkstra distances plus shortcut links, cost-routed and
   meandered road paths, graded road beds, straightened water crossings.
4. **tiles** (`tiles.py`) — every tile gets a concrete land id: pure material
   variants plus Britannia's transition kits decoded per corner pattern.
5. **water** (`water.py`) — the measured coast anatomy: sunk −15 beds, the
   exact shore-height distributions, corner-pattern shore quads per beach
   family (grass/sand/snow/dirt), foam statics, ring-distance seafloor bands,
   water statics at −5.
6. **bridges** (in `pipeline.py`) — plank decks with rails over the wet runs
   of each road.
7. **statics** (`statics.py`) — vegetation from a curated prop library
   (multi-part trees included), density per biome, kept clear of roads,
   plazas and bridges.
8. **write + validate** (`uo/map.py`, `validate.py`) — MUL emission, then
   Felucca-derived metrics and a ClassicUO-style walkability check, saved as
   `metrics.json`.

The stage rules were tuned against measurements of the real Felucca
(`docs/elevation.md`, `land-taxonomy.md`, `water-bodies.md`, …; the index is
`docs/README.md`); the generator is one re-runnable pipeline with no manual
fix-up passes.

## Determinism — the project's contract

**A given seed always produces byte-identical MUL files** — across thread
counts, across Linux/Windows, source or frozen. The seed-7 reference hashes
are in `VERIFICATION.md`, and any change to `gen/` or `uo/` must reproduce
them. One `np.random.default_rng(seed)` is threaded through the pipeline, so
the *order* of RNG draws is part of the contract; that is why stages are
never reordered and why parallelism lives below the algorithm, not across it.

## Multithreading (`gen/accel.py`)

The generator uses every core by default (`MAPGEN_THREADS` caps it) without
affecting output. Three exact-by-construction mechanisms, each verified
bit-identical against its serial original:

- **Row-band tiling with a halo** for binary morphology and gaussian
  filtering — an output row depends only on input rows within the kernel
  radius, so bands with that halo equal the global result. Noise
  (`gen/noise.py`) is banded the same way: Perlin values depend only on
  absolute lattice coordinates.
- **Exact Euclidean distance transforms** via the multithreaded `edt`
  package — squared distances are integers with a unique minimum, so any
  exact EDT yields the same values, and `sqrt` of the same integer in
  float64 is bit-deterministic.
- **Read-localized feature transforms** — the nearest-source *index* lookups
  (material fills, rock foot profiles, shore families) keep scipy for its
  tie-breaking, but run it on small crops around where the result is
  actually read, in parallel. Safe because scipy's tie-break is
  translation-invariant (verified: zero mismatches over 1.5M+ localizable
  pixels of dense random masks).

Dijkstra routing stays serial on purpose: scipy's implementation holds the
GIL, and each accepted river extends the target set of the next, so
parallelising it would change which worlds get generated.

Net effect on a 32-core machine: a full world in ~75 s (was ~230 s serial),
a preview in ~19 s (was ~84 s).

## Output folder anatomy

```
output/seed_7_20260827-153000/
  map0.mul, staidx0.mul, statics0.mul   the playable world
  overview.png                          biome/elevation map, 1 px per 8 tiles
  gen_state.npz                         material/z/wet/road masks for tooling
  meta.json                             towns, road edges, river lengths
  metrics.json                          Felucca-metric + walkability report
  config.json                           the exact settings used
  generation.log                        the stage log
```
