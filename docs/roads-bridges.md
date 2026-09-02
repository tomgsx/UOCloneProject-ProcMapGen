# Roads, paths, bridges and docks in Felucca (measured)

All numbers measured from Felucca map0/statics0 (void 0x244 excluded). Scripts:
`analysis/roads_01_ids.py` .. `roads_09_assemble.py`; data in `out/roads-bridges/` (`roads.json` is the
consolidated product; `bridge_templates.json` holds exact layouts; `roadlike_masks.npz` holds the packed
road mask + skeleton).

Direction bits everywhere below follow CentrED `IO/Models/LandBrush.cs`:
`N=1 R(NE)=2 E=4 D(SE)=8 S=16 L(SW)=32 W=64 U(NW)=128`; a bit is set when that neighbour is **not road
material**, where road material = core ids + the transition ids themselves (this is the convention that
gives clean, unimodal masks; counting only core produced 5-7 bit masks).

## 1. Which land ids are roads

tiledata names are useless ("dirt" for 200+ ids). Empirically:

| family | ids | tiles | role |
|---|---|---|---|
| dirt road core | 0x71-0x78 | 310k | the road surface. 0x75-0x78 (~33k each) dominate the mainland; 0x71-0x74 are 85% in T2A (x>=5120). Mean RGB ~ (45,36,24) |
| dirt inner corners | 0x79 0x7A 0x7B 0x7C | ~3k each | see table below |
| dirt->grass edges | 0x7D 0x7E 0x82 0x83 0x85-0x8C | 4-6.5k each | mean RGB (43,49-59,14-18) (half grass) |
| cobblestones | 0x3E9-0x3EC | 58k | town streets only (Britain etc.), flat (97% of tiles have 0 corner dz), mean width 4-8 |
| sand paths | none | - | beach sand 0x16-0x19 is never used as a linear road |
| planks land | 0x296-0x2BB | 3.5k | house/dock floors, not roads |

"Dirt" is also used for big dirt plains, mainly in T2A (min-run width >= 9 => 39k tiles), so a generator
must treat "road" as a thin structure: after removing tiles of width >= 9 and keeping components >= 150
tiles, there are 22,746 road-like tiles on the mainland (325 components total, largest 6,277 tiles) and
106,173 in T2A.

## 2. Transition tiles (dirt -> X), 3x3 masks

Canonical masks observed (>=40-50% of each id's occurrences, next candidates are strips/1-wide variants):

**dirt -> grass (0x3-0x6)**
```
 edge N : 0x8B,0x8C  mask NRU   (1|2|128 = 131)      edge E : 0x87,0x88  mask RED  (2|4|8  = 14)
 edge S : 0x85,0x86  mask DSL   (8|16|32 = 56)       edge W : 0x89,0x8A  mask LWU  (32|64|128 = 224)
 outer corner NW : 0x7D  NRLWU (227)   NE : 0x82  NREDU (143)   SE : 0x7E  REDSL (62)   SW : 0x83  DSLWU (248)
 inner corner NE : 0x7C  R (2)         SE : 0x79  D (8)         SW : 0x7B  L (32)       NW : 0x7A  U (128)
 1-wide N-S strip : mask REDLWU -> 0x87..0x8A ;  1-wide E-W strip : NRDSLU -> 0x85/0x86/0x8B/0x8C
```
Reverse check (mask -> id used in Felucca): NRU -> 0x8B 2677, 0x8C 1995 (and bare core 0x75.. 2106);
RED -> 0x87 2839 / 0x88 1856; DSL -> 0x85 3121 / 0x86 1749; LWU -> 0x89 2993 / 0x8A 1722;
R -> 0x7C 1747; D -> 0x79 2036; L -> 0x7B 1828; U -> 0x7A 1732. Important: **only 28% of mainland road
perimeter tiles use a transition**; the rest is bare core against grass (UO roads look "ragged").

**dirt -> beach sand 0x16-0x19**: edges N 0x335, E 0x337, S 0x338, W 0x336; outer corners NW 0x33A,
NE 0x33C, SE 0x339, SW 0x33B; inner NE 0x33F, SE 0x33E, SW 0x340, NW 0x33D (same mask scheme).

**dirt -> mountain rock 0x22C-0x22F**: edges N 0xDF, E 0xDC, S 0xDD, W 0xDE; inner NE 0xE0, SE 0xE1,
SW 0xE2, NW 0xE3; outer NW 0xE4, NE 0xE5, SE 0xE6, SW 0xE7.

**dirt -> snow 0x11A-0x11D**: N 0x385, E 0x387, S 0x388, W 0x386 (corners 0x389-0x38C, masks noisy).
**dirt -> cave floor 0x245-0x249**: N 0x1EE, E 0x1ED, S 0x1EC, W 0x1EF.
**dirt -> cobblestone 0x3E9-0x3EC** (town entrance): dirt-side edge tiles 0x3FE (cobble W), 0x3FF (cobble N),
0x400 (cobble E), 0x401 (cobble S); outer corners 0x3F9 (cobble SE) 0x3FA (NE) 0x3FD (NW) 0x3FC (SW);
inner 0x3FB. Cobble's most common neighbours are exactly these (1,8k each), then grass, then wooden floors.

All tables with numeric masks are in `roads.json -> dirt_road`.

## 3. Road geometry (mainland, thin road-like tiles)

* **Width** (min run through tile, core+edges): 1:3514 2:3312 3:4031 **4:7268** 5:2832 6:1789; mean 3.35.
  Core only: mode 4 (5772), 3 (4259). T2A roads are wider (mode 4-5, mean 4.15). => draw **3-4 core tiles
  wide**, plus occasional 1-tile edge tiles.
* **Curvature** (8-connected skeleton): a 45 deg heading change every 4.6 steps (0.218 turns/step),
  90 deg+ turns 0.3% of steps; straight runs p50 1, p75 3, p90 6, p99 14 tiles. Roads wander constantly
  at small angles and almost never make sharp bends. T2A: 0.33 turns/step.
* **Elevation along the centreline** (mainland): |dz| per step = 0 for 95% of steps, p99 = 3, max 15;
  mean 0.094. Road z quantiles p01 -3, p10 0, p50 0, p90 20, p99 57 (roads climb hills, but in long flat
  stretches with short steps). Max |dz| to any 8-neighbour on road tiles: 0 for 73%, <=2 for 83%, <=6 for 93%.
  Neighbouring land is on average 2.4 z higher than the road (roads sit slightly sunken / in valleys).
  T2A roads are rougher: dz mean 1.78, p95 5, p99 7.
* Cobblestone streets: |dz| 0 for 97%.

## 4. Roads through forest

214,002 tree statics (Foliage flag or name 'tree'). In forested zones (>=10 trees within a 25x25 window),
distance from road centreline to nearest tree: p05 1.4, p10 2, p25 2.8, **p50 4.1**, p75 5.4, p90 7.1 tiles.
Tree density by ring distance from the road edge (forest zones): 1 tile 0.022 /tile, 2: 0.033, 3: 0.031,
4+: 0.039-0.042. => a clearing of ~1-2 tiles beyond the road edge at about half density, full forest
density from 4 tiles out. Trees directly on mainland road tiles are rare (1,159 in T2A jungle mostly).

## 5. Bridges and docks

`TileFlag.Bridge` marks stairs/ramps, not bridges. Real bridge decks are plain `Surface` statics:
* plank deck **0x7C9 'wooden plank', 0x7CA/0x7CB 'wooden bridge', 0x7CC** (48x44 art, mixed at random per
  tile); also 0x7CD-0x7D0 (docks). Log deck 0x509/0x50A/0x4C1 (T2A). Stone deck 0x750 (+0x765-0x768).
* rails: **0x8F9/0x8FB** alternating along the N and S deck rows of an E-W bridge; **0x8F8/0x8FA/0x8FC**
  along the E/W columns of a N-S bridge. Suspension sides 0x7FB (E) / 0x7FC (W) + end pieces 0x7E7-0x7F9.
* ramps 0x87A-0x87D (z 0 and +5 to reach a deck at +10). Dock piers 0x3A5/0x3AA/0x3AC/0x3AE (Impassable)
  + rope 0x3A9 at deck_z+8, post 0x1296.

Found 54 bridges (>=30 deck statics, >=2 land sides, road adjacent) and 21 docks (1 land side, >=40).
**Land under a deck is the normal coast anatomy** (z=-15 + water static at -5, or water land id at -5);
the deck statics float at the bank road z (0 for 13/54; otherwise the bank z). Docks: deck z = **-3**
(17/21), the shore tiles it attaches to are road core sunk to z=-3 (2 tiles of them), then z=0 road.

Templates (exact land rows + every static, relative coords) in `roads.json -> templates`:
`bridge_T2A_EW_small` (5788,223: 12 long x 5 rows plank + 2 rail rows, deck z 0),
`bridge_T2A_EW_12x6` (5362,3337: deck z +4 = bank z), `bridge_Britain_W` (1377,1741: 20x11 plank deck z 0
with stone wall 0x63/window 0x5E parapets and stone stairs 0x751/0x756/0x758 at z -5),
`bridge_logs_NS` (5615,47: 3-wide 0x509 logs, 26 long, suspension sides), `bridge_plank_NS_long`
(1520,1469: 3 planks 0x7CC at z +10 over 35 tiles, rail columns, ramps at both ends),
`dock_SkaraBrae_small` (710,2230: 18x8 deck at z -3, piers at +5 on the outer row/corners).

## 6. How roads end

Skeleton endpoints on the mainland (n=286): cave/mountain pass 102, building wall 57, open land 58,
merge into a dirt field 32, cobblestone street 18, water edge without deck 17, dock/bridge deck 2.
12 of 21 docks have a dirt road touching them; the road reaches the shore by sinking to z=-3 on the last
2 tiles. Roads enter towns through the dirt->cobble edge tiles (0x3FE-0x401); they do not continue as dirt
inside the cobbled area.

## 7. Recipe: 2-3 tile wide dirt road with edges, and a bridge at a river

1. **Centreline**: polyline between waypoints; add low-frequency wander (heading noise ~ +-45 deg every
   4-6 tiles, never >90 deg). Rasterise 8-connected.
2. **Elevation**: sample terrain z along the line, then smooth it (moving average >= 9 tiles) and clamp
   |dz| <= 1 per step for 95% of steps, never more than 3; set all road tiles in the cross-section to the
   centreline z (flat across) and blend the 2 tiles either side of the road toward it (max step 2-3 per
   tile) so that no road tile sees a neighbour dz > 6. Roads should be <= the surrounding land.
3. **Surface**: paint a 3-wide (width W=3, occasionally 2 or 4, change width only every >= 10 tiles) band
   with core ids chosen randomly from 0x75-0x78 (mainland look) or 0x71-0x78.
4. **Edges**: for each non-road tile 8-adjacent to the band compute nothing; for each *road* tile on the
   band boundary compute mask = bits of 8-neighbours that are not road material. Look up, in this order:
   outer corner (mask contains NRLWU/NREDU/REDSL/DSLWU) -> edge (contains NRU/RED/DSL/LWU) -> inner corner
   (exactly R/D/L/U) -> else keep core. Apply it to only ~30-40% of boundary tiles (random) to mimic
   Britannia's ragged edge, or 100% for a tidy look. Use the grass table when the far side is grass
   0x3-0x6, the sand table on beaches, the rock table next to mountains, 0x3FE-0x401 at a cobbled town.
   Do NOT place a transition on a tile whose corner z differ by more than ~4 (it renders as a stretched
   texmap anyway; the art is only visible flat).
5. **River crossing**: where the centreline crosses water, choose the crossing perpendicular to the bank,
   at a point where the water width is <= ~12 tiles (Britannia decks: 12-35 tiles). Keep the river tiles
   exactly as the coast anatomy (land -15 + water statics at -5). Set both bank road tiles to the same z
   Zb (flatten 3 tiles of bank each side). For an E-W crossing of length L and a 3-wide road: for every
   water tile in rows y0..y0+2 and columns x0..x0+L-1 add one static from {0x7C9,0x7CA,0x7CB,0x7CC} at
   z=Zb; add rails 0x8F9/0x8FB alternating on rows y0-1 and y0+3 (same columns, same z) -- or make the deck
   5 rows wide like Felucca's bridges (rows y0..y0+4 plank, rails on y0-1/y0+5). For N-S crossings use
   rails 0x8F8/0x8FA/0x8FC on columns x0-1 and x0+3. Extend the deck 1 tile onto each bank (Felucca does),
   and put road core under those bank tiles. No land change under the deck; CanDrawStatic is satisfied
   because land z (-15) < deck z + 5.
6. **Dock** (road meets the sea): sink the last 2 road tiles to z=-3 (still road core), then on water tiles
   place the 0x7C9/0x7CA/0x7CB deck at z=-3 as an 8-18 x 3-8 rectangle perpendicular to the shore; piers
   0x3A5/0x3AA (corners 0x3AC/0x3AE) at z=+5 on the seaward row and every ~8 tiles along the sides, rope
   0x3A9 at +5 between them.
