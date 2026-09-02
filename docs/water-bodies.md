# Water bodies in Britannia (Felucca) — exact replication rules

All numbers measured on the real Felucca map (7168x4096, void 0x244 excluded) with the scripts in
`analysis/water_bodies_*.py`. Data products: `out/water-bodies/coast_rules.json` (all distributions),
`coast_profiles.json`, `corner_rules.json`, `corner_ids_all_families.json`, `inland_components.json`,
`water_statics_catalogue.json`, `cross_sections.md` (7 dumped 12x12 windows), `wetgrid.npz`, `distgrid.npz`, `corner.npz`.

## 0. Definitions (use these exactly)

* **Water statics**: 0x1796 (flat diamond "full water", 44x22 art), 0x1797-0x179C (six identical-looking 44x44 "object water"
  squares, 868k placed), 0x179D-0x17B2 (water with foam edge). Total 1,042,536 in Felucca; 95.4 % at static z = -5.
* **Wet core tile** = water land id (0xA8-0xAB, 0x136-0x137) OR tile carrying object water 0x1796-0x179C OR an edge static whose
  z is *above* the land z. 16.0 M tiles; 15.91 M belong to ocean-connected components (>= 50k tiles), 64,289 tiles are inland (1,718 components).
* **Foam overlay** = edge static whose z is <= land z (41,577 statics: 0x17A5, 0x17A8, 0x17B0, 0x17B2, half of 0x17AD/0x17AE, and the rare
  0x17A7, 0x179D/E, 0x17A1/2 which are the flat-style inland pieces). They sit on **dry** beach tiles at land z -1..-4 with static z = -5
  (static z - land z = -2,-3,-4 each ~25 %). Do NOT treat them as water.
* **The two styles**: (A) *sunk* style (96 % of everything incl. ocean and most rivers): land sunk to -15, water static at -5 (= land z + 10).
  (B) *flat* style (inland lakes only, 23 % of inland tiles): water land ids 0xA8-0xAB at the lake's own z (e.g. 28, 35, 0, 75) with no statics at all,
  or 0x1796 placed at exactly land z (36k cases). Never mix: 0x1796 is 0.5 % of ocean statics.
* Land-id = quad (x,y)-(x+1,y+1). The 4 corners are tiles own=(x,y), E=(x+1,y), S=(x,y+1), D=(x+1,y+1). **The coast land-id and z are a pure
  function of which of those 4 corners is wet** (and of the 8-neighbour dry mask for fully-wet quads). This is the key that the previous attempt missed.

## 1. Ocean coast anatomy (measured)

Cross-shore profile, ocean side, by Chebyshev distance k to nearest dry tile (136k tiles per ring):

| k | land z | land ids | static |
|---|---|---|---|
| 1 | -15 (91 %), -5 (2.6 % = water-land touching land directly) | ring-1 seafloor 0x53,0x50,0x4C,0x54,0x4D,0x4F or sunk sand 0x22,0x1A,0x1C,0x24,0x1B,0x20 | edge pieces or object water, z -5 |
| 2 | -15 (94 %) | ring-2 seafloor 0x5F,0x51,0x5C,0x52,0x58,0x60,0x55,0x56,0x59,0x57,0x4E,0x5B (+7 % 0x64) | object water 0x1797-C (97 %) |
| 3 | -15 (94 %) | 0x64 (49 %) or ring-3 0x5D,0x5E,0x5A,0x61,0x62,0x63 | object water |
| 4-6 | -15 (93 %) | 0x64 deep floor (92 %) | object water |
| 7 | -5 (58 %) / -15 (40 %) | 0x64 65 %, 0xA8-0xAB 34 % | 0x1796 18 % / object water / none |
| >= 8 | -5 | 0xA8-0xAB (water land, 75 % at k=8, 95 % at k=10) | none |

* **Wet band width** (distance of the first water-land tile from dry land): 7 tiles 27 %, 8 tiles 42 %, 9 tiles 17 %, 10: 3.5 %, 6: 2 %, <=5: 2.7 %.
  So: rings 1-3 = graded seafloor, rings 4-7 = 0x64 with object water, then water land at -5. In narrow bays/rivers the band is whatever fits.
* 0x4C..0x63 are NOT a depth gradient by brightness; they are **oriented pieces** (all share texmap 0x4C, so orientation only matters
  for flat tiles, which all fully-wet ring tiles are). 0x64 = generic deep floor (564k), 0x65 = rare variant (5.4k), 0x66 = rare (690).
* **Dry side** (ocean-adjacent, by distance from wet): k=1: z median 0, distribution 0:21 %, 1:11 %, -1:9 %, -2:11 %, -3:11 %, -4:5 %, 2:5 %, 3:5 %
  (i.e. the coast vertex is drawn from roughly uniform[-4,+3], mean ~0); k=2: z=0 68 % (mean 5.3 because of cliffs); k>=3: 0 (66 %). There is no
  gradual slope: the drop is 0 -> -15 across ONE quad. Materials at k=1: grass 36 %, shore-sand family 33 %, plain sand 8 %, rock 7 %, dirt 5 %, forest 4 %.
* By material, z of the last dry tile: sand-family -3..-1 (44 %), 0/1 (22 %); plain sand 0 (16 %), -5..-1 (46 %); grass 0 (31 %), 1 (14 %), -3..-1 (31 %);
  jungle 0 (28 %) but often on cliffs (z 12-20, 25 %); forest 0 (31 %), 10 (11 %).

## 2. Exact quad rule: corner pattern -> land id, z, static (sand coast)

`corner = own|E<<1|S<<2|D<<3` (bit set when that tile is in the wet core). Percentages = share of that id among all ocean-near quads with that pattern.
Z is the tile's own z. "objw" = one of 0x1797..0x179C uniformly at random (each 16.6 %). Static z always -5.

| corner wet | n | land id | own z | static on this tile |
|---|---|---|---|---|
| none | — | beach material (grass 0x3-6, sand 0x16-19, …) | 0 (54 %), else -4..3 near coast | none (3 % foam overlays, see below) |
| o only | 9.2k | **0x20** 62 % (dirt 0xA0, jungle, 0x1C/0x1A) | -15 | objw (97 %) |
| E only | 8.6k | **0x1F** 69 % | -3/-2/-1 (72 %), 0/1 (11 %) | overlay 0x17A8 23 % / 0x17B0 22 % / 0x17AE 11 %, none 42 % |
| o+E | 19k | **0x24** 31 % / **0x28** 10 % (or water-land 31 %, dirt 0x92) | -15 (62 %) / -5 if water-land | objw 58 %, 0x17AB 8 %, none 31 % (water land) |
| S only | 8.6k | **0x1E** 70 % | -3/-2/-1 (75 %) | overlay 0x17A5 23 % / 0x17B2 22 % / 0x17AD 15 %, none 38 % |
| o+S | 22k | **0x22** 37 % / **0x26** 13 % (water-land 23 %, dirt 0x8F) | -15 (71 %) | objw 65 %, 0x17A9 9 %, none 22 % |
| o+E+S (D dry) | 9.3k | **0x1C** 66 % (dirt 0x95) | -15 | objw (98 %) |
| D only | 9.3k | **0x1D** 74 % (dirt 0xA3) | -3..4 flat-ish (0:14 %,1:13 %) | none |
| E+D | 17k | **0x23** 51 % / **0x27** 16 % (dirt 0x8E/0x8D) | -5..3 (0:14 %, 1:11 %, rest ~8 % each) | none 83 %, overlay 0x17A8/0x17B0 7.5 % each |
| o+E+D (S dry) | 8.7k | **0x1A** 74 % (dirt 0x8D, snow 0x17B) | -15 | 0x17AB 37 %, 0x17A3/0x17A4 31 %, objw 28 % |
| S+D | 13.5k | **0x21** 50 % / **0x25** 15 % (dirt 0x93/0x91, rock 0x22C-F) | -5..3 (0:16 %) | none 83 %, overlay 0x17A5/0x17B2 7.7 % each |
| o+S+D (E dry) | 8.7k | **0x1B** 72 % (dirt 0x91, snow 0x17A) | -15 | 0x17A9 36 %, 0x179F/0x17A0 25 %, objw 35 % |
| E+S+D (o dry) | 9.4k | **0x1C** 76 % (dirt 0x95) | -5..2 (0:14 %, 1:13 %) | none (98 %) |
| all wet | 15.8M | ring ids below | -15 | see below |

Pairs (0x23/0x27, 0x21/0x25, 0x22/0x26, 0x24/0x28) are visual variants: use the first with p=0.76 and the second with p=0.24.
The same pattern table exists for other materials (`corner_ids_all_families.json`): dirt 0x8D-0xA3, snow 0x179-0x17F, rock 0x22C-0x22F; grass and
jungle have NO shore family — a grass/jungle coast keeps grass on the dry quads and uses the **sand** family (0x1A-0x28) or plain seafloor for the
slope quads (grass coasts: wet-1 ids 0x1C 16 %, 0x22 15 %, 0x20 14 %, 0x24 12 %; or directly ring-1 seafloor, see N-grass cross-section).

### 2b. Fully-wet ring-1 quads: dry 8-neighbour mask -> seafloor id and edge static

Dry mask uses CentrED Direction bits (N=1 R=2 E=4 D=8 S=16 L=32 W=64 U=128). Because E,S,D are wet here, only N/R/L/W/U can be dry.

| dry neighbours | n | land id | static |
|---|---|---|---|
| L+W+U (straight W-facing coast: dry to the West) | 11.4k | 0x53 73 %, 0x4F 11 % | **0x17A3 / 0x17A4** 50/50 |
| W+U | 3.0k | 0x53 88 % | 0x17A3/0x17A4 |
| N+R+U (straight N: dry to the North) | 8.7k | 0x50 72 %, 0x4D 11 % | **0x179F / 0x17A0** 50/50 |
| N+U | 2.4k | 0x50 88 % | 0x179F/0x17A0 |
| U only (dry only at the NW diagonal = inner corner) | 9.4k | 0x54 90 % | **0x17AC** 99 % |
| N+W+U (+R/L): outer corner, dry to the NW | 9.2k | 0x4C 92 % | **0x17AF / 0x17A6** 50/50 |
| R only | 8.7k | 0x4D 65 %, 0x50 24 % | objw |
| L only | 8.6k | 0x4F 58 %, 0x53 30 % | objw |
| L+W (dry W and SW, nothing at U) | 2.9k | 0x4F 46 %, 0x53 43 % | **0x17AB** 93 % |
| N+R (dry N and NE, nothing at U) | 2.4k | 0x4D 47 %, 0x50 41 % | **0x17A9** 90 % |
| W only / N only (rare) | 140/113 | 0x53 / 0x50 | 0x17AB 54 % / 0x17A9 47 % |

Ring-2 ids (toward-dry direction by Euclidean nearest dry): 0x5F=W (also L/U), 0x51=E, 0x5C=N, 0x52=S, 0x60=U(NW diag), 0x56=D(SE diag), 0x55/0x59=R(NE), 0x57/0x5B=L(SW), 0x58=U/W/N mix, 0x4E=D/E/S mix.
Ring-3 ids: 0x5D=E, 0x5E=S, 0x61=R, 0x63=L, 0x5A/0x62=D; for W and N directions ring 3 is already 0x64 (49 % of ring 3 overall). Ring >= 4: 0x64.
Summary of a straight coast, from dry to sea (matches the cross-sections below):
* dry on **W**: dry1 = 0x23/0x27 (z -3..3) | 0x53 (-15, 17A3/A4) | 0x5F | 0x64 …
* dry on **N**: dry1 = 0x21/0x25 | 0x50 (-15, 179F/A0) | 0x5C | 0x64 …
* dry on **E**: dry1 = grass/sand at z -3..3 | 0x22/0x26 (-15, objw) | 0x51 | 0x5D | 0x64 …
* dry on **S**: dry1 = grass/sand | 0x24/0x28 (-15, objw) | 0x52 | 0x5E | 0x64 …
The E/S-facing coasts put the slope quad on the wet side (because the quad's own corner is the NW one), hence no foam pieces there; foam pieces exist only for edges facing N, W and the NW corners (0x17A3/A4, 0x179F/A0, 0x17AF/A6, 0x17AC, 0x17AB, 0x17A9) plus the dry-side overlays 0x17A8/0x17B0 (only E corner wet) and 0x17A5/0x17B2 (only S corner wet).

## 3. Recipe: dry/wet boolean mask + beach material -> Britannia land ids, z, statics

Input: `wet[x,y]` (True = water), `material[x,y]` in {sand, grass, jungle, dirt, snow, rock, forest}. Water level -5.
1. **Vertex z**: wet tiles -> z = -15. Dry tiles: z = base terrain z; for dry tiles 8-adjacent to wet, draw z from {-4:5,-3:11,-2:11,-1:9,0:21,1:11,2:5,3:5} (weights in %, others 0);
   at distance 2 use the normal terrain (0 in Britannia 68 %). Keep the coast vertex <= +3 so the water static (-5) is not hidden (CentrED hides a static when land AverageZ >= static z + 5, i.e. >= 0 — Britannia's -1..-4 values on 0x1E/0x1F/0x23/0x21 quads are exactly what keeps the foam visible).
2. **Dry quads** (corner==0): material id (grass 0x3-0x6 random, sand 0x16-0x19, jungle 0xAC-0xAF …).
3. **Mixed quads** (corner in 1..14): look up the table in section 2 (sand family by default; dirt/snow/rock families for those materials; grass/jungle/forest use the sand family). Own z: -15 if own corner wet else step 1 value.
4. **Fully wet quads**: k = Chebyshev distance to nearest dry tile. k=1 -> ring-1 id by dry mask (2b); k=2 -> ring-2 id by direction to nearest dry; k=3 -> ring-3 id for E/S/R/L/D directions else 0x64; k=4..7 -> 0x64 (occasionally 0x65, 1 %); k>=8 (or k>=7 with p=0.58) -> water land 0xA8-0xAB uniformly random, z=-5, NO static.
5. **Statics** (z = -5, hue 0): every sunk tile (z=-15) with corner pattern o-bit set gets exactly one water static: edge piece per tables in 2/2b, otherwise object water uniformly from 0x1797-0x179C. Water-land tiles get none (k=7 band: 18 % 0x1796 at -5 — optional). Dry quads with only the E corner wet get 0x17A8 or 0x17B0 (p 0.23 each, 0.11 0x17AE); only S corner wet -> 0x17A5 or 0x17B2 (0.23 each, 0.15 0x17AD); E+D wet -> 0x17A8/0x17B0 with p 0.075 each; S+D -> 0x17A5/0x17B2 p 0.077 each. 2.2 % of wet tiles carry two water statics (ignore).
6. Never place statics on water-land tiles; never leave a -15 tile without a static (it renders as a brown pit).

## 4. Comparison with CentrED CoastlineTool.cs

Agrees: water z -5; sunk floor = waterZ-10 = -15; "Left/Right" tiles at waterZ+2 (-3) match Britannia's 0x1E/0x1F at -3..-1; direction->edge mapping
(East 0x17A3/A4, South 0x179F/A0, Down 0x17A6, E|D|S 0x17AC, N|R|E 0x17AB, S|L|W 0x17A9, Left 0x17A5, Right 0x17A8) matches Britannia when "direction" is read as *where the water is, seen from the dry tile*. Random object water from 0x1797-0x179C matches (0x1559 in its list never occurs in Felucca).
Differs: (1) CentrED never rewrites land ids except the optional random "brown shore" (random 0x4C-0x6F) — Britannia uses strictly oriented sand-slope ids (0x1A-0x28) and oriented seafloor rings; (2) CentrED uses waterZ-4 (-9) for "Up"-containing cases — Britannia never uses -9 (all sunk tiles -15; 0x54 inner-corner tiles are -15 with 0x17AC); (3) CentrED has one variant for Left/Down/Up/Right; Britannia uses pairs 0x17A5/0x17B2, 0x17A6/0x17AF, 0x17A8/0x17B0 and extra 0x17AD/0x17AE; (4) West 0x179D/E, North 0x17A1/2, Up 0x17A7, W|U|N 0x17AA are flat-style inland-lake pieces (z = land z, land z 0) and are almost absent on the ocean; (5) Britannia foam is on the wet sunk tile for N/W-facing edges and on the dry tile only for the two corner overlays.

## 5. Inland water (rivers, lakes), river mouths, waterfalls

* 1,718 inland components, 64,289 tiles; 109 components >= 20 tiles. 77 % of inland tiles use the **sunk** ocean recipe (land -15, objw at -5, seafloor 0x64 (31 %) + ring ids, sunk sand/dirt slopes at the banks), so a river is literally a thin ocean: static z - land z = 10 (80 %). Half-width distribution of inland wet tiles: 1 (26 %), 2 (19 %), 3 (15 %), 4 (12 %), 5 (8 %), >= 8 (13 %) -> typical river width 2-6 tiles, lakes up to 20+.
* Bank z: 0 (52 %), then -3..3; bank z minus water surface: 0 (56 %), +5 (11 %), +2..+4 (13 %); bank materials jungle 34 %, grass 24 %, dirt/cave (Lost Lands) 30 %. Bank overlays/foam pieces present on 58 % of inland bank tiles (0x17A8/0x17A5 6.5 % each, 0x17A7/0x17A6 5.7 % each, 0x179F 3.8 %) — inland uses the flat-style pieces 0x17A7 (Up), 0x179D/E (West), 0x17A1/2 (North) at z = land z = 0 when the lake is flat-style.
* **Flat-style lakes** (23 %): water land 0xA8-0xAB at an elevated level (z 28 lake at 6510,191 6.6k tiles; z 35 lake at 6912,1812; z 0 lake at 6992,2224) with banks at the same z; some elevated sunk lakes exist (land 30/35, static 38, i.e. +8).
* **Rivers meeting the sea** are simply connected to the ocean wet core (14.9k ocean-connected narrow-channel tiles, z -15 96 %, ids ring-1 seafloor 0x53/0x50/0x4C/0x54 + dirt slopes 0x92/0x8F, statics objw + 0x17AC/0x17A4): no special mouth tiles; the band-width rule just shrinks.
* **Waterfalls**: 669 statics (ids 0x34ED-0x3526 family, "waterfall" in name) sitting mostly on water land 0xA8-0xAB (49 %) or rock 0x22F, at z matching the upper water level (e.g. 35-40) dropping to 0/-5; rare, hand-placed.
* Unused in Felucca: 0x1559; lily pads etc. are never on wet-core tiles (see swamps).

## 6. Swamps

* Land ids: **0x3DE9-0x3DEC** (dark swamp, texmaps 2112-2115) and **0x3DED-0x3DF0** (lighter, texmaps 2111, 2014-2016); 113,565 tiles, 637 components (largest 29.6k at x1801-2125,y2240-2460; 17.6k at x1093-1259,y2729-3035; 14.2k at x1958-2104,y921-1107). Transition tiles to grass/dirt: 0x3DC1-0x3DE8 (0x3DDB/DE/DF/E2 ~2.5-2.9k each). Flags 0 (passable, not wet).
* z: 0 (78 %), **-15 (18 %)**, -10 (1.5 %), -40 (2 %). Swamp "pools" are sunk swamp land at -15 **without any water static** (only 3 swamp tiles are in the wet core); plants sit at land z (static z - land z = 0 for 85 %).
* Statics: 0.22 per swamp tile: reeds 0xD05 (1.8k), water plants 0xD04, lilypads 0xD06-0xD0B (~600-1000 each), water lilly 0xDBC-0xDC3, sunken log 0x324E-0x3250, stump 0x324C/D, cypress 0xCF8/CFB/CFE/D01, cattails 0xCB7/CB8, grasses 0xCB9-0xCBD, "swamp" 0x3209-0x3285 (2,975 total; 0x3213/0x322C/0x3241 ~230-260 each). Old-style marsh = jungle 0xAC-0xAF at z 0 with cattails/bulrushes 0xC94/0xCB7/0xCB8 (4.6k, 62 % within 2 tiles of water).

## 7. Other water-related statics (counts; on-wet-core count)
0x1797-0x179C object water 868k (all on wet); 0x1796 55.5k; edge 0x17A3/A4 10.1k/10.2k, 0x17AC 10.1k, 0x17A9 9.7k, 0x17AB 9.6k, 0x179F/A0 8.5k/8.2k, 0x17A6 6.5k, 0x17A5 6.4k (136 on wet), 0x17A8 6.4k (104 on wet), 0x17AD 6.1k, 0x17AF 5.1k, 0x17AE 4.8k, 0x17B0 4.7k, 0x17B2 4.6k, 0x17A7 1.8k, 0x179D/E 1.2k/1.1k, 0x17A1/2 1.1k/1.1k, 0x17AA 317, 0x17B1 53.
Man-made on water: wooden plank 0x7C9 12.2k (7.6k on wet), 0x7CD 4.7k (3.4k), wooden bridge 0x7CA/0x7CB 1.5k/1.3k (1.1k/1.0k on wet), pier 0x3A5 580, brick arch 0x45 1.5k (all on wet), nodraw 0x2199 891. Rocks 0x1778 are on land (29 on wet). Full list: `water_statics_catalogue.json`.

## 8. Evidence: three 12x12 cross-sections (rows = y, columns = x; ids hex)
### West-facing beach: dry land on the WEST (left), ocean to the EAST [sand coast]  (window x=2406..2417, y=3515..3526; rows = y, cols = x)
land id:
      2406 2407 2408 2409 2410 2411 2412 2413 2414 2415 2416 2417
y 3515   ac   b9    3    4    5   23   53   5f   64   64   64   64
y 3516   ad   b9    6    6    3   27   53   5f   64   64   64   64
y 3517   af   b9    5    5    5   23   53   5f   64   64   64   64
y 3518   ae   b9    4    5    6   23   53   5f   64   64   64   64
y 3519   af   b9    3    4    5   27   53   5f   64   64   64   64
y 3520   ac   b9    5    4    3   23   53   5f   64   64   64   64
y 3521   ac   b9    3    4    6   23   53   5f   64   64   64   64
y 3522   af   b9    4    4    3   23   53   5f   64   64   64   64
y 3523   ac   b9    3    3    5   27   53   5f   64   64   64   64
y 3524   ac   b9    6    5    3   27   53   5f   64   64   64   64
y 3525   bc   c0    6    4    6   23   53   5f   64   64   64   64
y 3526   c0    3    3    3   1d   1c   53   5f   64   64   64   64
land z:
      2406 2407 2408 2409 2410 2411 2412 2413 2414 2415 2416 2417
y 3515    0    0    0    0    0    3  -15  -15  -15  -15  -15  -15
y 3516    0    0    0    0    0   -1  -15  -15  -15  -15  -15  -15
y 3517    0    0    0    0    0    1  -15  -15  -15  -15  -15  -15
y 3518    0    0    0    0    0    2  -15  -15  -15  -15  -15  -15
y 3519    0    0    0    0    0   -3  -15  -15  -15  -15  -15  -15
y 3520    0    0    0    0    0    0  -15  -15  -15  -15  -15  -15
y 3521    0    0    0    0    0    0  -15  -15  -15  -15  -15  -15
y 3522    0    0    0    0    0    2  -15  -15  -15  -15  -15  -15
y 3523    0    0    0    0    0    2  -15  -15  -15  -15  -15  -15
y 3524    0    0    0    0    0    0  -15  -15  -15  -15  -15  -15
y 3525    0    0    0    0    0    3  -15  -15  -15  -15  -15  -15
y 3526    0    0    0    0   -2    2  -15  -15  -15  -15  -15  -15
water static (core) id:
      2406 2407 2408 2409 2410 2411 2412 2413 2414 2415 2416 2417
y 3515    .    .    .    .    .    . 17ab 179c 1798 1799 1798 1799
y 3516    .    .    .    .    .    . 17a3 179a 179b 1799 1798 179c
y 3517    .    .    .    .    .    . 17a4 179a 1797 179c 1799 1798
y 3518    .    .    .    .    .    . 17a4 1798 1799 1797 179b 179a
y 3519    .    .    .    .    .    . 17a4 179c 1798 179a 179b 179c
y 3520    .    .    .    .    .    . 17a3 1798 179b 179c 1798 179a
y 3521    .    .    .    .    .    . 17a4 179c 1799 179b 1798 179b
y 3522    .    .    .    .    .    . 17a4 179b 1798 179c 1799 179c
y 3523    .    .    .    .    .    . 17a4 1799 179b 179c 179b 179b
y 3524    .    .    .    .    .    . 17a3 179b 1797 1797 1797 179b
y 3525    .    .    .    .    .    . 17a3 1797 179a 1798 179c 1799
y 3526    .    .    .    .    .    . 17a4 179a 1797 1799 1798 1798
water static z:
      2406 2407 2408 2409 2410 2411 2412 2413 2414 2415 2416 2417
y 3515    .    .    .    .    .    .   -5   -5   -5   -5   -5   -5
y 3516    .    .    .    .    .    .   -5   -5   -5   -5   -5   -5
y 3517    .    .    .    .    .    .   -5   -5   -5   -5   -5   -5
y 3518    .    .    .    .    .    .   -5   -5   -5   -5   -5   -5
y 3519    .    .    .    .    .    .   -5   -5   -5   -5   -5   -5
y 3520    .    .    .    .    .    .   -5   -5   -5   -5   -5   -5
y 3521    .    .    .    .    .    .   -5   -5   -5   -5   -5   -5
y 3522    .    .    .    .    .    .   -5   -5   -5   -5   -5   -5
y 3523    .    .    .    .    .    .   -5   -5   -5   -5   -5   -5
y 3524    .    .    .    .    .    .   -5   -5   -5   -5   -5   -5
y 3525    .    .    .    .    .    .   -5   -5   -5   -5   -5   -5
y 3526    .    .    .    .    .    .   -5   -5   -5   -5   -5   -5
overlay (foam on dry) id@z:
      2406 2407 2408 2409 2410 2411 2412 2413 2414 2415 2416 2417
y 3515    .    .    .    .    . 17a8@-5    .    .    .    .    .    .
y 3516    .    .    .    .    .    .    .    .    .    .    .    .
y 3517    .    .    .    .    .    .    .    .    .    .    .    .
y 3518    .    .    .    .    .    .    .    .    .    .    .    .
y 3519    .    .    .    .    .    .    .    .    .    .    .    .
y 3520    .    .    .    .    .    .    .    .    .    .    .    .
y 3521    .    .    .    .    .    .    .    .    .    .    .    .
y 3522    .    .    .    .    .    .    .    .    .    .    .    .
y 3523    .    .    .    .    .    .    .    .    .    .    .    .
y 3524    .    .    .    .    .    .    .    .    .    .    .    .
y 3525    .    .    .    .    .    .    .    .    .    .    .    .
y 3526    .    .    .    .    .    .    .    .    .    .    .    .

### East-facing: ocean on the WEST, dry on the EAST [sand coast]  (window x=2823..2834, y=89..100; rows = y, cols = x)
land id:
      2823 2824 2825 2826 2827 2828 2829 2830 2831 2832 2833 2834
y   89   64   64   64   5d   51   22    6    5    4    6    4    3
y   90   64   64   64   5d   51   22    6    4    4    4    5    4
y   91   64   64   64   5d   51   22    3    6    6    6    5    5
y   92   64   64   64   5d   51   26    6    5    3    3    4    5
y   93   64   64   64   5d   51   22    3    6    4    6    5    6
y   94   64   64   64   5d   51   22    6    5    3    3    3    4
y   95   64   64   64   5d   51   22    5    3    4    4    4    4
y   96   64   64   64   5d   51   22    5    4    6    3    5    5
y   97   64   64   64   5d   51   22    3    6    4    6    4    3
y   98   64   64   64   5d   51   26    3    6    5    4    5    6
y   99   64   64   64   5d   51   22    6    3    3    6    5    4
y  100   64   64   64   5d   51   26    5    3    5    4    4    4
land z:
      2823 2824 2825 2826 2827 2828 2829 2830 2831 2832 2833 2834
y   89  -15  -15  -15  -15  -15  -15   -1    3    0    0    0    0
y   90  -15  -15  -15  -15  -15  -15    1    0    0    0    0    0
y   91  -15  -15  -15  -15  -15  -15   -1    0    0    0    0    0
y   92  -15  -15  -15  -15  -15  -15   -3    0    0    0    0    0
y   93  -15  -15  -15  -15  -15  -15    0    0    0    0    0    0
y   94  -15  -15  -15  -15  -15  -15    1    0    0    0    0    0
y   95  -15  -15  -15  -15  -15  -15   -2    0    0    0    0    0
y   96  -15  -15  -15  -15  -15  -15    1    0    0    0    0    0
y   97  -15  -15  -15  -15  -15  -15   -1    0    0    0    0    0
y   98  -15  -15  -15  -15  -15  -15   -2    0    0    0    0    0
y   99  -15  -15  -15  -15  -15  -15    0    0    0    0    0    0
y  100  -15  -15  -15  -15  -15  -15    1    0    0    0    0    0
water static (core) id:
      2823 2824 2825 2826 2827 2828 2829 2830 2831 2832 2833 2834
y   89 1797 179c 1797 179b 179b 1798    .    .    .    .    .    .
y   90 179a 179c 179c 1797 1799 1797    .    .    .    .    .    .
y   91 179c 1797 1799 179a 1797 1798    .    .    .    .    .    .
y   92 179a 1799 179a 179c 179c 179c    .    .    .    .    .    .
y   93 1798 179c 179b 179c 179a 179a    .    .    .    .    .    .
y   94 1799 179b 179a 179b 1798 179a    .    .    .    .    .    .
y   95 179b 1798 1799 1798 1799 179a    .    .    .    .    .    .
y   96 179a 179b 1798 179b 1797 179b    .    .    .    .    .    .
y   97 179c 1797 1797 1797 179a 1799    .    .    .    .    .    .
y   98 1799 1797 1797 179c 1797 179c    .    .    .    .    .    .
y   99 179b 179a 179a 1797 1799 179c    .    .    .    .    .    .
y  100 179c 179a 1797 1797 1799 1798    .    .    .    .    .    .
water static z:
      2823 2824 2825 2826 2827 2828 2829 2830 2831 2832 2833 2834
y   89   -5   -5   -5   -5   -5   -5    .    .    .    .    .    .
y   90   -5   -5   -5   -5   -5   -5    .    .    .    .    .    .
y   91   -5   -5   -5   -5   -5   -5    .    .    .    .    .    .
y   92   -5   -5   -5   -5   -5   -5    .    .    .    .    .    .
y   93   -5   -5   -5   -5   -5   -5    .    .    .    .    .    .
y   94   -5   -5   -5   -5   -5   -5    .    .    .    .    .    .
y   95   -5   -5   -5   -5   -5   -5    .    .    .    .    .    .
y   96   -5   -5   -5   -5   -5   -5    .    .    .    .    .    .
y   97   -5   -5   -5   -5   -5   -5    .    .    .    .    .    .
y   98   -5   -5   -5   -5   -5   -5    .    .    .    .    .    .
y   99   -5   -5   -5   -5   -5   -5    .    .    .    .    .    .
y  100   -5   -5   -5   -5   -5   -5    .    .    .    .    .    .
overlay (foam on dry) id@z:
      2823 2824 2825 2826 2827 2828 2829 2830 2831 2832 2833 2834
y   89    .    .    .    .    .    .    .    .    .    .    .    .
y   90    .    .    .    .    .    .    .    .    .    .    .    .
y   91    .    .    .    .    .    .    .    .    .    .    .    .
y   92    .    .    .    .    .    .    .    .    .    .    .    .
y   93    .    .    .    .    .    .    .    .    .    .    .    .
y   94    .    .    .    .    .    .    .    .    .    .    .    .
y   95    .    .    .    .    .    .    .    .    .    .    .    .
y   96    .    .    .    .    .    .    .    .    .    .    .    .
y   97    .    .    .    .    .    .    .    .    .    .    .    .
y   98    .    .    .    .    .    .    .    .    .    .    .    .
y   99    .    .    .    .    .    .    .    .    .    .    .    .
y  100    .    .    .    .    .    .    .    .    .    .    .    .

### North: dry land on the NORTH (top), ocean to the SOUTH [grass coast]  (window x=1534..1545, y=1787..1798; rows = y, cols = x)
land id:
      1534 1535 1536 1537 1538 1539 1540 1541 1542 1543 1544 1545
y 1787    4    3    6    4   da   c8   d7   c7   c7   c4   c7   c5
y 1788    3    6    4    4    6    5   ce   c6   c6   c7   c7   c5
y 1789    6    4    3    5    6    5   da   c8   c8   c8   c8   c9
y 1790    6    3    5    6    6    4    6    3    3    6    3    6
y 1791    4    4    4    5    6    4    5    4    4    6    6    6
y 1792    5    6    6    6    6    6    6    6    6    6    6    6
y 1793   50   50   50   50   50   50   50   50   50   50   50   50
y 1794   5c   5c   5c   5c   5c   5c   5c   5c   5c   5c   5c   5c
y 1795   64   64   64   64   64   64   64   64   64   64   64   64
y 1796   64   64   64   64   64   64   64   64   64   64   64   64
y 1797   64   64   64   64   64   64   64   64   64   64   64   64
y 1798   64   64   64   64   64   64   64   64   64   64   64   64
land z:
      1534 1535 1536 1537 1538 1539 1540 1541 1542 1543 1544 1545
y 1787    0    2    0    4    4    7    8    8   10   10   10   11
y 1788    0    0    0    1    1    3    3    3    5    7    7    6
y 1789    0    0    0    0    1    1    0    0    1    2    1    2
y 1790    0    0    0   -1    0    0    1    1    0    0    0    1
y 1791   -1   -1    0   -1    0    0    0    0    0    0    0    0
y 1792   -3   -4   -4   -4   -3   -3   -4   -3   -3   -2    0    0
y 1793  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15
y 1794  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15
y 1795  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15
y 1796  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15
y 1797  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15
y 1798  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15  -15
water static (core) id:
      1534 1535 1536 1537 1538 1539 1540 1541 1542 1543 1544 1545
y 1787    .    .    .    .    .    .    .    .    .    .    .    .
y 1788    .    .    .    .    .    .    .    .    .    .    .    .
y 1789    .    .    .    .    .    .    .    .    .    .    .    .
y 1790    .    .    .    .    .    .    .    .    .    .    .    .
y 1791    .    .    .    .    .    .    .    .    .    .    .    .
y 1792    .    .    .    .    .    .    .    .    .    .    .    .
y 1793 179f 179f 179f 17a0 17a0 17a0 179f 179f 179f 17a0 17a0 179f
y 1794 1799 179b 179a 1798 179a 1797 1797 1798 179a 179b 1797 179a
y 1795 179a 179b 179c 179b 179c 1799 179a 179c 179a 179a 179b 1798
y 1796 1799 179a 1797 179a 1797 179b 1799 179b 179c 1799 1798 1798
y 1797 1798 179b 1798 179a 1797 179b 179b 1798 179c 179a 179b 179c
y 1798 1798 179b 179b 1797 179c 1798 179a 179b 179c 1798 1798 179b
water static z:
      1534 1535 1536 1537 1538 1539 1540 1541 1542 1543 1544 1545
y 1787    .    .    .    .    .    .    .    .    .    .    .    .
y 1788    .    .    .    .    .    .    .    .    .    .    .    .
y 1789    .    .    .    .    .    .    .    .    .    .    .    .
y 1790    .    .    .    .    .    .    .    .    .    .    .    .
y 1791    .    .    .    .    .    .    .    .    .    .    .    .
y 1792    .    .    .    .    .    .    .    .    .    .    .    .
y 1793   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5
y 1794   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5
y 1795   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5
y 1796   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5
y 1797   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5
y 1798   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5   -5
overlay (foam on dry) id@z:
      1534 1535 1536 1537 1538 1539 1540 1541 1542 1543 1544 1545
y 1787    .    .    .    .    .    .    .    .    .    .    .    .
y 1788    .    .    .    .    .    .    .    .    .    .    .    .
y 1789    .    .    .    .    .    .    .    .    .    .    .    .
y 1790    .    .    .    .    .    .    .    .    .    .    .    .
y 1791    .    .    .    .    .    .    .    .    .    .    .    .
y 1792    .    .    .    .    .    .    .    .    .    .    .    .
y 1793    .    .    .    .    .    .    .    .    .    .    .    .
y 1794    .    .    .    .    .    .    .    .    .    .    .    .
y 1795    .    .    .    .    .    .    .    .    .    .    .    .
y 1796    .    .    .    .    .    .    .    .    .    .    .    .
y 1797    .    .    .    .    .    .    .    .    .    .    .    .
y 1798    .    .    .    .    .    .    .    .    .    .    .    .