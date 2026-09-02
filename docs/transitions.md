# Britannia transition tables (learned from Felucca, for the generator)

Scripts: `analysis/transitions_01_learn.py [main|t2a]` (whole pipeline, ~10 s per region).
Data: `out/transitions/transitions.json` (= `transitions_main.json`, x < 5120), `transitions_t2a.json` (x >= 5120),
`pure_variants.json` (= `_main`), `pure_variants_t2a.json`, `policy_<tag>.json` (band side per pair),
`id_side_<tag>.json` (**exact id -> pure-material map used**; the generator must use the same assignment to reproduce
the tables), `mask_specific_pure_ids_<tag>.json` (ids the taxonomy calls pure/variant that are really kit pieces),
`canonical_kits_main.txt` (kits of the main pairs from the band side), `pair_table.md`, `log_<tag>.txt`.

## 1. Definitions

* **Mask bit encoding = CentrED `LandBrush.Direction`** (offsets are map dx,dy): N=1 (0,-1), R=2 (1,-1), E=4 (1,0),
  D=8 (1,1), S=16 (0,1), L=32 (-1,1), W=64 (-1,0), U=128 (-1,-1). A bit is SET when that neighbour is on the **B side**.
  Taxonomy directions map as: tax N(-1,-1)=U, NE(0,-1)=N, E(1,-1)=R, SE(1,0)=E, S(1,1)=D, SW(0,1)=S, W(-1,1)=L,
  NW(-1,0)=W.  Side bits = N|E|S|W = 85, corner bits = R|D|L|U = 170.
* **Pure map.** Every tile gets one material: pure/variant/road/floor/decor ids -> their taxonomy material; transition /
  edge / floor_edge ids -> ONE side of their pair, chosen per pair (`band_side`, see 3). A tile is a **boundary tile**
  when its 8 neighbours contain exactly two materials A<B (tiles touching 3+ materials are excluded: 265k of 1.5M);
  its record is (A, B, mask of B neighbours, Britannia's tile id). Both orderings are stored (`B->A` uses mask^0xFF).
* Main continent: 20.97 M non-void tiles, **1,209,038 boundary tiles, 178 ordered pairs** with >= 50 tiles.
  Lost Lands: 4.52 M tiles, 760,706 boundary tiles, 224 pairs.

## 2. KEY FINDING: Britannia's kits are two-sided and sloppy; the band must be assigned per pair

The taxonomy's per-id "mostly A / mostly B" (art sector count) splits a kit across both sides and scrambles the
masks (forest/grass: N-edge piece 0xD1 is forest-major, E-edge piece 0xCB is grass-major). Measured on forest/grass,
the self-consistency (top-1 *group* accuracy, see 4) is 0.636 with the taxonomy split, 0.472 with the band assigned to
forest and **0.656 with the band assigned to grass**. For every pair the script tries {taxonomy split, all-to-A,
all-to-B} and keeps the best single side unless the split is > 0.03 better (`policy_main.json`). Result, main continent:

| pair | band side | pair | band side |
|---|---|---|---|
| forest/grass | **grass** | grass/jungle | **jungle** |
| grass/sand (beach) | **sand** | grass/rock | **rock** |
| dirt/rock | **dirt** | forest/rock | **forest** |
| grass/swamp | **swamp** | cobble/dirt | **dirt** |
| dirt_dark(road)/forest | **dirt_dark** | dirt/dirt_dark | dirt |
| furrows/grass | grass | jungle/sand | jungle |
| rock/sand | rock | rock/seafloor, seafloor/snow | seafloor |
| dirt/grass | taxonomy split (0.575 vs 0.42/0.51) | dirt_dark/grass | taxonomy split |
| dirt/forest, dirt/sand | taxonomy split | grass/sandstone_floor | grass |

"Band side = X" means: **in the generator, start from a sharp pure-material map; only tiles of material X that have a
neighbour of the other material get replaced** (by the top tile of the `X->other` table for their mask); tiles of the
other material stay pure. So the band is 1 tile wide and lies on the X side. For the three "taxonomy split" pairs
use `id_side_main.json` (it lists which pure material each id counts as) – in practice for dirt/grass Britannia puts
grass-side pieces (0x7D/0x7E/0x82/0x83 single dirt spot, 0x85-0x8C edges) AND dirt-side convex corners 0x79-0x7C, so
the generator can simply use the `grass->dirt` table (band on grass) and accept 0.51 instead of 0.575.

Britannia is inconsistent with itself: forest/grass mask 247 (forest only at D) is pure grass 71 % / 0xD9 22 %, while
mask 127 (forest only at U) is 0xD8 63 %; convex forest corners get the corner piece only 31-38 % of the time, otherwise
pure forest. Top-1 lookup therefore gives a *cleaner* map than Britannia, which is what we want.

## 3. Kits (top tile per canonical mask, from the band side; "bits = other material neighbours")

Full list in `canonical_kits_main.txt`; every one of the 256 masks is in `transitions.json`. Notation: edge_N = other
material at U|N|R (131), edge_E = R|E|D (14), edge_S = D|S|L (56), edge_W = L|W|U (224); diag_X = only the diagonal X;
L_NE = U|N|R|E|D (143, band tile wrapped around a convex corner of the other material pointing NE) etc.

**grass->forest (band on grass, 412,846 boundary tiles, 254/256 masks seen):** edge_N 0xC8/0xC9 (41/38 %, random
pair), edge_E 0xCE/0xCF (41/39), edge_S 0xD1 (75; rare variants 0xD2/0xD3), edge_W 0xCB (77); diag_U 0xD8 (59),
diag_L 0xDB (55), diag_D 0xD9 (21, pure grass 73), diag_R pure grass (0xDA 16); L_NE 0xD7 (68), L_SE 0xD5 (69), L_SW
0xD6 (34), L_NW 0xD4 (31) – these four are forest-major "convex corner" pieces that the taxonomy had labelled pure
forest (0xD5/0xD7) – their occurrence is 87-91 % at boundaries. Variant groups (interchangeable): {0xC8,0xC9}
{0xCE,0xCF} {0xCC,0xCD} {0xD2,0xD3} {0xD1,0x6B2}.

**jungle->grass (band on jungle, 131,563):** edge_N 0xB6 (66), edge_E 0xB9 (74), edge_S 0xB0 (80), edge_W 0xB3 (78,
0x582 8); diag_U 0xBE (45), diag_R 0xBF (46), diag_D 0xBC (41), diag_L 0xBD (45) (0xBC-0xBF were "pure jungle" in the
taxonomy: they are the diagonal pieces); L-shapes 0xC0/0xC1/0xC2/0xC3 (20-25 %, else pure grass). Groups
{0xB0,0x584} {0xB3,0x582} {0xB9,0x583} {0xB6,0x585}.

**sand->grass (beach, band on sand, 63,381, 0.96 accuracy):** edge_N 0x3A (78), edge_E 0x37 (65; sunk coast
variants 0x22/0x26 in the same group), edge_S 0x39 (77), edge_W 0x38 (80); diag_U 0x35 (92), diag_R 0x36 (85),
diag_D 0x33 (80), diag_L 0x34 (89); L-shapes 0x3C/0x3E/0x3B/0x3D (11-18 %, else pure grass).

**rock->grass (band on rock, 33,217, 0.83):** edge_N 0x239 (95), edge_E 0x23A (92), edge_S 0x23B (87), edge_W 0x23C
(93); diag_U 0x237 (78), diag_R 0x238 (57), diag_D 0x235 (49), diag_L 0x236 (48); L-shapes 0x233/0x234/0x231 (~20 %,
else pure grass). Mean |dz| across the boundary 9.0 (p90 19): this is a cliff kit – the band tile is the slope.

**dirt->rock (band on dirt, 14,538, 0.85):** edges 0xDF/0xDC/0xDD/0xDE (N/E/S/W, 89-93), diag_U 0xE3 (84), diag_R
0xE0 (84), diag_D/diag_L pure dirt; L_SE 0xE6 (85), L_SW 0xE7 (84). |dz| 8.8.

**forest->rock (band on forest, 13,294, 0.86):** edge_E 0xED (96), edge_S 0xEE (94), edge_W 0xEF (99), edge_N pure
forest; diag_R 0xF0 (54), diag_D 0xF1 (86), diag_U 0xF3 (46); L_SW 0xF7 (82), L_SE 0xF6 (25). |dz| 11.5.

**swamp->grass (band on swamp, 6,512, 0.88):** all edges and diagonals are the random group {0x3DED,0x3DEE,0x3DEF,
0x3DF0}; L-shapes 0x3DD5/0x3DD1/0x3DD2/0x3DD3 (60-85 %). (T2A swamp uses 0x3DFB/0x3DFD and dirt>swamp.)

**dirt->cobble (city street edge, band on dirt, 13,884, 0.88):** edges 0x3FF/0x400/0x401/0x3FE (84-95), diagonals
0x403/0x404/0x3F9/0x402 (79-88), L-shapes 0x3FA/0x3FB/0x3FC/0x3FD (42-51 %).

**dirt_dark(road 0x3FF8)->forest (band on road, 18,762, 0.94):** edges 0x168/0x166/0x165/0x167 (93-96), diag_R 0x16A
(53), diag_L 0x169 (48), diag_U/D pure road; L-shapes {0x172,0x161}/{0x173,0x163}/{0x171,0x162}/{0x174,0x164,0x14C}.
Road/grass (19,000) has no kit in Britannia except a few 0x16D-0x170 (0.88 with pure tiles only).

**grass->furrows (fields, 5,476, 0.96):** edges 0xB/0xC/0xD/0xA, diagonals 0x10/0xF/0x11/0x12, L 0x13/0xE.

**seafloor shore kit (no policy needed, 0.97-1.0):** seafloor tile next to sand/wetsand/snow/dirt: edge_N 0x50, E
0x51, S 0x52, W 0x53, diag_U 0x54, R 0x55, D 0x56, L 0x57 (0.89-1.0) – i.e. the 0x4C-0x63 ring's `id&3` orientation
(0=N,1=E,2=S,3=W) is exactly this mask family, ring 0x50-0x57 being the first ring; L-shapes at snow coasts are
0x179-0x17C, at sand coasts just pure sand. seafloor->water: 0x64 (93-99 %) on the seafloor side, pure water on the
other – distance/gradient driven (see `seafloor_gradient.json`), not mask driven.

**dirt->grass (60,594, taxonomy split, 0.57):** grass tile with a single dirt diagonal: dirt at D -> 0x7D, at U -> 0x7E,
at L -> 0x82, at R -> 0x83 (masks 247/127/223/253, 33-41 %); grass edges 124 -> {0x85,0x86}, 199 -> {0x8B,0x8C}, 31 ->
{0x87,0x88}, 241 -> {0x89,0x8A} (50-57 %); dirt-side convex corners 28 -> 0x79 (46), 193 -> 0x7A (48), 7 -> 0x7C
(49), 112 -> 0x7B (51); else pure. |dz| 1.8 (many dirt/grass contacts are the 0x8D-0xA7 cliff family).

Floors (wood/stone/marble/brick/sandstone/cobble vs grass/dirt/sand): no kit except grass->sandstone_floor
(0x456-0x465, 4 random variants per edge) and sand->stone_floor (0x444/0x445); top1_group 0.91-1.0 = just pure tiles.

## 4. Validation

Per pair (`pair_table.md`, full numbers in `transitions.json` -> `validation_self` / `validation_holdout`):
* *self* = re-applying the table to the tiles it was built from (top-1 id, top-3 id, top-1 group);
* *holdout* = table built from x < 2560 only, applied to x >= 2560 with the fallback chain of section 5.
"Group" = variant groups of section 3 merged and all pure ids of a material merged; it is the number that matters
(0xC8 vs 0xC9 is a coin flip in Britannia).

| pair | n | self top1 id | self top3 id | self top1 group | holdout top1 id | holdout top1 group | unseen masks |
|---|---|---|---|---|---|---|---|
| forest/grass | 412,846 | 0.34 | 0.65 | 0.66 | 0.26 | 0.52 | 0.000 |
| grass/jungle | 131,563 | 0.38 | 0.65 | 0.68 | 0.25 | 0.49 | 0.045 |
| grass/sand | 63,381 | 0.29 | 0.76 | 0.96 | 0.30 | 0.94 | 0.001 |
| dirt/grass | 60,594 | 0.31 | 0.64 | 0.57 | 0.28 | 0.48 | 0.000 |
| grass/rock | 33,217 | 0.52 | 0.81 | 0.83 | 0.47 | 0.78 | 0.003 |
| seafloor/wetsand | 31,627 | 0.90 | 0.98 | 1.00 | 0.86 | 0.98 | 0.005 |
| sand/seafloor | 23,356 | 0.88 | 0.96 | 0.97 | 0.86 | 0.96 | 0.002 |
| dirt_dark/forest | 18,762 | 0.42 | 0.80 | 0.94 | 0.46 | 0.94 | 0.001 |
| dirt/rock | 14,538 | 0.52 | 0.84 | 0.85 | 0.46 | 0.80 | 0.027 |
| cobble/dirt | 13,884 | 0.45 | 0.81 | 0.88 | 0.40 | 0.87 | 0.006 |
| forest/rock | 13,294 | 0.50 | 0.84 | 0.86 | 0.50 | 0.87 | 0.000 |
| grass/swamp | 6,512 | 0.44 | 0.82 | 0.88 | 0.06 | 0.74 | 0.000 |
| furrows/grass | 5,476 | 0.94 | 0.99 | 0.96 | 0.82 | 0.89 | 0.099 |

Why top-1 *id* is low: (a) pure variants are uniform random (4 ids x 25 % caps top-1 at ~0.25 wherever the answer is
"pure"), (b) paired kit variants (0xC8/0xC9 ...), (c) Britannia's own inconsistency: the same mask is left pure in
30-70 % of cases for forest/grass diagonal and L-shaped masks, and the forest/grass kit is placed on different sides
in different regions (west half vs east half drops group accuracy 0.66 -> 0.52; Lost Lands put the band on the
*forest* side and dirt/grass on the *dirt* side, `policy_t2a.json`). (d) 2-tile-wide spots: where two pieces meet
(e.g. 0xD4's E neighbour is 0xD8/0xC8 33/41 %) Britannia sometimes widens the band. No pair has a systematically
2-wide band: for every pair with a kit the far side is >= 0.89 pure (column "Aside pureA" in `log_main.txt`).

## 5. Lookup algorithm for the generator

```
pure[x,y]           : material index from the sharp biome map
for each tile t of material X where some 8-neighbour has material Y != X:
    if {X,Y} has no kit (has_transition_ids false) -> keep pure X (random variant, section 6)
    band = band_side(X,Y)              # policy_main.json; 'tax' pairs: treat as band on the grass/lighter side
    if X != band -> keep pure X
    mask = sum(bit_d for d in 8 dirs if pure[t+d] == Y)     # other neighbours (third materials, void) count as X
    table = transitions["X->Y"]["masks"]
    tile = lookup(table, mask)
lookup(table, mask):
    1. exact mask present           -> top-1 id (or sample from the first variant group proportionally)
    2. else masks with identical side bits (mask & 85), nearest by corner Hamming distance, ties by count
    3. else nearest by weighted Hamming (side bit = 2, corner bit = 1), ties by count
    4. else popcount(mask) >= 5 -> pure Y, otherwise pure X
```
Hold-out test of the chain (section 4): unseen masks were < 1 % for all big pairs (4.5 % grass/jungle, 2.7 % dirt/rock), so the
fallback is rarely exercised; unseen masks are almost all 'noisy' 5-7-bit masks whose correct answer is a pure tile. Tiles touching three materials: resolve pairwise in a fixed priority
(water/seafloor > sand > rock > snow > swamp > jungle > forest > dirt > grass), i.e. compute the mask against the
highest-priority foreign material only and treat the rest as X; Britannia has 265k such tiles (18 % of boundary tiles),
mostly coast corners where sand/seafloor/grass meet.

Elevation (mean |z(B side) - z(A side)| per ordered pair in `transitions.json`): flat kits (|dz| < 0.5): forest/grass
0.44, grass/jungle 0.48, grass/swamp 0.02, road/forest 0.05, dirt/dirt_dark 0.07, cobble/dirt 0.35, furrows 0.02.
Cliff kits: grass/rock 9.0 (rock higher by 8.8), dirt/rock 8.8, forest/rock 11.5, rock/snow 13.7 (snow higher), rock/
sand 11.1 (sand lower). Coast: grass/sand -5.2 (sand lower, p90 14.8), sand/seafloor -7.7, seafloor/water +5.4,
grass/wetsand -15.4. dirt/grass 1.8 and dirt/forest 3.2 (mixed flat + cliffs).

## 6. Pure variants and decor (interior tiles = all 8 neighbours same material, main continent)

`pure_variants.json`: grass (1.30 M interior) 0x3:0x4:0x5:0x6 = 25.5:24.4:24.4:24.1 %; anything else < 0.3 % in total
(the "variants" that remain are kit pieces leaking in, e.g. 0xCB 0.28 %; decorative grass ids like 0x3DC3 are 0.08 % in
the earlier count and effectively absent inside pure grass – **Britannia has no flower/decor land ids in grass**, all
decoration is statics). forest (1.90 M) 0xC4-0xC7 24.6-24.7 % each + 0xF0-0xF3 0.31 % each (a slightly different
forest variant sprinkled at ~1.2 %). jungle 0xAC-0xAF 24.6 % each + 0x100-0x103 0.28 % each (1.1 %). rock
0x22C:0x22D:0x22E:0x22F = 26.5:26.2:25.9:21.3 (0x22F under-used), darker 0x21F-0x22B < 0.01 %. sand 0x16:0x17:0x18:0x19
= 26.3:23.2:23.2:23.8 (+0x444/0x445 1.7 % each = stone-floor edge used as beach detail). dirt 0x75:0x76:0x77:0x78 =
21.8:20.0:20.3:18.7 and 0x71:0x72:0x74:0x73 = 5.4:5.3:5.2:2.4 (two dirt looks mixed 80/20). snow 0x11A-0x11D 25 %
each. swamp 0x3DE9-0x3DEC 15 % each + 0x3DED-0x3DF0 5-7 % each (the "transition" ids are used inside swamp too) +
0x3DC2..0x3DE8 1-1.3 % each. dirt_dark road 0x3FF8:0x3FF9:0x3FFA:0x3FFB = 74:8:8:10. cobble 0x3E9-0x3EC 25 % each.
water 0xA8-0xAB 25 % each. seafloor interior: 0x64 77 %, rings 0x58-0x63 1.4-2.8 % each. furrows 0x9 99 %.

## 7. Ids mislabelled by the taxonomy (`mask_specific_pure_ids_main.json`, 74 ids)

Called pure/variant but >= 50 % of occurrences sit at one boundary mask: 0xD5/0xD7 (forest convex corners),
0xBC-0xBF (jungle diagonals), 0x50-0x57 (seafloor first-ring orientation pieces), 0x237/0x238 (rock diagonals),
0xE6/0xE7/0xF7 (rock L-shapes), 0x3FA-0x3FD (cobble L-shapes), 0x37B-0x37E (grass with dirt spot), 0x377-0x37A (dirt
corners), 0x3DC9/0x3DCA/0x3DD1-0x3DD5 (swamp L-shapes), 0x17A-0x17E/0x181/0x182 (snow coast pieces), 0x115-0x117
(snow/rock), 0x296/0x297 (planks next to sand). The interior-based variant ratios above already exclude them.

## 8. Lost Lands (x >= 5120)

Same materials, but different conventions and extra kits: cave/cave_wall (118k boundary tiles, 0x25B-0x269, 0x2BC,
0x2C0), cave/dirt (31k, 0x1E0-0x1EF), dirt/snow (7.9k, 0x385-0x390, band on snow), jungle/rock cliffs (5.7k, 0xFC-0xFF,
0x777-0x791), dirt/swamp (2k, 0x3DF0/0x3DFB/0x3DFD), leaves/tree (giant tree 0x2E76-0x2ED8), obsidian/rock/void
(0x3FCC, 0x2745). dirt/grass there is a clean dirt-side kit 0x79-0x7C (0.89) and dirt/forest uses the 0x2E5-0x305 cliff
family instead of road edges. Use `transitions_t2a.json` for those pairs; main-continent tables for everything else.
