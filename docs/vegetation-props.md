# Vegetation / natural-prop catalogue (Felucca, measured)

Scripts: `analysis/vegetation_props_01_inventory.py` (static inventory + land under each id), `_02_cooc.py` (3x3 part co-occurrence),
`_03_bigtrees.py` (wide-window mining of composite trees), `_04_catalogue.py` (whitelist, props, per-material stats -> `out/vegetation-props/props.json`),
`_05_roads.py` (road mask + tree distance to roads, `out/vegetation-props/road_mask.npy`).
Data: `out/vegetation-props/props.json` (main product), `static_inventory.json` (all 6023 static ids used in Felucca with land-material histogram),
`cooc_raw.json` / `cooc_wide.json` (raw co-occurrence).

All numbers are from the real Felucca map (7168x4096, void 0x244 excluded, statics 2,912,345). Coordinates: `dx,dy = part.x - anchor.x, part.y - anchor.y`; `dz = part.z - anchor.z`.

## 1. Land materials used
Land ids are classed by tiledata name (`decimated_` prefix stripped): grass, forest (incl. 'leaves' land 0x3AF0-0x3AF8), jungle, sand, snow, rock, dirt, cave,
**swamp = unnamed land 0x3DDB-0x3DF0** (found empirically: cypress trees, lilypads, reeds sit on these), other (void 0x1AE, dungeon floors, embank, sandstone...).
Tile counts: grass 2,899,968, forest 2,476,080, jungle 552,863, sand 319,826, snow 151,203, rock 1,062,760, dirt 532,387, cave 631,716, swamp 136,205, other 727,228.

## 2. Whitelist (natural statics) — 395 ids, 281 placeable anchors + 114 part-only ids
Selection = tiledata name/flags, then verified by where the id sits in Felucca (>=85% on natural land) and by decoding sprites.

| kind | ids (hex) | notes |
|---|---|---|
| tree | 0xccd, 0xcd0, 0xcd3 | tree (forest) (n=39,617) |
| tree | 0xcd6, 0xcd8 | cedar tree (n=29,507) |
| tree | 0xcda, 0xcdd | oak tree (n=26,425) |
| tree | 0xce0, 0xce3 | walnut tree (n=25,644) |
| tree | 0xce6 | willow tree (n=13,177) |
| tree | 0xcf8, 0xcfb, 0xcfe, 0xd01 | cypress tree (swamp) (n=2,018) |
| tree | 0xd94, 0xd98, 0xd9c, 0xda0, 0xda4, 0xda8 | fruit tree (apple/peach/pear) (n=65) |
| tree | 0xc9e | o'hii tree (n=8,648) |
| tree | 0xce9-0xcea | sapling (n=20,986) |
| tree | 0xc95 | coconut palm (n=120) |
| tree | 0xc96 | date palm (n=113) |
| tree | 0xc99-0xc9d | small palm (n=19,113) |
| tree | 0xca6 | ponytail palm (n=1,745) |
| tree | 0xca8 | small banana tree (n=65) |
| tree | 0xcaa-0xcab | banana tree (n=25) |
| tree | 0x1b7e | tuscany pine (snow) (n=392) |
| tree | 0xcc9 | spider tree (n=31) |
| tree | 0xd41, 0xd57, 0xd6e, 0xd84 | jungle tree (composite) (n=16,909) |
| tree | 0x12b6 | Yew tree (composite, giant) (n=80) |
| dead_tree | 0xcca-0xccc | dead tree (bare) (n=18) |
| dead_tree | 0xe56-0xe59 | stump (n=34) |
| part | 0xcce, 0xcd1, 0xcd4, 0xcd7, 0xcd9, 0xcdb, 0xcde, 0xce1, 0xce4, 0xce7, 0xcf9, 0xcfc, 0xd42-0xd56, 0xd58-0xd6d, 0xd6f-0xd83, 0xd85-0xd93, 0xd95, 0xd99, 0xd9d, 0xda1, 0xda5, 0xda9, 0x12b7-0x12c7 | canopy/secondary part (n=303,803) |
| bush | 0xcc8 | juniper bush (n=25) |
| bush | 0xd3f-0xd40 | brambles (n=30,824) |
| bush | 0xc93 | blade plant (n=2,651) |
| bush | 0xc97 | elephant ear plant (n=2,441) |
| bush | 0xc98 | fan plant (n=2,498) |
| bush | 0xca9 | snake plant (n=1,761) |
| bush | 0xc9f-0xca0, 0xca2-0xca4 | fern (n=42,659) |
| bush | 0xca1 | large fern (n=8,259) |
| bush | 0xca5, 0xcc4 | pampas grass (n=3,617) |
| bush | 0xd30-0xd31 | century plant (n=170) |
| bush | 0xd37-0xd38 | yucca (n=137) |
| grass | 0xcac-0xcb6, 0xcb9-0xcbd, 0xcc5-0xcc6, 0xd32-0xd33 | grasses (n=365,674) |
| grass | 0xcc7 | weed (n=6,273) |
| grass | 0xca7 | rushes (n=8,110) |
| grass | 0xc94 | bulrushes (n=2,437) |
| grass | 0x1782-0x1785 | grass tuft (small) (n=2,643) |
| flower | 0xc37-0xc38, 0xc45-0xc4e | flowers (hue-able) (n=5,371) |
| flower | 0xc83, 0xc87, 0xc89 | campion flowers (n=462) |
| flower | 0xc84, 0xc8a | foxglove flowers (n=6,751) |
| flower | 0xc85, 0xcc0-0xcc1 | orfluer flowers (n=7,678) |
| flower | 0xc86 | red poppies (n=240) |
| flower | 0xc8d | white poppies (n=329) |
| flower | 0xc88, 0xc8e | snowdrops (n=345) |
| flower | 0xc8b-0xc8c | white flowers (n=12,669) |
| flower | 0xcbe-0xcbf | poppies (n=210) |
| flower | 0xd29, 0xd2b, 0xd2d, 0xd2f | flowers (n=31,180) |
| flower | 0xd34 | morning glories (n=1,745) |
| flower | 0xd36 | flowers (desert) (n=72) |
| mushroom | 0xd0c-0xd15 | mushrooms (n=34,324) |
| mushroom | 0xd16-0xd19 | mushroom (n=15,672) |
| cactus | 0xd25-0xd28, 0xd2a, 0xd2c, 0xd2e | cactus (n=2,411) |
| cactus | 0xd35 | pipe cactus (n=114) |
| reed | 0xcb7-0xcb8 | cattails (n=4,301) |
| reed | 0xd04 | water plants (n=1,067) |
| reed | 0xd05 | reeds (n=1,836) |
| reed | 0xd06-0xd0b | lilypads (n=4,671) |
| rock | 0x1771-0x177c | rock (small) (n=39,280) |
| rock | 0x1363-0x136d | rock(s) (impassable) (n=3,461) |
| rock | 0x134f-0x1362 | boulder (n=5,124) |
| rock | 0x8e1, 0x8e4 | stalagmites (cave) (n=5,181) |
| rock | 0x2da, 0x2226, 0x222c | crystal (cave) (n=183) |
| other | 0x324c-0x324d | stump (swamp, wet) (n=950) |
| other | 0x324e-0x3251 | sunken log (swamp) (n=1,893) |
| other | 0xcf3-0xcf7 | fallen log (n=52,548) |
| other | 0xd3b-0xd3d | fallen branch (n=27) |
| other | 0x17cd-0x17ce | snow patch (n=617) |
| other | 0xee3-0xee6, 0x10d3, 0x10d6-0x10d7 | spiderweb (cave) (n=1,756) |
| other | 0x1b1f-0x1b26 | leaf litter pile (cave/dirt) (n=1,521) |
| other | 0xeca-0xed2, 0x1ad8-0x1ae4, 0x1b09-0x1b1c | bones/skulls (cave) (n=6,608) |

### Multi-part props (measured co-occurrence)
* **Forest trees** are 2 statics on the SAME tile, same z: trunk + canopy. Pairings (canopy present in 99.5-99.85% of trunks): 0xCCD+0xCCE, 0xCD0+0xCD1, 0xCD3+0xCD4 (generic 'tree'),
  0xCD6+0xCD7, 0xCD8+0xCD9 (cedar), 0xCDA+0xCDB, 0xCDD+0xCDE (oak), 0xCE0+0xCE1, 0xCE3+0xCE4 (walnut), 0xCE6+0xCE7 (willow). The trunk sprite alone is a BARE tree (looks dead).
* **Cypress (swamp)** 0xCF8/0xCFB/0xCFE/0xD01 are complete single sprites (120x184); 'cypress leaves' 0xCF9/0xCFC are optional extra canopy used on 29% / 19% of 0xCF8/0xCFB and ~0% on 0xCFE/0xD01. Emitted as single-part props.
* **Jungle trees are giant diagonal composites** (4 families). Anchor = first trunk slice; the other trunk slices lie at (+1,-1),(+2,-2)... and a set of 'leaves' slices lies along the same diagonal from (-2,+2) to (+5,-5), all at dz=0. Each family has two mutually exclusive leaf sets (~50/50) and optional vine sets (each ~12.5%, so ~50% of trees have one):
  * family A: trunks 0xD41,0xD42,0xD43,0xD44 at (0,0),(1,-1),(2,-2),(3,-3); leaves set0 0xD45-0xD4C at (-2,2)..(5,-5); set1 0xD4D-0xD53 at (-1,1)..(5,-5). n=3,826
  * family B: trunks 0xD57-0xD5B (5 slices, (0,0)..(4,-4)); leaves set0 0xD5C-0xD62, set1 0xD63-0xD69 at (-1,1)..(5,-5). n=3,729 (note 0xD57 also occurs alone 1,814x as the tail of vine set 0xD55/0xD56/0xD57 - never place it as a tree on its own)
  * family C: trunks 0xD6E-0xD72 (0,0)..(4,-4); leaves set0 0xD74-0xD79 at (0,0)..(5,-5), set1 0xD7A-0xD7F at (-1,1)..(4,-4). n=3,794
  * family D: trunks 0xD84-0xD86 (0,0)..(2,-2); leaves set0 0xD87-0xD8B, set1 0xD8C-0xD90 at (-1,1)..(3,-3). n=3,746
  * vine add-ons (relative to anchor, dz=0): {0xD55 (1,-1), 0xD56 (2,-2), 0xD57 (3,-3)}, {0xD6D (1,-1), 0xD6C (2,-2), 0xD6B (3,-3), 0xD6A (4,-4)}, {0xD80,0xD81,0xD82 at (1,-1)..(3,-3)}, {0xD91,0xD92,0xD93 at (1,-1)..(3,-3)} (family D uses offsets shifted by (-1,+1)). Exact per-family part lists with probabilities are in props.json (`optional_vines`).
* **Yew tree** 0x12B6-0x12C7: one giant prop (18 slices along the diagonal (−1,1)..(8,−8), two slices per tile), 80 instances, only in Yew forest. In props.json as anchor 0x12B6.
* Fruit trees 0xD94.. (apple/peach/pear, <15 each), 'tree' 0xCCA-0xCCC (dead, 18 total) and stumps 0xE56-0xE59 (34) are rare in Felucca.
* Every other whitelisted id is a single-part prop (nothing else co-occurs >=70%). The only frequent sub-70% neighbour of forest trunks is grass tuft 0xCAF at (+1,0) (15-18%) - i.e. a grass tuft is often placed just east of a tree.

## 3. Per-material statistics (anchors = placeable ids, land under the anchor tile)

| material | tiles | anchors | props/100 tiles | trees/100 | kind mix (top) | static z == land z | tree NN dist p10/p50/p90 (tiles) | NN<=1 | trees <=1 tile from ANY dirt-road/cobble land id (naive; dirt material is trivially 80%, see road-mask numbers below) |
|---|---|---|---|---|---|---|---|---|---|
| grass | 2,899,968 | 92,865 | 3.202 | 0.373 | grass 47%, flower 14%, tree 12%, bush 10% | 97.05% | 1.41/3.0/6.08 | 8.5% | 0.18% |
| forest | 2,476,080 | 642,414 | 25.945 | 6.009 | grass 49%, tree 23%, flower 8%, other 6% | 99.07% | 1.0/3.0/4.0 | 15.2% | 0.11% |
| jungle | 552,863 | 141,110 | 25.524 | 6.408 | bush 39%, tree 26%, grass 13%, rock 8% | 95.11% | 1.0/2.0/3.61 | 25.5% | 0.13% |
| sand | 319,826 | 7,858 | 2.457 | 0.037 | cactus 30%, grass 28%, flower 26%, rock 9% | 91.63% | 2.24/6.0/21.1 | 4.2% | 0.0% |
| snow | 151,203 | 2,602 | 1.721 | 1.526 | tree 89%, rock 11%, other 1% | 95.27% | 1.0/1.0/1.41 | 73.5% | 0.04% |
| rock | 1,062,760 | 1,143 | 0.108 | 0.012 | rock 53%, other 21%, tree 11%, grass 11% | 15.14% | 1.0/2.83/6.16 | 16.4% | 1.56% |
| dirt | 532,387 | 10,972 | 2.061 | 0.55 | grass 28%, tree 27%, other 16%, rock 13% | 77.99% | 1.0/2.0/8.06 | 41.1% | 79.52% |
| cave | 631,716 | 15,692 | 2.484 | 0.0 | rock 46%, other 43%, mushroom 11%, grass 0% | 71.14% | - | -% | -% |
| swamp | 136,205 | 15,839 | 11.629 | 1.493 | reed 51%, other 18%, grass 13%, tree 13% | 98.93% | 1.0/3.0/6.4 | 14.7% | 0.0% |
| other | 727,228 | 2,957 | 0.407 | 0.021 | other 64%, grass 13%, flower 7%, rock 7% | 80.76% | 1.0/3.0/9.36 | 16.1% | 1.94% |

Britannia (x<5120) vs Lost Lands density per 100 tiles: grass: 5.578 vs 0.235; forest: 26.155 vs 23.365; jungle: 25.764 vs 24.745; sand: 2.047 vs 2.983; snow: 0.006 vs 3.855; rock: 0.072 vs 0.16; dirt: 3.069 vs 1.585; cave: 4.567 vs 2.483; swamp: 6.762 vs 16.966; other: 0.459 vs 0.387.
Grass is 24x denser with props in Britannia than in the Lost Lands (T2A grass is nearly bare); snow only exists in the Lost Lands (Britannia snow: 0.006). Forest/jungle are equal. Use the Britannia values for grass/forest/jungle/dirt and the Lost-Lands value for snow.

Top props per material (weight = share of anchors on that material; full lists in props.json):

* **grass**: 0x0caf grasses 10.2%, 0x0cb0 grasses 9.8%, 0x0cb5 grasses 9.7%, 0x0cb6 grasses 9.6%, 0x0c85 orfluer flowers 1.3%, 0x0ca3 fern 1.3%, 0x1774 rock (small) 1.3%, 0x0d29 flowers 1.3%
* **forest**: 0x0caf grasses 10.3%, 0x0cb0 grasses 8.4%, 0x0cb5 grasses 6.4%, 0x0cb6 grasses 6.4%, 0x0d40 brambles 2.3%, 0x0d3f brambles 2.3%, 0x0cb2 grasses 2.1%, 0x0cb3 grasses 2.1%
* **jungle**: 0x0ca3 fern 6.1%, 0x0ca0 fern 5.1%, 0x0ca1 large fern 5.1%, 0x0ca4 fern 5.1%, 0x0ca2 fern 5.1%, 0x0c9f fern 5.0%, 0x0c9b small palm 2.5%, 0x0c9c small palm 2.5%
* **sand**: 0x0d32 grasses 15.1%, 0x0d33 grasses 11.4%, 0x0d2f flowers 10.4%, 0x0d2d flowers 6.6%, 0x0d2e cactus 6.2%, 0x0d2c cactus 4.3%, 0x0d2b flowers 4.3%, 0x0d28 cactus 4.1%
* **snow**: 0x0cd6 cedar tree 40.6%, 0x0cd8 cedar tree 39.0%, 0x1b7e tuscany pine (snow) 9.1%, 0x177c rock (small) 0.6%, 0x17cd snow patch 0.6%, 0x1362 boulder 0.5%, 0x135c boulder 0.5%, 0x135d boulder 0.5%
* **rock**: 0x08e1 stalagmites (cave) 13.2%, 0x17cd snow patch 11.6%, 0x08e4 stalagmites (cave) 11.4%, 0x02da crystal (cave) 5.4%, 0x17ce snow patch 3.6%, 0x222c crystal (cave) 3.6%, 0x0cac grasses 2.8%, 0x2226 crystal (cave) 2.1%
* **dirt**: 0x0caf grasses 7.7%, 0x0cd6 cedar tree 6.0%, 0x0cad grasses 5.9%, 0x0cd8 cedar tree 5.8%, 0x0cac grasses 5.1%, 0x0cb0 grasses 2.4%, 0x0cb6 grasses 1.9%, 0x0cf7 fallen log 1.7%
* **cave**: 0x08e1 stalagmites (cave) 17.2%, 0x08e4 stalagmites (cave) 11.6%, 0x0d16 mushroom 3.9%, 0x0ee3 spiderweb (cave) 2.5%, 0x0ee6 spiderweb (cave) 2.0%, 0x0ee4 spiderweb (cave) 1.9%, 0x0ee5 spiderweb (cave) 1.8%, 0x1b20 leaf litter pile (cave/dirt) 1.6%
* **swamp**: 0x0d05 reeds 11.6%, 0x0d04 water plants 6.6%, 0x0d0b lilypads 6.3%, 0x0d09 lilypads 5.6%, 0x324f sunken log (swamp) 5.1%, 0x0d0a lilypads 5.0%, 0x0cf8 cypress tree (swamp) 4.1%, 0x0d06 lilypads 4.0%
* **other**: 0x17cd snow patch 3.6%, 0x1b19 bones/skulls (cave) 2.5%, 0x1b17 bones/skulls (cave) 2.5%, 0x0c84 foxglove flowers 2.2%, 0x17ce snow patch 2.2%, 0x0cad grasses 2.1%, 0x0caf grasses 2.1%, 0x0cea sapling 2.0%

### Elevation (dz = static z - land z)
On grass/forest/jungle/snow/swamp natural statics sit exactly on land z in 95-99% of cases (forest 99.07%, grass 97.05%, jungle 95.11%, swamp 98.93%, snow 95.27%). Deviations are concentrated in
kinds that are placed on slopes/cliffs: on **rock** land only 15% have dz=0 (rocks/stalagmites mean dz -25: they are decor of cliff faces placed at the cliff-foot z), cave 71%, dirt 78% (trees on dirt mean dz +2.3).
**Rule for the generator: z_static = land z of the anchor tile; for multi-tile composites all parts use the ANCHOR's z (measured dz=0 for every slice), so composite jungle trees must go on flat ground (or the parts will float/sink).**

### Living vs dead
Per material (living = trunk with canopy on the same tile; dead/bare = 0xCCA-0xCCC or trunk without canopy):
grass: 3,691 : 100 (stumps 21); forest: 126,037 : 233 (stumps 4); jungle: 229 : 0 (stumps 0); sand: 1 : 1 (stumps 0); snow: 2,070 : 1 (stumps 0); rock: 27 : 5 (stumps 0); dirt: 1,972 : 26 (stumps 8); swamp: 286 : 1693 (stumps 0); other: 15 : 19 (stumps 1).
Forest trunks carry their canopy 99.5-99.85% of the time (per-trunk fractions in props.json `trunk_canopy_fraction`). Jungle composites carry leaves 99.4-99.8%. Bare/dead trees are essentially absent from Britannia (ratio ~540:1 in forest, 37:1 on grass); the swamp is the exception: cypress 0xCFE/0xD01 (no canopy) make it look "dead" (286 : 1,693). Recommendation: <=0.5% bare trunks in forest, 2-3% on grass, none in jungle.

### Tree spacing (nearest-neighbour between tree anchors, Euclidean tiles)
forest p10/p25/p50/p75/p90 = 1/2/3/3/4, 15% at distance 1, 58% >=3; grass 1.41/2.24/3/4.47/6.08; jungle 1/1/2/2.83/3.61 (25% adjacent - the composites overlap their canopies); snow 1/1/1/1.41/1.41 (cedars placed in tight clumps, 73% adjacent); sand palms 2.2/4/6/10/21.
A Poisson-disc radius of 2 (forest), 1 (jungle), 2.5 (grass) with occasional adjacent pairs reproduces these.

### Roads
Road mask = thin corridors of dirt 0x71-0x7C / cobblestones 0x3E9-0x3EC (inner EDT <= 2.5, >=6 tiles away from any dirt blob wider than 8, component >= 60 tiles) -> 116,967 road tiles.
Of 204,732 tree anchors: 0.33% ON a road tile, 0.49% within 1 tile, 0.86% within 2, 1.39% within 3, 2.6% within 5. Among the 39,785 trees within 40 tiles of a road, only 2.5% are <=1 tile and 7.2% <=3 tiles away.
The few on-road cases are cedar pairs (0xCD6/0xCD8) and small grass tufts 0x1782/0x1783 placed *on* cobblestone streets as decoration. **Rule: keep tree anchors (and composite footprints) >= 2 tiles from road tiles; grass tufts/flowers may touch roads.** (Caveat: plain dirt 0x71-0x7C is also used as forest-floor patches, so trees on 'dirt' material are legitimately common: 2,984 on dirt.)

### Sprite slices (never place alone)
Strict rule (bbox width < 20 px and height > 60): 0x0d4c, 0x0d53, 0x0d63, 0x0d6d, 0x0d7a, 0x0d93, 0x12be - all of them are jungle/Yew canopy slices.
Practical rule (bbox width <= 48 and height > 100, i.e. one-tile-wide tall strips): all trunk/leaf/vine slices of the 4 jungle families and the Yew tree (0xD41-0xD93 except vines 0xD54, and 0x12B6-0x12C7) plus 0x1B7E tuscany pine (45x158, a legitimate single sprite), 0xD31 century plant and 0xD37/0xD38 yucca (legit). Every id carries `narrow_slice`, `tall_slice` and `place_alone` flags in props.json `ids`.
Forest trunks (0xCCD... 122x175) and canopies (122x178) are full-width sprites but are still only meaningful as the measured pair.

## 4. REJECTED ids (never place)
| ids | name | reason |
|---|---|---|
| 0xC8F-0xC92, 0xDB8-0xDB9 | hedge / untrimmed hedge | explicitly banned (man-made topiary) |
| 0x4C1-0x4C5, 0x504-0x50A | wooden logs | Bridge|Surface flagged log bridges/walkways on dirt roads |
| 0x90-0x97, 0xA4-0xA5 | log wall / log post | Wall flag, building pieces |
| 0x58F-0x594, 0x5E4-0x5E9, 0x5F1-0x5FE | palm fronds / palm frond roof / log roof | Roof flag |
| 0x11C9 | potted tree | furniture |
| 0xC5E-0xC60, 0xD1B-0xD24 | vines / grapevines | farm crop rows (sit on furrows land) |
| 0xC3B-0xC42, 0xC4F-0xC82 | dried flowers/herbs, cotton, wheat, vegetables | crops / indoor decor |
| 0xCEB-0xCF2 | vines (0xCEB-0xCF2) | wall-climbing vines, found on dirt/stone/cave near buildings, not attached to trees |
| 0x177F-0x1781 | grass | only on marble/cobble floors (courtyard decoration) |
| 0xD55-0xD57 as standalone | vines/tree | 0xD57 alone is the tail of a vines add-on (0xD55,0xD56,0xD57) of jungle trees; only emitted inside composite props |
| 0x2F4F-0x2F55, 0x31B0-0x31C0, 0x3B41 | (no name) | 44x1 px blank sprites on rock land (invisible markers) |
| 0x229A, 0x229D | (no name) | 'UNUSED' placeholder art |
| 0x1797-0x17B2 | water | coast water statics (handled by the coastline pass) |
| 0x2E02-0x2E29 | acid | dungeon liquid |
| 0x3241 | swamp | swamp surface overlay (terrain pass, not a prop) |
| 0xAE46-0xAE47 | Tracks | mine-cart tracks |
| 0x187E, 0xF35, 0x10EF-0x10F2, 0x1B9F, 0xCC3 | spilled flour, hay, garbage, refuse, muck | man-made litter |
| 0xEDF-0xEE2, 0xED3 | grave | graveyard |
| 0xF13-0xF2C | gems | dungeon loot decoration |
| 0x53C-0x53F | cave floor | floor overlay statics |
| 0x39B1-0x3AE8 | tree (Foliage, 0x39xx-0x3Axx) | newer (SA/ML) tree art: <30 uses each, only on 'other' land (not Britannia proper); not measured |
| 0xCCF,0xCD2,0xCD5,0xCDC,0xCDF,0xCE2,0xCE5,0xCE8,0xCFA,0xCFD,0xCFF,0xD00,0xD02,0xD03 | alt leaves | alternate canopy ids used <15 times; keep to the measured pairings |

Also not in the whitelist by construction: everything with Wall/Roof/Door/Window/Container/Surface+Bridge flags, furniture, floors ('cave floor' overlays 0x53C-0x53F, 'dirt' patch statics 0x31F4-0x31F7, 0x911), signs, lights, and the coast water statics 0x1796-0x17B2 which belong to the coastline pass.

## 5. Generator recommendations (summary)
1. Place props per land material with the Britannia densities: forest 26/100 tiles (6 trees), jungle 25.5/100 (6.4 tree anchors, composites cover ~8 tiles each), grass 5.6/100 (0.37 trees), swamp 6.8-17/100, sand 2-3/100 (cacti, desert grasses, flowers; palms only 0.04/100), snow 3.9/100 (almost only cedar 0xCD6/0xCD8 pairs + tuscany pine 0x1B7E, in tight clumps), dirt 3/100, cave 2.5/100 (stalagmites, mushrooms, webs), rock 0.1/100.
2. Weighted choice of props from `materials[M].props[].weight`; expand `parts` relative to the anchor with z = anchor land z; for composite jungle trees pick one leaf set (props already split into leafset 0/1) and add one `optional_vines` set with its `p`.
3. Tree anchors: >=2 tiles from roads, >=1 tile from water/coast ring, NN spacing as above; forest floor gets 5 grass-tuft props per tree (grasses 0xCAF/0xCB0/0xCB5/0xCB6 = 33% of all forest anchors) plus brambles, mushrooms, flowers, small rocks 0x1771-0x177C, fallen logs 0xCF3-0xCF7.
