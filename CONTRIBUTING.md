# Contributing

Thanks for looking at MapGen. This page says how to run it from source, what
the tests and the byte-identical contract are, and what a change needs before
it can be merged.

## Running from source

```bash
git clone https://github.com/tomgsx/UOCloneProject-ProcMapGen.git
cd UOCloneProject-ProcMapGen
python3 -m pip install numpy==2.4.6 scipy==1.18.0 Pillow==12.3.0 PySide6==6.11.1 edt==3.1.2
./run_development.sh            # Linux: the GUI
run_development.cmd             # Windows: the GUI (py launcher)
python3 -m gen.pipeline --seed 7 --out /tmp/seed7    # the generator alone
```

The generator needs `UO_CLIENT_DIR` set to a folder containing `tiledata.mul`
from a legally obtained client install (the Classic Client from
https://uo.com/client-download/) for its final metrics stage (the app sets it
from the folder you select). The
MUL files are written before that stage runs, so a missing client only costs
you `metrics.json`.

## The tests

```bash
python3 -m unittest discover -s tests
```

54 tests, a few seconds, no client files needed (one test reads the client's
`tiledata.mul` and skips itself when `UO_CLIENT_DIR` is unset). The Qt form
tests set `QT_QPA_PLATFORM=offscreen` themselves. The same suite runs on Linux
and Windows in CI (`.github/workflows/ci.yml`).

## The byte-identical contract

A given seed with given settings must always produce the same `map0.mul`,
`staidx0.mul` and `statics0.mul`, byte for byte, on any machine, with any
thread count, from source or from a release build. The reference is seed 7
with the default settings; its three SHA-256 hashes are in `VERIFICATION.md`.

**Any change under `gen/` or `uo/` must reproduce those hashes before it is
merged**, unless the change is meant to alter the output, in which case the
pull request says so, explains why, and updates the hashes in
`VERIFICATION.md` in the same commit. Run the gate like this (about 75 s on a
16-core machine):

```bash
python3 -m gen.pipeline --seed 7 --out /tmp/seed7 && sha256sum /tmp/seed7/*.mul
```

Two consequences of the contract that are easy to break by accident:

- **The order of random draws is part of the output.** One
  `np.random.default_rng(seed)` is threaded through the stages. Reordering
  stages, adding a draw, or consuming the generator in a different place
  changes every world.
- **Parallel code must be exact.** Everything in `gen/accel.py` is a
  drop-in for a `scipy.ndimage` call that returns bit-identical results; the
  arguments for why each one is exact are in its docstring. A new parallel
  primitive needs the same kind of argument and a check against the serial
  original before it ships.

## Comments explain rules, not history

The generator is full of numbers that were measured on the real Felucca map
or chosen after looking at the result in the client. A comment next to such a
number states the rule and why it exists, in the vocabulary of the module's
docstring (corner pattern, sunk tile, shelf, deck, apron, run-up, kit, pure
variant ...). It does not record who asked for it, when, or which attempt it
was; the git history holds that. If a rule only makes sense with an example,
give a coordinate that illustrates it, not one that identifies a bug report.

Every module has a docstring saying what stage it is, what it reads and
writes (array shapes, `[x, y]` indexing, units) and the terms it uses. Keep
it true when you change the module.

## Tools for looking at the result

The scripts in `tools/` need a client install (`UO_CLIENT_DIR`; the Classic
Client from https://uo.com/client-download/) because they render with the
client's art:

- `tools/bridge_check.py <world>`: every bridge is straight, full width and
  railed, and its road runs in straight.
- `tools/world_check.py <world> [x y]`: sampled coastline windows contain no
  unpainted pixels.
- `tools/blackhunt.py`, `tools/notch_battery.py`, `tools/bench_publish.py`:
  the shoreline rules on small scenes and on a world window.
- `tools/verify_release.py --world <world>`: a completed world folder is
  well-formed.

For seeing a world properly, load it into CentrED or a client (README.md,
"Using the world").

## Pull requests

- One topic per pull request.
- The tests pass on Linux and Windows.
- The seed-7 hashes still match, or the request explains the intended change
  in output and updates `VERIFICATION.md`.
- New settings get a `Setting` entry in `gui/config_io.py` with a tooltip that
  says what the setting does in plain language; the GUI tests enforce that
  every `Config` field has one.
- New dependencies are pinned in `pyproject.toml` and
  `requirements-build.txt` and listed in `THIRD-PARTY-NOTICES.md` with their
  license.
- Never commit Ultima Online client files or images rendered from their art.
