# The measurements behind the generator

Every rule in `gen/` was tuned against numbers taken from the real Felucca map
(the classic 7168 x 4096 `map0` of Ultima Online). These documents record
those numbers. They are the reference a maintainer needs when a rule looks
arbitrary: the rule is usually reproducing a distribution written down here.

| Document | What it measures | Consumed by |
| --- | --- | --- |
| `macro-structure.md` | Land and water fractions, landmass sizes, hill and mountain shares, biome areas and shapes, settlement spacing | `gen/macro.py`, `gen/config.py` defaults |
| `elevation.md` | Heights per material, terrace levels, ramp slopes, the rock foot profile, corner-difference histograms | `gen/macro.py` (terraces, `rock_profile`), `gen/validate.py` reference values |
| `land-taxonomy.md` | Every land id with 20+ uses: material, role (pure, variant, transition, floor), art colour, neighbour context | `gen/materials.py`, the tables in `out/transitions/` |
| `transitions.md` | How Britannia's transition kits are laid out per material pair, the corner rule, the learned kit tables | `gen/tiles.py` (`KITS`, `Kits`, `decode_corners`) |
| `water-bodies.md` | The coast anatomy: sunk beds, water statics, shore heights, corner patterns per beach family, ring seafloor ids, foam contexts | `gen/water.py` |
| `roads-bridges.md` | Road ids and widths, meander, verges, the bridge layouts (planks, rails, posts) | `gen/roads.py`, `gen/pipeline.py` (`build_bridges`) |
| `vegetation-props.md` | The natural-statics catalogue: which props sit on which land, densities, multi-part trees | `gen/statics.py`, `out/vegetation-props/props.json` |
| `render-spec.md` | How CentrED# and the client draw a tile: projection, stretching, texmap selection, static depth, the hidden-static rule, the walking rule | `tools/cedrender.py`, `gen/validate.py` (`walkability`) |

`macro_overview.png` is the 1/8-scale material map of Felucca that
`macro-structure.md` describes.

## About the scripts the documents mention

The documents name the analysis scripts (`analysis/*.py`) and data products
(`out/<topic>/*.json`) that produced them. Those scripts read the client's map
and art files directly and were a one-off measurement pass; they are **not
part of this repository**, and neither are most of their outputs. What the
generator actually loads is the small set of tables under `out/`:

- `out/transitions/transitions_main.json` and `pure_variants_main.json`, the
  learned transition kits and pure-variant frequencies (`transitions.md`);
- `out/vegetation-props/props.json`, the prop catalogue (`vegetation-props.md`).

These are tables of tile ids, counts and offsets. They contain no art and no
map data.

## The bench islands

`island-tests/*.npz` are six small (19 x 19) wet masks - a square island, a
diamond, a staircase, a plus, a notch and a blob - that together exercise
every corner pattern the shoreline rules handle. `tools/bench_publish.py`
re-encodes and renders them, and `tools/notch_battery.py` and
`tools/island_test_map.py` use them as scenes. The rendered PNGs are made
from the client's copyrighted art and are therefore not tracked; generate them
locally when you want to look at a change to `gen/water.py`.
