# Verification

## The contract

**A given seed with given settings always produces byte-identical MUL files:**
across thread counts, across Linux and Windows, from source or from a release
build. The reference world is seed 7 with the default settings
(`presets/default.json`):

| File | SHA-256 |
| --- | --- |
| `map0.mul` | `ca596c21bb6f451b6f91856a12f107a169fa95b44ca7fb9c4cc1364019eb5780` |
| `staidx0.mul` | `f0c65b644743a115d4b71492775a02d082c6be9e790b570291f291cfd3297f66` |
| `statics0.mul` | `8a0e3d707a6ef084dca3159f1c513798918f0d0938e8aa2b56399424b3be8d1c` |

Any change to `gen/` or `uo/` must reproduce these hashes before it ships. A
change that is meant to alter the output re-baselines them here, in the same
commit, with a note of what changed. The output these hashes describe:

- the shoreline ruleset of `gen/water.py`: sunk beds, the measured shore
  heights and corner-pattern art per beach family, the -8 shelf between dry
  land and water-land, side banks clamped to -3 and below;
- coast smoothing radius 2, ramp slope 2, and the rest of the default
  settings;
- the biome bands (`gen/macro.py` `band_mask`), each a fence the biome never
  crosses with a front that stands in from it by a varying depth, all five
  unlimited by default, under the "coldest at the top and bottom" temperature
  profile with cold zones reaching to 0.10 and from 0.90 and a heat zone of
  0.50 to 0.50;
- three over-wide desert props excluded from the vegetation palette;
- bridges as axis-aligned decks grown until clear of the shore, with the
  full-width road apron, straight 4-tile run-ups and smoothed approaches.

### Re-baselines

- **v1.0.0**: `365347c1…`, `8080654a…`, `28652f06…`.
- **v1.1.0**: the hard latitude cuts that confined snow to the northern
  third of the map, jungle to the southern 45 % and swamp to the southern
  70 % became the biome bands and the temperature profile, and the default
  world was redrawn to show them at work: a slightly smaller continent (radii
  0.30 and 0.32, ocean margin 150, coast variation 0.95, coast feature size
  800), 4 islands, 6 extra lakes, enclosed pockets under 300 tiles filled,
  the two-pole profile with cold zones to 0.10 and from 0.90, snow at 8 %
  and every band open. Nothing of the v1.0.0 reference world survives this;
  the hashes above are of the new one.

## Running the gate

```bash
python3 -m unittest discover -s tests                  # 54 tests, a few seconds
python3 -m gen.pipeline --seed 7 --out /tmp/seed7      # about 75 s on 16 cores
sha256sum /tmp/seed7/*.mul                             # must match the table
```

The pipeline's final metrics stage needs `UO_CLIENT_DIR` to point at a
client folder with `tiledata.mul` (a legally obtained Classic Client,
https://uo.com/client-download/); without it the stage fails after the MUL
files are already written, which does not affect the hashes.

For a release build, the same check through the frozen app (BUILDING.md,
"Verifying a build"):

```bash
./MapGen --headless-world /tmp/world --uo-directory "/path/to/client"
sha256sum /tmp/world/*.mul
```

## What has been verified

- **Thread count does not affect output.** Every parallel primitive in
  `gen/accel.py` was checked bit-identical against its scipy or numpy
  original: tiled binary morphology and gaussian filtering on random masks,
  the `edt` package's exact squared distances, and the localized nearest-index
  transform against more than 1.5 million pixels of dense random masks with
  zero index mismatches. The seed-7 world reproduces the hashes on 32 threads
  and on 4.
- **Operating system does not affect output.** At v1.0.0 the frozen Windows
  build generated the seed-7 world (run under Wine on the Linux build host
  and natively on Windows) with the same three hashes as Linux, and its
  headless preview was pixel-identical to the Linux build's; nothing that
  depends on the platform has changed since.
- **Frozen equals source.** A release build's world matches a source run's
  world and its `metrics.json` exactly.
- **The Windows release runs on Windows.** The natively built bundle
  (`build_windows.ps1` on a Windows runner) was unpacked and launched on a
  Windows machine; the GUI came up. A Wine-built bundle cannot be launched
  under Wine to check this (BUILDING.md), which is why the native build is
  the one released.
- **The app behaves under failure.** Cancelling a world leaves a
  `.cancelled` folder with `CANCELLED.txt` and never a completed-looking
  folder; the frozen GUI launches from a folder with no project on the Python
  path.
- **Presets from older releases load**: retired keys are dropped and
  `lake_hole_range` becomes `min_lake_size` (`gui/config_io.py`).

Timing on a 16-core / 32-thread Linux machine with wide memory bandwidth: a
full seed-7 world in about 75 s (about 230 s single-threaded), a preview in
about 19 s. Desktop machines take longer for the same output; see the
performance note in README.md.
