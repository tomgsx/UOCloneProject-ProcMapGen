# Verification

## The contract

**A given seed with given settings always produces byte-identical MUL files:**
across thread counts, across Linux and Windows, from source or from a release
build. The reference world is seed 7 with the default settings
(`presets/default.json`):

| File | SHA-256 |
| --- | --- |
| `map0.mul` | `365347c16b1f48339ce4b5ec1807ae965995b8b82ecc616412d1d3754018e2f9` |
| `staidx0.mul` | `8080654a19dfef6c3ccae686da4a12748f2f7fa46606e87ffafa6c330784a5a4` |
| `statics0.mul` | `28652f06b9858e45990b191477a68c966340b78ab9cdfdc10ff18173730458ac` |

Any change to `gen/` or `uo/` must reproduce these hashes before it ships. A
change that is meant to alter the output re-baselines them here, in the same
commit, with a note of what changed. The output these hashes describe:

- the shoreline ruleset of `gen/water.py`: sunk beds, the measured shore
  heights and corner-pattern art per beach family, the -8 shelf between dry
  land and water-land, side banks clamped to -3 and below;
- coast smoothing radius 2, ramp slope 2, and the rest of the default
  settings;
- three over-wide desert props excluded from the vegetation palette;
- bridges as axis-aligned decks grown until clear of the shore, with the
  full-width road apron, straight 4-tile run-ups and smoothed approaches.

## Running the gate

```bash
python3 -m unittest discover -s tests                  # 40 tests, under a second
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
  and on 1.
- **Operating system does not affect output.** The frozen Windows build
  generated the seed-7 world (run under Wine on the Linux build host and
  natively on Windows) with the same three hashes, and its headless preview
  is pixel-identical to the Linux build's.
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
