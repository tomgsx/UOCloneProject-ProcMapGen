# Land-tile taxonomy of Felucca (data-driven)

Scope: every land id with >= 20 occurrences in Felucca (7168x4096), excluding the void filler 0x244.
**949 ids** qualify. Everything below is measured from map0.mul / tiledata.mul / artLegacyMUL.uop / texmaps; the
machine-readable result is `out/land-taxonomy/land_taxonomy.json` (one record per id, keys: `name, flags, flags_raw,
texid, count, count_lostlands, material, role, a, b, visual, sectors8, sectors8_cov, nbr_pattern, nbr_b_mask,
sector_nbr_agreement, orientation_source, context, mean_rgb, tex_rgb, mean_z, mean_abs_dz, frac_stretched,
water_static_frac, impassable`).

Scripts (all in `analysis/`): `land-taxonomy_01_stats.py` (per-id counts, tiledata, art/texmap RGB, 8-sector
colours+coverage), `_02_sheets.py` (contact sheets `out/land-taxonomy/sheet_0*.png`, visually checked),
`_03_classify.py` (seed materials -> 8-direction neighbour histograms -> iterative assignment), `_04_final.py`
(visual sector classification + neighbour orientation, writes the JSON), `_05_seafloor.py` (seafloor gradient family),
`_06_report.py` (tables). Other products: `material_palette.json`, `seafloor_gradient.json`, `nbr_hist.npy`
(int64 [16384 id, 8 dir, 32 material] neighbour counts), `preview_material_map.png` (1/4 scale material map),
`preview_britain_roads.png`.

## Method (short)

1. Seed pure ids per material were picked from names + art sheets (e.g. grass 0x3-0x6, forest 0xC4-0xC7, jungle
   0xAC-0xAF, dirt 0x71-0x78, sand 0x16-0x19, snow 0x11A-0x11D, rock 0x21F-0x22F+0xE4-0xE7, cave 0x245-0x249, ...).
2. For every id and each of the 8 screen directions (N = screen-up = map (x-1,y-1); NE = (x,y-1); E = (x+1,y-1);
   SE = (x+1,y); S = (x+1,y+1); SW = (x,y+1); W = (x-1,y+1); NW = (x-1,y)) the material histogram of the neighbour
   was accumulated over the whole map (`nbr_hist.npy`). Ids whose neighbours are >= 80 % one material and whose art colour
   is within 40 RGB units of it became pure/variant; this was iterated 3 rounds (886/949 auto-assigned).
3. Visual classification: the 44x44 art diamond was split into 8 angular sectors (N..NW, N = top vertex = map corner
   (x,y)); each sector's mean RGB was matched to the nearest material reference colour *among the candidates suggested
   by neighbourhood context + tiledata name* (colour alone cannot separate grass/jungle/forest or dirt/dirt_dark/cobble).
   Sectors with < 60 % opaque pixels are "cut-outs" (cave edge tiles). `a` = majority-sector material, `b` = minority.
4. Context orientation: `nbr_pattern[dir] = {a: P, b: P}` = probability that the neighbour in that direction is pure
   a / pure b; `nbr_b_mask[dir]` = b is enriched relative to its average in that direction.
   `sector_nbr_agreement` = fraction of the 8 directions where art-sector says b exactly where the neighbourhood says b.
5. For id families whose art really is indistinguishable (jungle<->grass 0xB0-0xC3, 0x582-0x585; swamp<->grass
   0x3DED-0x3DF0) `sectors8` is null and `orientation_source = "nbr_only"` – use `nbr_b_mask`.

Roles: `pure` (use freely inside a biome), `variant` (same material, decorated or slightly different, sprinkle),
`transition` (passable two-material art), `edge` (Impassable two-material or cliff tile), `road`, `floor`
(building floors that exist as land tiles), `floor_edge`, `decor` (furrows, tree trunks, leaves, nodraw, black).
Counts: pure 195, variant 77, transition 211, edge 268, floor 100, floor_edge 34, road 5, decor 59.

Agreement between art orientation and Britannia neighbourhood: over the 401 ids with two visual materials the
mean agreement is 0.75 (70 % of ids >= 6/8 directions agree). Flat (passable) transitions agree almost perfectly
(grass/forest 0xC8-0xDB: 0.75-1.0; dirt/grass 0x79-0x8C: 0.88-1.0; road edges 0x165-0x170: 0.88-1.0; sand/grass 0x33-0x3E:
0.75-1.0; seafloor-coast 0x20-0x28: 0.75-1.0). Low agreement is concentrated in **cliff/embankment tiles**
(0x8D-0xA7, 0x2E5-0x305, 0x777-0x791, 0x98C-0x9BF, cave edges): those are vertical faces whose art stripe direction is
governed by elevation, not by which flat neighbour is which (their `mean_abs_dz` is 4-11 z per tile vs < 1.6 for flat
transitions). For those use `mean_abs_dz`, `frac_stretched` and `nbr_pattern`, not the art sectors.

## KEY FINDINGS / SURPRISES

* **Grass families.** 0x3-0x6 (2.79 M tiles, RGB 43/64/12) is plain grass. 0xC4-0xC7 "forest" (2.19 M tiles, RGB
  63/65/7, brownish leaf-litter) is the second biggest biome = Britannia's woods floor. 0xC0-0xC3 are NOT dark grass:
  they are jungle<->grass transitions (context 50/50, art indistinguishable, orientation only from neighbours).
  0xD8-0xDB are grass>forest transitions. 0x7D/0x7E/0x82/0x83 are grass with one dirt spot (grass>dirt, 1 sector).
  Real pure "dark grass" does not exist; the dark look of Britannia woods comes from 0xC4-0xC7.
* **Jungle** 0xAC-0xAF (0.5 M). jungle<->grass: 0xB0/B3/B6/B9, 0xBC-0xBF, 0xC0-0xC3, 0x100-0x103 (variants),
  0x582-0x585 — all "nbr_only" orientation. jungle<->dirt 0x26E-0x279 (passable), jungle<->rock cliffs 0xFC-0xFF,
  jungle cliffs 0x777-0x791 (Impassable, dz 4-7).
* **Roads.** The Britannia road network is **0x3FF8-0x3FFB ("NoName", 62 k tiles, 46 k of them 0x3FF8)** – a dark dirt
  that tiledata does not name; NOT 0x71-0x78. Roads are 3-4 tiles wide (axis run median 5-6), flat (85 % of
  road/grass contacts have dz = 0) and rimmed by transition tiles: forest side 0x161-0x168 (forest>road),
  0x171-0x174; road>dirt/forest 0x169-0x16C; grass side 0x16D-0x170 (grass>road); small sets 0x367-0x37A, 0x547-0x556.
  Dirt 0x71-0x78 (316 k, 60 % in Lost Lands) is used for dirt *areas* (mountain valleys, town ground, T2A), its
  flat transitions to grass are 0x79-0x7C (50/50) and 0x85-0x8C (grass-major). Cobblestone 0x3E9-0x3EC (58 k)
  is city paving (Britain streets); 0x3F9-0x405 are cobble>dirt edges.
* **Seafloor 0x4C-0x66 is a 6-step shade gradient x 4 orientations**, one ring per step going away from the shore:
  0x4C-0x4F (lightest, touches land), 0x50-53, 0x54-57, 0x58-5B, 0x5C-5F, 0x60-63 (darkest ring), then 0x64 (deep
  floor, 564 k tiles, z = -15 ± with water statics), 0x65/0x66 = lighter isolated variants. Within each quad the index
  k = id & 3 gives the shore direction: k=0 shore to the N/NE/NW (screen-up), k=1 E (screen-right), k=2 S, k=3 W
  (see `seafloor_gradient.json`, "lighter"/"nonsea" direction masks). All are at z = -15 (mean -14.5..-15.4) and 100 %
  carry water statics. All 27 share texmap 0x4C, so when stretched they all look the same.
* **Coast transition family 0x1A-0x28 (Impassable "sand")**: 0x1A/0x1B/0x1C = wet rippled sand (pure); 0x1D-0x28 =
  sand>grass edges. They come in two z-populations: 0x20,0x22,0x24,0x26,0x28 and 0x1A,0x1B are SUNK (mean z -13..-15,
  94-98 % carry a water static) – the first wet tile of a grass coast; 0x1D,0x21,0x23,0x25,0x27 sit dry at z ~ +1
  (15-19 % water statics); 0x1E/0x1F/0x1C are intermediate (z -1..-7, 49-65 %). Grass-side masks (N..NW):
  0x21/0x25 = N,NE,E; 0x22 = SE,S; 0x26 = E,SE,S; 0x23 = W,NW; 0x27 = NW,N,W; 0x28 = S,SW,W; 0x20 = SE,S,SW; 0x1D = N,NE,NW;
  0x1E = N,SW,W,NW; 0x1F = SW,W,NW; 0x24 = all sand. (0x2A-0x32 are the same art family used inland at z ~ 20 as
  grass/sand cliff edges.) Passable sand<->grass on beaches: 0x33-0x36 (sand with one grass sector), 0x37-0x3A (50/50),
  0x3B-0x3E (grass with one sand sector).
* **Impassable ids that are not rock** (full table below): the coast family above; dirt cliffs 0x8D-0xA7 (dirt face
  with grass lip; 0x8D/0x8F/0x91/0x95/0x92/0x99 are used sunk on coasts with 30-80 % water statics, the rest at z 7-26
  as inland cliffs with |dz| 4-9); dirt>rock cliffs 0xDC-0xE3; forest/rock 0xEC-0xEF, 0xF4-0xF7; jungle/rock 0xFC-0xFF;
  snow/rock 0x10C-0x117; sand/rock 0x122-0x129; snow coast 0x17C-0x185 (same sunk/dry split as sand: 0x17F,0x181,0x184
  sunk 96-99 % water); grass/rock 0x231-0x23C; forest cliffs 0x2E5-0x305; jungle cliffs 0x777-0x791; "embank"
  0x98C-0x9BF (dirt embankment with grass lip, two z-levels ~2 and ~18-25 – the bottom and top of a 16-z step);
  cave walls 0x24A-0x26D (Wall|Impassable, 0x25A/0x266 = 204 k tiles at z 21 = the rock ceiling around cave floors);
  dark cave rock 0x2BC-0x2C0; lava; void 0x1FA-0x1FF (star field, 195 k, z -13.5 = dungeon surroundings); obsidian;
  leaves 0x3AF0-0x3AF8 and tree trunks 0x2E73-0x2F0E (the giant tree at the far east of T2A, z 0).
* **Cave**: floor 0x245-0x249 (397 k, z ~ 0-1); wall/ceiling 0x25A/0x266 (z 21, dz 4); edge tiles 0x24A-0x259 are
  cave floor art with transparent cut-out corners (sectors with coverage < 0.6 in `sectors8_cov`) placed next to the
  wall; 0x25B-0x26D are the rough wall texture on sloped faces (z 3-20, dz 5-7). Stone floors 0x43A-0x441 (z -12..0)
  are dungeon floors.
* **Snow** 0x11A-0x11D pure (133 k, mostly around Dagger Isle/ice areas x 3865-6551). snow<->dirt 0x385-0x390
  (passable), snow<->rock 0x10C-0x117 (Impassable). No snow<->grass land transition exists in Felucca usage.
* **Swamp** 0x3DC1-0x3DF1 (99 k): 0x3DE9-0x3DEC are the swamp-water core (0/48/25), 0x3DDB-0x3DE8 mid tones,
  0x3DED-0x3DF0 swamp>grass rims (nbr_only), 0x3DC4-0x3DD8 are swamp-grass (visually grass, placed on the swamp rim).
  z -3..-6; no water statics.
* **Other**: furrows 0x9 (13 k, decor, + 0xA-0x13 furrow/grass edges), lava 0x1F4-0x1F7, acid 0x2E0E-0x2E39
  (Wet|Surface, TexID 0 => always flat, drawn in T2A), black 0x1AE (182 k, art missing, z 0, T2A dungeon backdrop)
  and 0x1DB, NODRAW 0x2. Water 0xA8-0xAB 15.06 M tiles.
* **Texmaps**: every natural material's texmap is ~15-20 % brighter than its art (e.g. grass art 43/64/12 vs texmap
  55/79/20) – stretched tiles render lighter than flat ones; this is inherent to the client assets.

## Recommended pure sets for the generator (ids, all passable, z-free)

grass 0x3-0x6 | forest 0xC4-0xC7 | jungle 0xAC-0xAF | dirt 0x71-0x78 | road 0x3FF8-0x3FFB | sand 0x16-0x19 |
snow 0x11A-0x11D | rock (mountain top, Impassable) 0x22C-0x22F (+0x21F-0x22B darker/rougher) | cave floor 0x245-0x249 |
cave wall 0x25A/0x266 | swamp 0x3DE9-0x3DEC | cobble 0x3E9-0x3EC | lava 0x1F4-0x1F7 | void 0x1FA-0x1FF |
water 0xA8-0xAB | seafloor rings 0x4C..0x63 + deep 0x64 | wet sand 0x1A-0x1C.

Full per-pair transition tables, material palette and the Impassable list follow.

## Material palette (count-weighted mean of pure/variant ids)

| material | tiles | art RGB | texmap RGB | pure ids (count) |
|---|---|---|---|---|
| water | 15056398 | [0, 53, 80] | [0, 0, 0] | 0x00A8(3843308), 0x00AB(3740464), 0x00AA(3737107), 0x00A9(3735423), 0x0136(48) |
| grass | 2794433 | [43, 64, 12] | [55, 79, 20] | 0x0003(759184), 0x0004(678524), 0x0005(678100), 0x0006(672220), 0x037E(665), 0x037D(418), 0x037B(402), 0x037C(232), 0x3DD1(207), 0x3DC9(206), 0x3DCA(197), 0x3DD2(196) … |
| forest | 2255062 | [63, 65, 7] | [77, 79, 12] | 0x00C4(549127), 0x00C6(548760), 0x00C5(548746), 0x00C7(547158), 0x00D5(13305), 0x00F0(7867), 0x00F2(7849), 0x00F3(7743), 0x00F1(7663), 0x015F(209), 0x015E(140), 0x06BD(112) … |
| rock | 1051580 | [88, 82, 79] | [104, 97, 93] | 0x022F(236028), 0x022C(219148), 0x022D(210881), 0x022E(208439), 0x0227(31163), 0x022B(17732), 0x0225(17414), 0x0224(17339), 0x0223(17180), 0x021F(14792), 0x0220(11692), 0x0221(10966) … |
| seafloor | 830693 | [83, 55, 14] | [66, 41, 0] | 0x0064(564020), 0x005D(16831), 0x005F(16442), 0x0051(16304), 0x0053(16294), 0x004C(13482), 0x0050(12893), 0x005C(12844), 0x005E(12612), 0x0052(12600), 0x0060(9278), 0x0054(9219) … |
| jungle | 505637 | [48, 58, 10] | [59, 71, 19] | 0x00AC(122470), 0x00AF(121674), 0x00AD(121426), 0x00AE(120797), 0x00BD(4628), 0x00BE(4592), 0x00BC(3586), 0x027D(50), 0x027B(22) |
| cave | 396840 | [109, 100, 75] | [128, 118, 91] | 0x0245(94043), 0x0246(78929), 0x0248(74995), 0x0247(74882), 0x0249(73874) |
| dirt | 316398 | [45, 36, 25] | [53, 44, 32] | 0x0075(54809), 0x0078(49357), 0x0077(48701), 0x0076(48476), 0x0071(28843), 0x0072(27804), 0x0074(27509), 0x0073(24455), 0x00E8(26) |
| cave_wall | 204110 | [82, 75, 59] | [99, 92, 74] | 0x0266(107319), 0x025A(96791) |
| void | 194945 | [18, 18, 18] | [20, 20, 20] | 0x01FA(33388), 0x01FE(32636), 0x01FF(32330), 0x01FB(32328), 0x01FC(32174), 0x01FD(32089) |
| sand | 191736 | [176, 153, 116] | [207, 179, 138] | 0x0016(50262), 0x0019(47037), 0x0018(45635), 0x0017(45282), 0x03C8(37), 0x012D(23) |
| black | 183578 | [0, 0, 0] | [0, 0, 0] |  |
| snow | 132619 | [213, 211, 214] | [246, 243, 247] | 0x011C(33295), 0x011B(32891), 0x011D(32837), 0x011A(32825), 0x03AC(32) |
| swamp | 99436 | [10, 55, 28] | [16, 60, 33] | 0x3DE9(19442), 0x3DEC(18556), 0x3DEA(18231), 0x3DEB(18140), 0x3DDF(2883), 0x3DDB(2722), 0x3DDE(2719), 0x3DE2(2487), 0x3DE5(1780), 0x3DE6(1758), 0x3DE4(1685), 0x3DE3(1648) … |
| stone_floor | 97242 | [91, 87, 77] | [99, 95, 85] |  |
| wood_floor | 90411 | [77, 51, 37] | [96, 69, 52] |  |
| dirt_dark | 61935 | [44, 35, 23] | [53, 43, 32] | 0x3FF8(46343), 0x3FFB(5550), 0x3FFA(5122), 0x3FF9(4920) |
| cobble | 58127 | [54, 47, 44] | [63, 56, 52] |  |
| leaves | 53582 | [45, 67, 43] | [43, 64, 41] |  |
| wetsand | 32614 | [160, 138, 103] | [190, 164, 124] | 0x001C(15396), 0x001A(9332), 0x001B(7886) |
| sandstone_floor | 16285 | [178, 147, 105] | [213, 175, 124] |  |
| marble_floor | 15292 | [167, 159, 153] | [207, 199, 190] |  |
| furrows | 13727 | [55, 44, 32] | [67, 54, 42] |  |
| brick_floor | 10812 | [78, 44, 40] | [91, 53, 49] |  |
| tree | 8627 | [175, 145, 100] | [173, 144, 98] |  |
| lava | 8079 | [116, 8, 0] | [138, 17, 4] | 0x01F4(2569), 0x01F6(1879), 0x01F7(1829), 0x01F5(1802) |
| acid | 7117 | [116, 143, 59] | [0, 0, 0] | 0x2E35(506), 0x2E31(492), 0x2E2C(485), 0x2E2F(466), 0x2E37(448), 0x2E2D(446), 0x2E38(446), 0x2E2A(444), 0x2E2E(439), 0x2E34(439), 0x2E2B(436), 0x2E33(430) … |
| obsidian | 5407 | [42, 37, 32] | [45, 39, 35] | 0x3FCE(1689), 0x3FCF(1205), 0x3FCD(1093) |
| tile_floor | 2790 | [81, 62, 48] | [97, 77, 62] |  |
| planks | 1761 | [99, 69, 53] | [118, 85, 64] |  |
| nodraw | 727 | [222, 222, 222] | [25, 25, 29] |  |
| flagstone | 581 | [147, 109, 62] | [173, 130, 74] |  |

## Variant / floor / decor ids per material

- **black**: 0x01AE[d](181661), 0x01DB[d](1917)
- **brick_floor**: 0x047A[f](383), 0x047B[f](451), 0x047C[f](329), 0x047D[f](359), 0x047E[f](1564), 0x047F[f](1391), 0x0480[f](926), 0x0481[f](837), 0x0482[f](920), 0x0483[f](845), 0x0484[f](1161), 0x0485[f](810), 0x048F[f](604), 0x0490[f](25), 0x0491[f](28), 0x0492[f](38), 0x0493[f](38), 0x0494[f](29), 0x0495[f](33), 0x0496[f](41)
- **cave**: 0x063B[v](41), 0x063C[v](23), 0x063D[v](24), 0x063E[v](29)
- **cobble**: 0x03E9[r](15727), 0x03EA[r](14144), 0x03EB[r](13843), 0x03EC[r](14315), 0x07AC[r](98)
- **dirt**: 0x00EA[v](56), 0x0377[v](264), 0x0378[v](159), 0x0379[v](211), 0x037A[v](208), 0x03F9[v](396), 0x03FA[v](738), 0x03FB[v](907), 0x03FC[v](816), 0x03FD[v](718), 0x0401[v](1821), 0x0553[v](124)
- **flagstone**: 0x0201[f](246), 0x0202[f](148), 0x0203[f](105), 0x0204[f](82)
- **forest**: 0x00D7[v](12699), 0x00F8[v](535), 0x00F9[v](75), 0x0163[v](1364), 0x0164[v](1045), 0x01AF[v](166)
- **furrows**: 0x0009[d](13350), 0x000E[d](45), 0x0013[d](34), 0x0150[d](298)
- **grass**: 0x067D[v](35), 0x067F[v](47), 0x0680[v](48), 0x3DC3[v](1839)
- **jungle**: 0x0100[v](1541), 0x0101[v](1555), 0x0102[v](1542), 0x0103[v](1596), 0x0276[v](40), 0x027A[v](33), 0x0590[v](85)
- **leaves**: 0x2E74[d](114), 0x2E75[d](55), 0x2E7B[d](59), 0x2E9D[d](117), 0x2E9E[d](118), 0x2EA4[d](105), 0x2EA5[d](118), 0x2EA6[d](117), 0x2EAC[d](111), 0x2EB9[d](77), 0x2EBC[d](80), 0x2EBD[d](125), 0x2EC1[d](123), 0x2EDB[d](56), 0x3AF0[d](5127), 0x3AF1[d](7376), 0x3AF2[d](6648), 0x3AF3[d](5984), 0x3AF4[d](5738), 0x3AF5[d](5313), 0x3AF6[d](5577), 0x3AF7[d](5228), 0x3AF8[d](5216)
- **marble_floor**: 0x0486[f](1712), 0x0487[f](1607), 0x0488[f](1609), 0x0489[f](1648), 0x04E9[f](720), 0x04EA[f](670), 0x04EF[f](1812), 0x04F0[f](1809), 0x04F1[f](1931), 0x04F2[f](1774)
- **nodraw**: 0x0002[d](727)
- **obsidian**: 0x3FB4[v](158), 0x3FB5[v](278), 0x3FB6[v](239), 0x3FB7[v](100), 0x3FB8[v](51), 0x3FB9[v](83), 0x3FBA[v](94), 0x3FBB[v](73), 0x3FBC[v](92), 0x3FBD[v](64), 0x3FBE[v](85), 0x3FBF[v](103)
- **planks**: 0x0296[f](947), 0x0297[f](814)
- **rock**: 0x00F7[v](571), 0x0104[v](140), 0x0106[v](136), 0x0107[v](186), 0x0110[v](370), 0x0111[v](390), 0x0112[v](391), 0x0113[v](437), 0x0237[v](1694), 0x0238[v](1342), 0x06FC[v](76), 0x06FD[v](26), 0x071F[v](22), 0x0720[v](42), 0x07D2[v](65), 0x09EC[v](231), 0x09ED[v](68), 0x09EE[v](132), 0x09EF[v](134), 0x09F0[v](37), 0x09F1[v](52), 0x09F2[v](34), 0x09F3[v](38), 0x3FD1[v](644)
- **sand**: 0x012B[v](27), 0x07BD[v](1251), 0x07BE[v](1111), 0x07BF[v](1071)
- **sandstone_floor**: 0x0442[f](2550), 0x0443[f](2988), 0x0446[f](1753), 0x0447[f](1786), 0x0448[f](1683), 0x0449[f](1776), 0x044A[f](939), 0x044B[f](923), 0x044C[f](957), 0x044D[f](876), 0x0454[f](54)
- **snow**: 0x0179[v](188), 0x017A[v](315), 0x017B[v](236)
- **stone_floor**: 0x0436[f](10978), 0x0437[f](575), 0x0438[f](633), 0x0439[f](555), 0x043A[f](10015), 0x043B[f](9227), 0x043C[f](8840), 0x043D[f](8945), 0x043E[f](18246), 0x043F[f](8340), 0x0440[f](8328), 0x0441[f](11840), 0x04EB[f](190), 0x04EC[f](187), 0x04ED[f](167), 0x04EE[f](176)
- **tile_floor**: 0x0418[f](30), 0x041E[f](318), 0x041F[f](347), 0x0420[f](20), 0x0422[f](28), 0x0423[f](32), 0x0428[f](690), 0x042F[f](481), 0x048A[f](46), 0x048B[f](321), 0x048C[f](81), 0x048D[f](200), 0x048E[f](196)
- **tree**: 0x2E73[d](74), 0x2E89[d](113), 0x2E90[d](592), 0x2E94[d](59), 0x2E95[d](51), 0x2EA1[d](88), 0x2EA2[d](1236), 0x2EA3[d](59), 0x2EAA[d](860), 0x2EAB[d](61), 0x2EBA[d](32), 0x2EBF[d](71), 0x2EC4[d](36), 0x2EC8[d](1176), 0x2ECC[d](22), 0x2ECE[d](25), 0x2ED1[d](43), 0x2ED2[d](50), 0x2EE3[d](22), 0x2EEB[d](825), 0x2EED[d](30), 0x2EF8[d](140), 0x2EF9[d](48), 0x2EFA[d](42), 0x2F00[d](974), 0x2F02[d](86), 0x2F09[d](48), 0x2F0D[d](1107), 0x2F0E[d](657)
- **water**: 0x3FF0[v](48)
- **wood_floor**: 0x0406[f](13857), 0x0407[f](14355), 0x0408[f](14554), 0x0409[f](14301), 0x040A[f](7748), 0x040B[f](7441), 0x040C[f](7308), 0x040D[f](7330), 0x040E[f](268), 0x040F[f](112), 0x0411[f](1066), 0x0412[f](174), 0x0413[f](125), 0x0414[f](116), 0x0415[f](539), 0x04B3[f](165), 0x04B4[f](111), 0x04B5[f](105), 0x04B6[f](163), 0x04BA[f](22), 0x04BC[f](139), 0x04BD[f](132), 0x04BE[f](133), 0x04BF[f](147)

## Transition / edge ids per material pair (A>B = majority A, minority B). `[T]`=passable transition, `[E]`=Impassable edge/cliff, `[F]`=floor edge. ag=art-sector vs neighbour agreement (8 dirs)


### forest <-> grass  (28 ids, 205301 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x00C8 | forest | forest>grass | T | 12909 | 7.17 | 0.46 | n/a | aaaabbba | None |
| 0x00C9 | forest | forest>grass | T | 12205 | 6.62 | 0.35 | n/a | aaaabbba | None |
| 0x00CA | forest | forest>grass | T | 3247 | 5.46 | 0.39 | n/a | aaabbbbb | None |
| 0x00CB | forest | grass>forest | T | 27179 | 6.98 | 0.39 | n/a | baaaaabb | None |
| 0x00CC | forest | forest>grass | T | 2905 | 5.98 | 0.42 | n/a | abbbbbaa | None |
| 0x00CD | forest | forest>grass | T | 3118 | 5.78 | 0.42 | n/a | abbbbbaa | None |
| 0x00CE | forest | forest>grass | T | 15067 | 6.14 | 0.36 | n/a | bbaaaabb | None |
| 0x00CF | forest | forest>grass | T | 14860 | 6.24 | 0.38 | n/a | bbaaaabb | None |
| 0x00D0 | forest | forest>grass | T | 4653 | 4.77 | 0.34 | n/a | bbaaabbb | None |
| 0x00D1 | forest | forest>grass | T | 20922 | 5.97 | 0.34 | n/a | bbbaaaaa | None |
| 0x00D2 | forest | forest>grass | T | 4610 | 5.93 | 0.47 | n/a | bbbbaaab | None |
| 0x00D3 | forest | forest>grass | T | 4316 | 5.04 | 0.37 | n/a | bbbbaaab | None |
| 0x00D4 | forest | forest>grass | T | 13718 | 7.74 | 0.38 | n/a | aaabbbaa | None |
| 0x00D6 | forest | forest>grass | T | 12819 | 6.45 | 0.34 | n/a | aabbaaaa | None |
| 0x00D8 | grass | grass>forest | T | 11224 | 8.06 | 0.46 | n/a | bbaaaaab | None |
| 0x00D9 | grass | grass>forest | T | 16838 | 6.7 | 0.42 | n/a | aaabbbaa | None |
| 0x00DA | grass | grass>forest | T | 13564 | 5.72 | 0.38 | n/a | aabbaaaa | None |
| 0x00DB | grass | grass>forest | T | 10472 | 6.26 | 0.39 | n/a | aaaaabbb | None |
| 0x06AF | forest | forest>grass | T | 47 | 23.13 | 3.24 | n/a | bbbbaaaa | None |
| 0x06B0 | forest | forest>grass | T | 25 | 18.92 | 1.47 | n/a | bbaaaabb | None |
| 0x06B1 | forest | forest>grass | T | 147 | 14.18 | 1.71 | n/a | aaaabbba | None |
| 0x06B2 | forest | forest>grass | T | 115 | 10.76 | 1.33 | n/a | bbbaaaaa | None |
| 0x06B3 | forest | forest>grass | T | 60 | 10.35 | 1.25 | n/a | baaaaabb | None |
| 0x06B4 | forest | forest>grass | T | 84 | 16.99 | 1.55 | n/a | aabbbaaa | None |
| 0x06B5 | grass | grass>forest | T | 31 | 10.58 | 4.3 | n/a | bbbaaaab | None |
| 0x06B9 | grass | grass>forest | T | 61 | 18.41 | 2.85 | n/a | aabbbbaa | None |
| 0x06BA | grass | forest>grass | T | 20 | 19.35 | 0.68 | n/a | bbbaaaab | None |
| 0x06C1 | grass | grass>forest | T | 85 | 7.4 | 3.61 | n/a | aabbbaaa | None |

### dirt <-> grass  (52 ids, 108052 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x0079 | dirt | dirt>grass | T | 3008 | 6.46 | 1.37 | aaaabbaa | aaabbbaa | 0.88 |
| 0x007A | dirt | dirt>grass | T | 2662 | 7.16 | 1.57 | bbaaaaaa | bbaaaaab | 0.88 |
| 0x007B | dirt | dirt>grass | T | 3015 | 5.47 | 1.16 | aaaaaaba | aaaaabbb | 0.75 |
| 0x007C | dirt | dirt>grass | T | 2917 | 6.36 | 1.27 | abbaaaaa | abbbaaaa | 0.88 |
| 0x007D | grass | grass>dirt | T | 4993 | 5.1 | 0.93 | aaaabaaa | aaaabaaa | 1.0 |
| 0x007E | grass | grass>dirt | T | 5467 | 5.13 | 0.8 | baaaaaaa | baaaaaaa | 1.0 |
| 0x0082 | dirt | grass>dirt | T | 5212 | 4.71 | 0.83 | aaaaaaba | aaaaaaba | 1.0 |
| 0x0083 | dirt | grass>dirt | T | 5349 | 4.62 | 0.75 | aabaaaaa | aabaaaaa | 1.0 |
| 0x0085 | dirt | grass>dirt | T | 6130 | 6.16 | 1.02 | bbbaaaaa | bbbaaaaa | 1.0 |
| 0x0086 | dirt | grass>dirt | T | 4073 | 5.01 | 0.69 | bbbaaaaa | bbbaaaaa | 1.0 |
| 0x0087 | dirt | grass>dirt | T | 6493 | 6.32 | 0.97 | baaaaabb | baaaaabb | 1.0 |
| 0x0088 | dirt | grass>dirt | T | 4064 | 5.5 | 0.99 | baaaaabb | baaaaabb | 1.0 |
| 0x0089 | dirt | grass>dirt | T | 5895 | 6.08 | 1.29 | aabbbaaa | aabbbaaa | 1.0 |
| 0x008A | dirt | grass>dirt | T | 4113 | 5.8 | 0.73 | aabbbaaa | aabbbaaa | 1.0 |
| 0x008B | dirt | grass>dirt | T | 5128 | 5.96 | 1.1 | aaaabbba | aaaabbba | 1.0 |
| 0x008C | dirt | grass>dirt | T | 4388 | 5.24 | 0.91 | aaaabbba | aaaabbba | 1.0 |
| 0x0090 | dirt | dirt>grass | E | 1628 | 22.42 | 5.49 | aaabaaab | abbbbbaa | 0.38 |
| 0x0092 | dirt | dirt>grass | E | 1884 | -11.31 | 4.95 | aaaaabaa | aaabbbab | 0.62 |
| 0x0093 | dirt | dirt>grass | E | 1528 | 7.83 | 6.04 | abaaaaaa | bbbbaaaa | 0.62 |
| 0x0094 | dirt | dirt>grass | E | 1634 | 24.05 | 5.82 | abaaabaa | bbaabbba | 0.62 |
| 0x0096 | dirt | dirt>grass | E | 278 | -4.26 | 8.67 | aabbbaaa | abbbbbaa | 0.75 |
| 0x0097 | dirt | dirt>grass | E | 482 | 17.76 | 8.18 | aaabbbaa | abbbbbbb | 0.5 |
| 0x0098 | dirt | dirt>grass | E | 852 | 6.31 | 2.33 | bbaaaaab | bbaaabbb | 0.75 |
| 0x0099 | dirt | dirt>grass | E | 696 | -10.07 | 5.66 | aaaabbba | aaabbbba | 0.88 |
| 0x009A | dirt | dirt>grass | E | 609 | 8.45 | 5.29 | bbbaaaaa | bbbaaaab | 0.88 |
| 0x009B | dirt | dirt>grass | E | 479 | 6.75 | 5.54 | baaaaabb | baaaabbb | 0.88 |
| 0x009C | dirt | dirt>grass | E | 935 | 15.5 | 4.54 | abaabbba | abbbbbbb | 0.62 |
| 0x009D | dirt | dirt>grass | E | 992 | 15.52 | 4.39 | abaaabba | aaabbbbb | 0.5 |
| 0x009E | dirt | dirt>grass | E | 1388 | 15.43 | 4.33 | baaaaabb | abbbbbaa | 0.0 |
| 0x009F | dirt | dirt>grass | E | 869 | 14.33 | 5.17 | aaabaaaa | bbbbbbbb | 0.12 |
| 0x00A0 | dirt | dirt>grass | E | 4491 | 13.45 | 7.08 | aaabbbba | bbbaaabb | 0.12 |
| 0x00A1 | dirt | dirt>grass | E | 3668 | 6.75 | 6.04 | aaaaabbb | abababbb | 0.75 |
| 0x00A2 | dirt | grass>dirt | E | 3687 | 6.85 | 7.7 | aaaaabbb | aaaaabbb | 1.0 |
| 0x00A3 | dirt | dirt>grass | E | 4450 | 6.79 | 2.68 | bbaaaabb | aaabbbaa | 0.12 |
| 0x00A4 | dirt | dirt>grass | E | 80 | 23.73 | 5.21 | aaabbbba | bbabbbbb | 0.62 |
| 0x00A5 | dirt | dirt>grass | E | 98 | 20.52 | 4.15 | baaaaabb | bbbbabbb | 0.5 |
| 0x00A6 | dirt | dirt>grass | E | 92 | 25.86 | 3.98 | aabbbaaa | bbaaabab | 0.12 |
| 0x00A7 | dirt | dirt>grass | E | 92 | 26.33 | 3.26 | bbbbaaaa | abaabbbb | 0.12 |
| 0x016D | dirt | grass>dirt | T | 712 | 2.83 | 0.16 | abbbaaaa | abbbaaaa | 1.0 |
| 0x016E | dirt | grass>dirt | T | 710 | 2.97 | 0.2 | aaaaabbb | aaaaabbb | 1.0 |
| 0x016F | dirt | grass>dirt | T | 775 | 3.35 | 0.44 | aaabbbaa | aaabbbba | 0.88 |
| 0x0170 | dirt | dirt>grass | T | 710 | 3.4 | 0.11 | aabbbbaa | aabbbbba | 0.88 |
| 0x0367 | dirt | dirt>grass | T | 150 | 2.5 | 0.29 | bbbbaaaa | bbbbaaaa | 1.0 |
| 0x0368 | dirt | dirt>grass | T | 134 | 3.03 | 0.17 | baaaabbb | baaaabbb | 1.0 |
| 0x0369 | dirt | dirt>grass | T | 150 | 3.33 | 0.17 | abbbbaaa | abbbbaaa | 1.0 |
| 0x036A | dirt | dirt>grass | T | 130 | 2.42 | 0.19 | aaaabbbb | aaaabbbb | 1.0 |
| 0x036B | dirt | dirt>grass | T | 133 | 4.22 | 0.66 | bbbaaaab | bbbaaaab | 1.0 |
| 0x036C | dirt | dirt>grass | T | 179 | 5.58 | 0.44 | bbaaaabb | bbaaaabb | 1.0 |
| 0x036D | dirt | dirt>grass | T | 133 | 3.41 | 0.13 | aabbbbaa | aabbbbaa | 1.0 |
| 0x036E | dirt | dirt>grass | T | 124 | 4.09 | 0.14 | aaabbbba | aaabbbba | 1.0 |
| 0x0373 | grass | grass>dirt | T | 113 | 3.95 | 0.15 | bbaaaaaa | bbbaaaab | 0.75 |
| 0x0376 | grass | grass>dirt | T | 80 | 5.89 | 0.43 | aaaabbaa | aaabbbba | 0.75 |

### grass <-> sand  (30 ids, 68419 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x001D | sand | sand>grass | E | 7153 | 2.04 | 2.52 | bbaaaaab | bbbaaabb | 0.75 |
| 0x001E | sand | grass>sand | E | 6447 | -1.11 | 7.08 | baaaabbb | aaaaaaaa | 0.5 |
| 0x001F | sand | sand>grass | E | 6274 | -0.66 | 6.93 | aaaaabbb | baaabbbb | 0.75 |
| 0x0020 | sand | sand>grass | E | 6065 | -14.62 | 6.53 | aaabbbaa | aabbbbaa | 0.88 |
| 0x0021 | sand | sand>grass | E | 7195 | 0.63 | 6.15 | bbbaaaaa | bbbbaaab | 0.75 |
| 0x0022 | sand | sand>grass | E | 8904 | -13.94 | 4.43 | aaabbaaa | aabbbaaa | 0.88 |
| 0x0023 | sand | sand>grass | E | 9283 | 1.03 | 6.11 | aaaaaabb | bbaaabbb | 0.62 |
| 0x0025 | sand | sand>grass | E | 2294 | 1.04 | 6.03 | bbbaaaaa | bbbbaaab | 0.75 |
| 0x0026 | sand | sand>grass | E | 3126 | -13.53 | 4.63 | aabbbaaa | aabbbaaa | 1.0 |
| 0x0027 | sand | sand>grass | E | 2876 | 0.87 | 6.1 | baaaaabb | bbaaabbb | 0.75 |
| 0x0028 | sand | sand>grass | E | 2026 | -13.44 | 4.36 | aaaabbba | aaaabbba | 1.0 |
| 0x002A | sand | sand>grass | E | 30 | 22.43 | 2.76 | aabbbaaa | bbbbbabb | 0.5 |
| 0x002D | sand | grass>sand | E | 31 | 20.81 | 2.36 | aaaabbba | aaaaaaaa | 0.62 |
| 0x0030 | sand | grass>sand | E | 39 | 15.46 | 3.62 | bbbaaaaa | aaaaaaaa | 0.62 |
| 0x0032 | sand | grass>sand | E | 134 | 23.45 | 2.63 | bbaaabba | aaaaaaaa | 0.5 |
| 0x0033 | sand | sand>grass | T | 255 | 6.03 | 1.18 | aaaabaaa | aaabbbaa | 0.75 |
| 0x0034 | sand | sand>grass | T | 272 | 9.9 | 1.1 | aaaaaaba | aaaaabbb | 0.75 |
| 0x0035 | sand | sand>grass | T | 275 | 7.24 | 1.35 | baaaaaaa | bbaaaaab | 0.75 |
| 0x0036 | sand | sand>grass | T | 232 | 11.15 | 0.96 | aabaaaaa | aabbaaaa | 0.88 |
| 0x0037 | sand | sand>grass | T | 1015 | 11.54 | 0.79 | aabbbaaa | abbbbbaa | 0.75 |
| 0x0038 | sand | sand>grass | T | 1220 | 13.2 | 0.9 | baaaaabb | bbaaabbb | 0.75 |
| 0x0039 | sand | sand>grass | T | 997 | 11.87 | 1.05 | aaaabbba | aaabbbbb | 0.75 |
| 0x003A | sand | sand>grass | T | 971 | 11.52 | 0.68 | bbbaaaaa | bbbbaaab | 0.75 |
| 0x003B | grass | grass>sand | T | 281 | 10.78 | 0.98 | aabaaaaa | aabbaaaa | 0.88 |
| 0x003C | grass | grass>sand | T | 242 | 11.72 | 0.82 | aaaaaaba | aaaaabbb | 0.75 |
| 0x003D | grass | grass>sand | T | 285 | 7.8 | 1.08 | aaaabaaa | aaabbaaa | 0.88 |
| 0x003E | grass | grass>sand | T | 268 | 6.81 | 1.14 | baaaaaaa | baaaaaab | 0.88 |
| 0x0049 | sand | grass>sand | E | 107 | 12.2 | 8.96 | baaaabbb | aaaaaabb | 0.75 |
| 0x004B | sand | grass>sand | E | 99 | 10.15 | 7.98 | bbaaaaab | baaaaaaa | 0.75 |
| 0x01AA | sand | sand>grass | T | 23 | 0.0 | 0.0 | aaabbbaa | aabbbbaa | 0.88 |

### grass <-> jungle  (15 ids, 64904 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x00B0 | jungle | jungle>grass | T | 9147 | 7.24 | 0.65 | n/a | aaaabbba | None |
| 0x00B1 | NoName | grass>jungle | T | 140 | 34.09 | 0.09 | n/a | bbaaaaab | None |
| 0x00B2 | NoName | grass>jungle | T | 234 | 36.43 | 0.18 | n/a | abbbaaaa | None |
| 0x00B3 | jungle | jungle>grass | T | 8999 | 6.58 | 0.58 | n/a | baaaaabb | None |
| 0x00B6 | jungle | jungle>grass | T | 5769 | 5.57 | 0.59 | n/a | bbbaaaaa | None |
| 0x00B9 | jungle | jungle>grass | T | 7498 | 4.97 | 0.56 | n/a | aabbbbaa | None |
| 0x00BF | jungle | jungle>grass | T | 8121 | 7.21 | 0.63 | n/a | abbbaaaa | None |
| 0x00C0 | grass | grass>jungle | T | 3936 | 4.85 | 0.57 | n/a | bbaaaaab | None |
| 0x00C1 | grass | grass>jungle | T | 5890 | 6.93 | 0.62 | n/a | abbbaaaa | None |
| 0x00C2 | grass | jungle>grass | T | 6838 | 7.64 | 0.73 | n/a | bbbaaabb | None |
| 0x00C3 | grass | grass>jungle | T | 4484 | 5.56 | 0.57 | n/a | aaaaaabb | None |
| 0x0582 | jungle | jungle>grass | T | 2538 | 14.58 | 0.69 | n/a | baaaabbb | None |
| 0x0583 | jungle | jungle>grass | T | 355 | 39.77 | 0.38 | n/a | aabbbbaa | None |
| 0x0584 | jungle | jungle>grass | T | 443 | 38.81 | 0.35 | n/a | aaaabbba | None |
| 0x0585 | jungle | jungle>grass | T | 512 | 41.44 | 0.35 | n/a | bbbaaaaa | None |

### dirt <-> forest  (57 ids, 47363 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x014C | dirt | forest>dirt | T | 112 | -2.76 | 1.56 | aaaabbaa | aaabbbba | 0.75 |
| 0x014D | dirt | forest>dirt | T | 24 | 1.62 | 0.02 | aaaaaabb | aaaaaabb | 1.0 |
| 0x014E | dirt | forest>dirt | T | 26 | 0.19 | 0.0 | bbaaaaaa | bbbaaaaa | 0.88 |
| 0x014F | dirt | forest>dirt | T | 62 | 0.53 | 0.07 | aaabbaaa | aaabbaaa | 1.0 |
| 0x0169 | dirt | dirt>forest | T | 1139 | 1.34 | 0.24 | aaaaabbb | aaaaabbb | 1.0 |
| 0x016A | dirt | dirt>forest | T | 1276 | 1.31 | 0.17 | abbbaaaa | abbbaaaa | 1.0 |
| 0x016B | dirt | dirt>forest | T | 1076 | 1.33 | 0.24 | bbaaaaab | bbaaaaab | 1.0 |
| 0x016C | dirt | dirt>forest | T | 1329 | 1.07 | 0.13 | aaabbbaa | aaabbbaa | 1.0 |
| 0x0171 | dirt | forest>dirt | T | 283 | 0.5 | 0.04 | abbbaaaa | bbbbaaaa | 0.88 |
| 0x0172 | dirt | forest>dirt | T | 181 | 0.67 | 0.04 | aaaaabbb | baaaabbb | 0.88 |
| 0x0173 | dirt | forest>dirt | T | 262 | 0.04 | 0.01 | bbaaaaab | bbbaaaab | 0.88 |
| 0x0174 | dirt | forest>dirt | T | 405 | 0.18 | 0.05 | aaabbbaa | aaabbbba | 0.88 |
| 0x02E7 | dirt | dirt>forest | E | 634 | 5.17 | 6.65 | aaabaaaa | abbbbbaa | 0.5 |
| 0x02E8 | dirt | dirt>forest | E | 1317 | 23.13 | 8.67 | aaabaaab | abababbb | 0.62 |
| 0x02EA | dirt | dirt>forest | E | 840 | 3.06 | 7.57 | aaaaabaa | aaabbbbb | 0.5 |
| 0x02EB | dirt | dirt>forest | E | 790 | 21.02 | 6.35 | abaaaaaa | bbbbaaab | 0.5 |
| 0x02EC | dirt | dirt>forest | E | 1453 | 21.71 | 8.39 | abaaabaa | abababbb | 0.62 |
| 0x02EE | dirt | dirt>forest | E | 320 | 2.21 | 6.6 | aabbbaaa | abbbbbaa | 0.75 |
| 0x02EF | dirt | dirt>forest | E | 2745 | 11.27 | 9.99 | aaabbbaa | abbbbbbb | 0.5 |
| 0x02F0 | dirt | dirt>forest | E | 2638 | 25.0 | 1.55 | bbaaaaab | bbbbabbb | 0.5 |
| 0x02F1 | dirt | dirt>forest | E | 386 | 2.91 | 7.53 | aaaabbba | aaabbbbb | 0.75 |
| 0x02F2 | dirt | dirt>forest | E | 358 | 22.69 | 6.61 | bbbaaaaa | bbbbaaab | 0.75 |
| 0x02F3 | dirt | dirt>forest | E | 308 | 24.37 | 7.12 | baaaaabb | bbaaabbb | 0.75 |
| 0x02F4 | dirt | forest>dirt | E | 1451 | 22.47 | 8.45 | baabaaab | babaaaba | 0.5 |
| 0x02F5 | dirt | dirt>forest | E | 1482 | 22.36 | 8.3 | abaabbba | bbababab | 0.38 |
| 0x02F6 | dirt | dirt>forest | E | 1356 | 22.75 | 8.52 | baabaabb | abababab | 0.5 |
| 0x02F7 | dirt | dirt>forest | E | 1339 | 23.49 | 8.6 | aabbaaaa | abababab | 0.5 |
| 0x02F8 | dirt | forest>dirt | E | 728 | 28.35 | 10.34 | bbaaaaab | aabababa | 0.25 |
| 0x02F9 | dirt | dirt>forest | E | 2767 | 22.72 | 10.23 | aaaabbbb | bbabbbbb | 0.62 |
| 0x02FA | dirt | forest>dirt | E | 2695 | 16.68 | 10.45 | aaaaabbb | aaaaaaba | 0.75 |
| 0x02FB | dirt | forest>dirt | E | 739 | 17.62 | 8.28 | aaabbbaa | bababaaa | 0.5 |
| 0x02FC | dirt | dirt>forest | E | 137 | 33.36 | 6.63 | aaabbbba | bbaaabbb | 0.38 |
| 0x02FD | dirt | dirt>forest | E | 191 | 33.58 | 4.52 | baaaaabb | bbbbabab | 0.38 |
| 0x02FE | dirt | dirt>forest | E | 143 | 34.71 | 6.95 | aabbbaaa | bbabaaab | 0.38 |
| 0x02FF | dirt | dirt>forest | E | 166 | 31.6 | 4.22 | babbaaaa | bbababbb | 0.38 |
| 0x0547 | dirt | dirt>forest | T | 91 | 4.76 | 1.29 | bbbbaaaa | bbbbaaaa | 1.0 |
| 0x0548 | dirt | dirt>forest | T | 118 | 4.57 | 1.11 | baaaabbb | baaaabbb | 1.0 |
| 0x0549 | dirt | dirt>forest | T | 72 | 8.65 | 1.18 | abbbbaaa | abbbbaaa | 1.0 |
| 0x054A | dirt | dirt>forest | T | 79 | 10.1 | 0.95 | aaaabbbb | aaaabbbb | 1.0 |
| 0x054B | dirt | dirt>forest | T | 102 | 3.78 | 0.79 | bbbaaaab | bbbaaaaa | 0.88 |
| 0x054C | dirt | dirt>forest | T | 72 | 1.11 | 0.95 | bbaaaabb | baaaaabb | 0.88 |
| 0x09AC | embank | dirt>forest | E | 1052 | 24.72 | 6.16 | aaaaaaab | bbaaabbb | 0.5 |
| 0x09AD | embank | dirt>forest | E | 1387 | 7.85 | 6.51 | aaabaaaa | abbbbbaa | 0.5 |
| 0x09AE | embank | dirt>forest | E | 1484 | 8.55 | 6.74 | aaaaabaa | aaabbbbb | 0.5 |
| 0x09AF | embank | dirt>forest | E | 1212 | 24.81 | 6.09 | abaaaaaa | bbbbaaab | 0.5 |
| 0x09B0 | embank | dirt>forest | E | 1437 | 7.88 | 6.65 | abaabbba | aaabbbbb | 0.62 |
| 0x09B1 | embank | dirt>forest | E | 1141 | 24.44 | 6.09 | abaaabaa | bbbbaaaa | 0.5 |
| 0x09B2 | embank | dirt>forest | E | 1380 | 7.95 | 6.84 | abaabbba | aaabbbbb | 0.62 |
| 0x09B3 | embank | dirt>forest | E | 1177 | 23.93 | 5.98 | abaaaaaa | bbbbaabb | 0.38 |
| 0x09B4 | embank | dirt>forest | E | 1291 | 7.42 | 6.84 | aaabaaab | abbbbbaa | 0.38 |
| 0x09B5 | embank | dirt>forest | E | 1100 | 24.31 | 6.21 | baaaaabb | bbbaabbb | 0.62 |
| 0x09B6 | embank | dirt>forest | E | 1281 | 8.47 | 6.54 | aaabaaaa | abbbbbaa | 0.5 |
| 0x09B7 | embank | dirt>forest | E | 1106 | 24.39 | 6.18 | aaabaaaa | bbaaabbb | 0.25 |
| 0x09B9 | embank | dirt>forest | E | 178 | 22.7 | 5.86 | aaaaabba | bbaabbbb | 0.5 |
| 0x09BA | embank | dirt>forest | E | 132 | 22.2 | 4.91 | bbaaaaba | bbbbaabb | 0.62 |
| 0x09BD | embank | dirt>forest | E | 175 | 24.26 | 5.88 | abbabaaa | bbbbbaab | 0.62 |
| 0x09BF | embank | dirt>forest | E | 138 | 21.75 | 4.72 | bbaaaaaa | bbbaabbb | 0.5 |

### grass <-> swamp  (6 ids, 39488 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x3DCF | NoName | grass>swamp | T | 268 | -11.64 | 0.28 | n/a | aaaaabbb | None |
| 0x3DED | NoName | swamp>grass | T | 10019 | -5.06 | 0.7 | n/a | aabbbbba | None |
| 0x3DEE | NoName | swamp>grass | T | 10012 | -4.54 | 0.7 | n/a | baaabbbb | None |
| 0x3DEF | NoName | swamp>grass | T | 9984 | -4.76 | 0.7 | n/a | bbbaaabb | None |
| 0x3DF0 | NoName | swamp>grass | T | 9181 | -5.14 | 0.78 | n/a | bbabaaab | None |
| 0x3DF1 | NoName | grass>swamp | T | 24 | 17.21 | 0.16 | n/a | aaabbbbb | None |

### dirt <-> jungle  (49 ids, 32404 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x026E | jungle | jungle>dirt | T | 129 | 23.49 | 2.49 | bbbaaaaa | bbbbaaab | 0.75 |
| 0x026F | jungle | jungle>dirt | T | 118 | 14.8 | 1.88 | baaaaabb | baaaabbb | 0.88 |
| 0x0270 | jungle | jungle>dirt | T | 200 | 14.77 | 3.96 | aabbbaaa | aabbbbaa | 0.88 |
| 0x0271 | jungle | jungle>dirt | T | 188 | 17.72 | 3.92 | aaaabbba | aaabbbba | 0.88 |
| 0x0272 | dirt | dirt>jungle | T | 38 | 10.37 | 2.29 | aaabbbaa | aaaabaaa | 0.75 |
| 0x0273 | dirt | dirt>jungle | T | 63 | 15.6 | 4.46 | bbaaaaab | bbaaaaab | 1.0 |
| 0x0274 | dirt | dirt>jungle | T | 53 | 15.23 | 3.39 | abbbaaaa | abbaaaaa | 0.88 |
| 0x0275 | dirt | dirt>jungle | T | 58 | 22.5 | 2.12 | aaaaaabb | aaaaabbb | 0.88 |
| 0x0277 | jungle | jungle>dirt | T | 57 | 14.72 | 2.95 | aaaabaaa | aaabbbaa | 0.75 |
| 0x0278 | jungle | jungle>dirt | T | 51 | 22.82 | 1.5 | aabaaaaa | abbbaaaa | 0.75 |
| 0x0279 | jungle | jungle>dirt | T | 46 | 16.17 | 2.73 | aaaaaaba | aaaaabbb | 0.75 |
| 0x0779 | dirt | dirt>jungle | E | 1263 | -1.94 | 7.48 | aaabaaaa | aabbbbaa | 0.62 |
| 0x077A | dirt | dirt>jungle | E | 927 | 13.14 | 7.32 | aaabaaaa | aaabbbab | 0.62 |
| 0x077D | dirt | dirt>jungle | E | 1344 | 15.52 | 6.08 | abaaaaaa | bbbbaaab | 0.5 |
| 0x077E | dirt | dirt>jungle | E | 924 | 11.76 | 7.41 | abaaabaa | abababaa | 0.88 |
| 0x0780 | dirt | dirt>jungle | E | 624 | -2.91 | 7.39 | aabbbaaa | aabbbbaa | 0.88 |
| 0x0781 | dirt | dirt>jungle | E | 2237 | 2.11 | 9.08 | aaabbbaa | aabbbbba | 0.75 |
| 0x0782 | dirt | dirt>jungle | E | 2119 | 18.29 | 1.34 | bbaaaabb | bbbaaabb | 0.88 |
| 0x0783 | dirt | dirt>jungle | E | 641 | 1.35 | 7.15 | aaaabbba | aaabbbbb | 0.75 |
| 0x0784 | dirt | dirt>jungle | E | 557 | 15.91 | 6.08 | bbbaaaaa | bbbaaaab | 0.88 |
| 0x0785 | dirt | dirt>jungle | E | 556 | 16.7 | 6.13 | baaaaabb | bbaaabbb | 0.75 |
| 0x0786 | dirt | jungle>dirt | E | 897 | 11.39 | 7.57 | aaabaaab | babababa | 0.25 |
| 0x0787 | dirt | jungle>dirt | E | 890 | 11.26 | 7.55 | aaabbaab | babbbabb | 0.62 |
| 0x0788 | dirt | dirt>jungle | E | 961 | 12.52 | 7.55 | baabaabb | aaababab | 0.62 |
| 0x0789 | dirt | dirt>jungle | E | 868 | 12.56 | 7.37 | aabbaaaa | bbababbb | 0.25 |
| 0x078A | dirt | dirt>jungle | E | 513 | 19.26 | 9.31 | aaabbbba | bbabbbab | 0.5 |
| 0x078B | dirt | jungle>dirt | E | 2232 | 15.15 | 8.31 | abbbaaaa | aabbaaaa | 0.88 |
| 0x078C | dirt | jungle>dirt | E | 2282 | 9.18 | 8.85 | aaaaabbb | aaaaabbb | 1.0 |
| 0x078D | dirt | jungle>dirt | E | 574 | 4.61 | 6.35 | aaabbbaa | abbaaaba | 0.25 |
| 0x078E | dirt | dirt>jungle | E | 62 | 17.95 | 6.5 | aaabbbba | bbabbbbb | 0.62 |
| 0x078F | dirt | dirt>jungle | E | 87 | 17.31 | 3.53 | bbaaaabb | bbbbaabb | 0.75 |
| 0x0790 | dirt | dirt>jungle | E | 76 | 17.33 | 6.06 | abbbbaaa | bbbbaaab | 0.62 |
| 0x0791 | dirt | dirt>jungle | E | 57 | 19.86 | 3.34 | bbbbaaaa | bbbaabbb | 0.5 |
| 0x098C | embank | dirt>jungle | E | 865 | 18.14 | 4.89 | aaabaaab | bbaaabbb | 0.38 |
| 0x098D | embank | dirt>jungle | E | 846 | 1.97 | 6.4 | aaabaaab | abbbbbaa | 0.38 |
| 0x098E | embank | dirt>jungle | E | 1006 | 2.32 | 5.75 | abaaabaa | aaabbbbb | 0.38 |
| 0x098F | embank | dirt>jungle | E | 793 | 17.82 | 4.86 | abaaabaa | bbbbbabb | 0.12 |
| 0x0990 | embank | dirt>jungle | E | 936 | 1.74 | 6.14 | abaabbba | aaabbbbb | 0.62 |
| 0x0991 | embank | dirt>jungle | E | 816 | 17.89 | 4.83 | abaabbba | bbbbbabb | 0.38 |
| 0x0992 | embank | jungle>dirt | E | 816 | 17.94 | 4.84 | aabbaaab | aaaaaaaa | 0.62 |
| 0x0993 | embank | dirt>jungle | E | 917 | 1.76 | 6.18 | abaabbba | aaabbbba | 0.75 |
| 0x0994 | embank | dirt>jungle | E | 878 | 2.25 | 6.52 | baabaabb | abbbbbaa | 0.12 |
| 0x0995 | embank | dirt>jungle | E | 784 | 18.46 | 4.94 | baabaabb | bbaaaabb | 0.75 |
| 0x0996 | embank | dirt>jungle | E | 774 | 19.02 | 4.95 | aabbbaab | bbaaabbb | 0.12 |
| 0x0997 | embank | dirt>jungle | E | 859 | 2.45 | 6.34 | aabbbaab | abbbbbaa | 0.62 |
| 0x0998 | embank | dirt>jungle | E | 117 | 17.0 | 5.66 | aaabbbba | bbaabbbb | 0.5 |
| 0x099B | embank | jungle>dirt | E | 95 | 16.13 | 4.27 | aabbbaaa | aaaaaaaa | 0.62 |
| 0x099C | embank | dirt>jungle | E | 114 | 16.57 | 5.47 | abbbbaaa | bbbbaaab | 0.62 |
| 0x099F | embank | jungle>dirt | E | 96 | 17.27 | 4.29 | aaaabbba | aaaaaaaa | 0.62 |

### cave <-> cave_wall  (34 ids, 30684 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x024A | cave | cave>cave_wall | E | 409 | 0.91 | 0.95 | aaabbbba | aabbbbba | 0.88 |
| 0x024B | cave | cave_wall>cave | E | 329 | 1.64 | 0.76 | abbbaaaa | abbbabbb | 0.62 |
| 0x024C | cave | cave_wall>cave | E | 291 | 2.05 | 0.84 | aaaaabbb | abbaabbb | 0.75 |
| 0x024D | cave | cave_wall>cave | E | 280 | 0.38 | 0.58 | aaabbbaa | aabbbbba | 0.75 |
| 0x024E | cave | cave>cave_wall | E | 1367 | 1.23 | 1.28 | aaaabbba | aaaabbba | 1.0 |
| 0x024F | cave | cave>cave_wall | E | 1340 | 1.47 | 1.33 | aaaabbaa | aaabbbba | 0.75 |
| 0x0250 | cave | cave>cave_wall | E | 758 | 3.47 | 2.41 | baaaaabb | baaaaabb | 1.0 |
| 0x0251 | cave | cave>cave_wall | E | 692 | 3.68 | 2.33 | baaaaaab | baaaaabb | 0.88 |
| 0x0252 | cave | cave>cave_wall | E | 669 | 3.36 | 2.25 | aaaaaabb | baaaaabb | 0.88 |
| 0x0253 | cave | cave>cave_wall | E | 1256 | 1.19 | 1.33 | aaaaabba | aaabbbba | 0.75 |
| 0x0254 | cave | cave>cave_wall | E | 1173 | 2.49 | 1.52 | aabbbaaa | aabbbaaa | 1.0 |
| 0x0255 | cave | cave>cave_wall | E | 1159 | 2.07 | 1.48 | aabbaaaa | aabbbaaa | 0.88 |
| 0x0256 | cave | cave>cave_wall | E | 1269 | 1.13 | 1.64 | aaabbaaa | aabbbaaa | 0.88 |
| 0x0257 | cave | cave>cave_wall | E | 640 | 1.34 | 1.7 | bbbaaaaa | bbbaaaaa | 1.0 |
| 0x0258 | cave | cave>cave_wall | E | 871 | 0.45 | 2.09 | abbaaaaa | bbbaaaaa | 0.88 |
| 0x0259 | cave | cave>cave_wall | E | 655 | 1.77 | 1.98 | bbbaaaaa | bbbaaaaa | 1.0 |
| 0x025B | cave | cave_wall>cave | E | 788 | 5.6 | 6.58 | babaaaaa | aabbbaaa | 0.62 |
| 0x025C | cave | cave>cave_wall | E | 589 | 2.57 | 4.92 | abaabbba | bbabaaab | 0.25 |
| 0x025D | cave | cave_wall>cave | E | 711 | 7.46 | 6.54 | baaaaaba | aabbbbaa | 0.25 |
| 0x025E | cave | cave_wall>cave | E | 1117 | 9.04 | 5.32 | baaaaaaa | aaaabbba | 0.5 |
| 0x025F | cave | cave_wall>cave | E | 1250 | 8.23 | 5.29 | babaaaaa | aaaabbba | 0.38 |
| 0x0260 | cave | cave>cave_wall | E | 1151 | 7.78 | 4.97 | abaabbba | bbbbaaab | 0.12 |
| 0x0261 | cave | cave_wall>cave | E | 1090 | 9.36 | 4.91 | baaaaaaa | aaaabbba | 0.5 |
| 0x0262 | cave | cave_wall>cave | E | 30 | 0.1 | 2.42 | bbaaaaab | bbaaaaab | 1.0 |
| 0x0267 | cave | cave_wall>cave | E | 735 | 14.48 | 4.61 | baaaaaba | aabbbbaa | 0.25 |
| 0x0268 | cave | cave>cave_wall | E | 521 | 17.63 | 5.33 | aabbbaab | bbaaabba | 0.0 |
| 0x0269 | cave | cave_wall>cave | E | 1064 | 20.08 | 5.92 | baaaaaaa | aabbbbaa | 0.38 |
| 0x026A | cave | cave_wall>cave | E | 150 | 17.12 | 5.51 | baaaaaaa | aaabbaaa | 0.62 |
| 0x026B | cave | cave_wall>cave | E | 156 | 10.61 | 5.96 | baaaaaba | aabbbaaa | 0.38 |
| 0x026C | cave | cave>cave_wall | E | 305 | 3.82 | 4.78 | aabbbaab | bbaaabbb | 0.12 |
| 0x026D | cave | cave_wall>cave | E | 129 | 15.05 | 6.6 | babaaaaa | aabbbaaa | 0.62 |
| 0x02BC | cave | cave_wall>cave | E | 4149 | 13.66 | 2.95 | baaaaaaa | bbaabbba | 0.5 |
| 0x02BE | cave | cave>cave_wall | E | 91 | 14.07 | 4.55 | abbbaaaa | abbabbaa | 0.62 |
| 0x02C0 | cave | cave_wall>cave | E | 3500 | 13.62 | 3.65 | baaaabba | aabbbaab | 0.12 |

### grass <-> rock  (10 ids, 26082 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x0231 | grass | grass>rock | E | 1924 | 9.79 | 1.87 | aaabbbaa | aaabbbaa | 1.0 |
| 0x0232 | grass | grass>rock | E | 1695 | 10.35 | 3.37 | aaaaabbb | aaaaabbb | 1.0 |
| 0x0233 | grass | grass>rock | E | 1727 | 15.28 | 4.86 | bbaaaaab | bbaaaaab | 1.0 |
| 0x0234 | grass | grass>rock | E | 1696 | 10.65 | 3.11 | abbbaaaa | abbbaaaa | 1.0 |
| 0x0235 | rock | rock>grass | E | 1318 | 21.01 | 13.61 | aaaabaaa | aaabbbaa | 0.75 |
| 0x0236 | rock | rock>grass | E | 1134 | 17.22 | 11.64 | aaaaaaba | aaaaabbb | 0.75 |
| 0x0239 | grass | rock>grass | E | 3984 | 11.75 | 6.79 | bbbaaaaa | bbbaaaaa | 1.0 |
| 0x023A | grass | rock>grass | E | 4348 | 15.97 | 8.59 | aabbbaaa | aabbbaaa | 1.0 |
| 0x023B | grass | rock>grass | E | 3742 | 14.9 | 8.57 | aaaabbba | aaaabbba | 1.0 |
| 0x023C | grass | rock>grass | E | 4514 | 10.42 | 6.1 | baaaaabb | baaaaabb | 1.0 |

### dirt <-> rock  (14 ids, 19234 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x00DC | dirt | rock>dirt | E | 2741 | 14.34 | 5.6 | baaaaabb | baaaaabb | 1.0 |
| 0x00DD | dirt | rock>dirt | E | 3061 | 16.14 | 5.6 | bbbaaaaa | bbbaaaaa | 1.0 |
| 0x00DE | dirt | rock>dirt | E | 2527 | 18.52 | 7.13 | aabbbaaa | aabbbaaa | 1.0 |
| 0x00DF | dirt | rock>dirt | E | 3099 | 18.91 | 7.55 | aaaabbba | aaaabbba | 1.0 |
| 0x00E0 | dirt | dirt>rock | E | 1264 | 14.3 | 3.19 | abbbaaaa | abbbaaaa | 1.0 |
| 0x00E1 | dirt | dirt>rock | E | 1325 | 15.61 | 2.11 | aaaabbaa | aaabbbaa | 0.88 |
| 0x00E2 | dirt | dirt>rock | E | 1198 | 17.08 | 3.12 | aaaaabbb | aaaaabbb | 1.0 |
| 0x00E3 | dirt | dirt>rock | E | 1350 | 20.81 | 5.34 | bbaaaaab | bbaaaaab | 1.0 |
| 0x00E4 | rock | rock>dirt | E | 1446 | 21.39 | 9.2 | aaaabaaa | aaaabaaa | 1.0 |
| 0x00E5 | rock | rock>dirt | E | 1116 | 18.44 | 11.04 | aaaaaaba | aaaaabbb | 0.75 |
| 0x0141 | dirt | rock>dirt | T | 23 | 11.09 | 5.65 | aaabbbaa | aaabbbaa | 1.0 |
| 0x0142 | dirt | rock>dirt | T | 36 | -1.11 | 0.51 | bbaaaaab | aabaaaab | 0.62 |
| 0x06ED | rock | rock>dirt | E | 22 | 8.5 | 10.39 | aabbaaaa | aabbbaaa | 0.88 |
| 0x06F1 | rock | rock>dirt | E | 26 | 18.15 | 10.86 | aaabbaaa | aabbbaaa | 0.88 |

### rock <-> sand  (10 ids, 17458 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x011E | sand | sand>rock | T | 39 | 8.05 | 10.63 | bbaaaaab | bbaaaaab | 1.0 |
| 0x0122 | rock | rock>sand | E | 1233 | 19.48 | 15.06 | aaabbbaa | aaabbaaa | 0.88 |
| 0x0123 | rock | rock>sand | E | 1075 | 22.0 | 14.03 | aaaaabbb | aaaaaaba | 0.75 |
| 0x0124 | rock | rock>sand | E | 1146 | 22.39 | 13.64 | bbaaaaab | baaaaaaa | 0.75 |
| 0x0125 | rock | rock>sand | E | 1142 | 19.2 | 14.83 | abbbaaaa | abbbaaaa | 1.0 |
| 0x0126 | sand | sand>rock | E | 2603 | 17.0 | 7.47 | aabbbaaa | abbbbbaa | 0.75 |
| 0x0127 | sand | sand>rock | E | 2895 | 20.81 | 7.9 | aaaabbba | aaabbbbb | 0.75 |
| 0x0128 | sand | sand>rock | E | 2982 | 17.43 | 8.17 | baaaaabb | bbaaabbb | 0.75 |
| 0x0129 | sand | sand>rock | E | 3235 | 20.35 | 8.18 | bbbaaaaa | bbbbaaab | 0.75 |
| 0x07C0 | NoName | sand>rock | T | 1108 | 18.96 | 2.62 | aaaaaaba | aaaaabbb | 0.75 |

### cave <-> dirt  (16 ids, 16243 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x01DC | dirt | dirt>cave | T | 545 | 3.71 | 0.95 | aaaabbba | aaabbbbb | 0.75 |
| 0x01DD | dirt | cave>dirt | T | 425 | -0.28 | 0.99 | abbbbaaa | aabbbaaa | 0.88 |
| 0x01DE | dirt | cave>dirt | T | 506 | 1.12 | 0.7 | baaaabbb | baaaaabb | 0.88 |
| 0x01DF | dirt | dirt>cave | T | 431 | 1.89 | 0.86 | bbbaaaaa | bbbbaaab | 0.75 |
| 0x01E0 | dirt | cave>dirt | T | 1544 | 3.02 | 1.69 | aaaabaaa | aaaabaaa | 1.0 |
| 0x01E1 | dirt | cave>dirt | T | 1633 | 1.98 | 1.51 | baaaaaaa | baaaaaaa | 1.0 |
| 0x01E2 | dirt | cave>dirt | T | 1527 | 2.34 | 1.59 | aabaaaaa | aabaaaaa | 1.0 |
| 0x01E3 | dirt | cave>dirt | T | 1582 | 2.34 | 1.55 | aaaaaaba | aaaaaaba | 1.0 |
| 0x01E4 | dirt | dirt>cave | T | 730 | 4.19 | 1.55 | baaaaaaa | bbaaaaab | 0.75 |
| 0x01E5 | dirt | dirt>cave | T | 769 | 3.32 | 1.65 | aaaabaaa | aaabbbaa | 0.75 |
| 0x01E6 | dirt | dirt>cave | T | 717 | 3.23 | 1.5 | aabaaaaa | abbbaaaa | 0.75 |
| 0x01E7 | dirt | dirt>cave | T | 755 | 2.79 | 1.6 | aaaaaaba | aaaaabbb | 0.75 |
| 0x01EC | dirt | dirt>cave | T | 1427 | 1.27 | 2.01 | aaaabbba | aaabbbbb | 0.75 |
| 0x01ED | dirt | cave>dirt | T | 1202 | -0.01 | 1.97 | baaaabbb | baaaaabb | 0.88 |
| 0x01EE | dirt | dirt>cave | T | 1370 | 3.05 | 2.28 | bbbaaaaa | bbbbaaab | 0.75 |
| 0x01EF | dirt | cave>dirt | T | 1080 | 2.64 | 2.22 | abbbbaaa | aabbbaaa | 0.88 |

### dirt <-> sand  (12 ids, 15860 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x0335 | sand | dirt>sand | T | 2394 | 14.29 | 2.84 | bbbaaaaa | bbbbaaaa | 0.88 |
| 0x0336 | sand | dirt>sand | T | 2027 | 13.07 | 2.92 | baaaaabb | baaaaabb | 1.0 |
| 0x0337 | sand | dirt>sand | T | 1924 | 12.75 | 3.24 | aabbbaaa | aabbbbaa | 0.88 |
| 0x0338 | sand | dirt>sand | T | 2224 | 12.8 | 3.16 | aaaabbba | aaabbbbb | 0.75 |
| 0x0339 | sand | sand>dirt | T | 824 | 13.79 | 3.02 | baaaaaaa | bbaaaaab | 0.75 |
| 0x033A | sand | sand>dirt | T | 932 | 13.54 | 3.04 | aaaabaaa | aaaabaaa | 1.0 |
| 0x033B | sand | sand>dirt | T | 869 | 10.01 | 3.39 | aabaaaaa | aabaaaaa | 1.0 |
| 0x033C | sand | sand>dirt | T | 878 | 11.77 | 3.0 | aaaaaaba | aaaaaabb | 0.88 |
| 0x033D | dirt | dirt>sand | T | 981 | 13.51 | 3.01 | baaaaaaa | bbaaaaab | 0.75 |
| 0x033E | dirt | dirt>sand | T | 910 | 13.84 | 3.18 | aaaabaaa | aaabbbaa | 0.75 |
| 0x033F | dirt | dirt>sand | T | 957 | 11.8 | 3.08 | aabaaaaa | aabbaaaa | 0.88 |
| 0x0340 | dirt | dirt>sand | T | 940 | 10.7 | 3.24 | aaaaaaba | aaaaabbb | 0.75 |

### dirt_dark <-> forest  (9 ids, 11953 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x0161 | forest | forest>dirt_dark | T | 1266 | 1.22 | 0.07 | aaaaaaba | aaaaabbb | 0.75 |
| 0x0162 | forest | forest>dirt_dark | T | 1131 | 1.13 | 0.1 | aabaaaaa | abbbaaaa | 0.75 |
| 0x0165 | forest | forest>dirt_dark | T | 2483 | 0.8 | 0.07 | bbbaaaaa | bbbaaaab | 0.88 |
| 0x0166 | forest | forest>dirt_dark | T | 2356 | 1.48 | 0.1 | baaaaabb | bbaaaabb | 0.88 |
| 0x0167 | forest | forest>dirt_dark | T | 2104 | 1.58 | 0.25 | aabbbaaa | aabbbbaa | 0.88 |
| 0x0168 | forest | forest>dirt_dark | T | 2449 | 1.38 | 0.25 | aaaabbba | aaaabbba | 1.0 |
| 0x054F | forest | forest>dirt_dark | T | 36 | 1.22 | 0.0 | abbaaaaa | bbbbaaaa | 0.75 |
| 0x0550 | forest | forest>dirt_dark | T | 79 | 1.3 | 0.4 | aabbaaaa | abbbbaaa | 0.75 |
| 0x0551 | forest | forest>dirt_dark | T | 49 | 1.41 | 0.23 | aaaaabba | aaaabbba | 0.88 |

### sand <-> stone_floor  (2 ids, 11148 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x0444 | stone | stone_floor>sand | F | 5784 | 6.99 | 0.06 | baaaaabb | bbbbbbbb | 0.38 |
| 0x0445 | stone | sand>stone_floor | F | 5364 | 6.2 | 0.06 | aaabbbaa | aaaaaaaa | 0.62 |

### cobble <-> dirt  (8 ids, 7839 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x03F7 | dirt | cobble>dirt | T | 29 | 2.55 | 0.94 | n/a | bbbbaaaa | None |
| 0x03FE | dirt | cobble>dirt | T | 1918 | 4.81 | 0.19 | n/a | aabbbaaa | None |
| 0x03FF | dirt | cobble>dirt | T | 1877 | 7.9 | 0.22 | n/a | aaaabbba | None |
| 0x0400 | dirt | cobble>dirt | T | 1878 | 4.9 | 0.33 | n/a | baaaaabb | None |
| 0x0402 | dirt | cobble>dirt | T | 682 | 2.8 | 0.2 | n/a | bbbbbaaa | None |
| 0x0403 | dirt | cobble>dirt | T | 633 | 4.38 | 0.15 | n/a | aabbbbba | None |
| 0x0404 | dirt | cobble>dirt | T | 560 | 2.89 | 0.25 | n/a | baaabbbb | None |
| 0x0405 | dirt | dirt>cobble | T | 262 | -7.39 | 0.13 | n/a | aaabbbaa | None |

### forest <-> rock  (6 ids, 5431 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x00ED | forest | rock>forest | E | 1436 | 19.51 | 3.15 | baaaaabb | bbaaabbb | 0.75 |
| 0x00EE | forest | rock>forest | E | 1126 | 22.9 | 3.51 | bbbaaaaa | bbbbaaab | 0.75 |
| 0x00EF | forest | rock>forest | E | 1324 | 29.6 | 5.93 | aabbbaaa | abbbbbaa | 0.75 |
| 0x00F4 | rock | rock>forest | E | 513 | 33.61 | 8.6 | aaaabaaa | aaabbbaa | 0.75 |
| 0x00F5 | rock | rock>forest | E | 619 | 16.65 | 6.6 | aaaaaaba | aaaaabbb | 0.75 |
| 0x00F6 | rock | rock>forest | E | 413 | 22.62 | 4.03 | baaaaaaa | bbaaaaab | 0.75 |

### dirt <-> snow  (12 ids, 4183 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x0385 | snow | dirt>snow | T | 528 | 1.49 | 3.25 | bbbaaaaa | bbbbaaaa | 0.88 |
| 0x0386 | snow | dirt>snow | T | 463 | 3.95 | 2.76 | baaaaabb | bbaaabbb | 0.75 |
| 0x0387 | snow | dirt>snow | T | 379 | 2.22 | 2.48 | aabbbaaa | aabbbbaa | 0.88 |
| 0x0388 | snow | dirt>snow | T | 813 | 3.98 | 2.32 | aaaabbba | aaabbbba | 0.88 |
| 0x0389 | snow | snow>dirt | T | 249 | 4.06 | 2.33 | baaaaaaa | bbaaaaaa | 0.88 |
| 0x038A | snow | snow>dirt | T | 203 | 2.95 | 3.11 | aaaabaaa | aaaabbaa | 0.88 |
| 0x038B | snow | snow>dirt | T | 305 | 5.39 | 2.42 | aabaaaaa | aabbaaaa | 0.88 |
| 0x038C | snow | snow>dirt | T | 181 | 1.47 | 3.05 | aaaaaaba | aaaaabbb | 0.75 |
| 0x038D | dirt | dirt>snow | T | 240 | 1.87 | 2.31 | baaaaaaa | bbaaaaab | 0.75 |
| 0x038E | dirt | dirt>snow | T | 270 | 2.94 | 2.17 | aaaabaaa | aaabbbaa | 0.75 |
| 0x038F | dirt | dirt>snow | T | 229 | 1.89 | 2.22 | aabaaaaa | aabbaaaa | 0.88 |
| 0x0390 | dirt | dirt>snow | T | 323 | 4.9 | 2.13 | aaaaaaba | aaaaabbb | 0.75 |

### furrows <-> grass  (12 ids, 3141 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x000A | furrows | furrows>grass | T | 760 | 11.23 | 0.04 | aabbbaaa | abbbbbaa | 0.75 |
| 0x000B | furrows | furrows>grass | T | 627 | 4.44 | 0.1 | aaaabbba | aaaabbba | 1.0 |
| 0x000C | furrows | furrows>grass | T | 757 | 11.24 | 0.06 | baaaaabb | bbaaaabb | 0.88 |
| 0x000D | furrows | furrows>grass | T | 632 | 5.34 | 0.05 | bbaaaaaa | bbbbaaab | 0.62 |
| 0x000F | furrows | grass>furrows | T | 62 | 14.55 | 0.08 | abbbaaaa | abbbaaaa | 1.0 |
| 0x0010 | furrows | grass>furrows | T | 68 | 15.49 | 0.41 | bbaaaaab | bbaaaaab | 1.0 |
| 0x0011 | furrows | grass>furrows | T | 72 | 16.58 | 0.13 | aaabbbaa | aaabbbaa | 1.0 |
| 0x0012 | furrows | grass>furrows | T | 56 | 12.88 | 0.04 | aaaaabbb | aaaaaaba | 0.75 |
| 0x0151 | furrows | furrows>grass | T | 31 | 0.0 | 0.0 | aaaabbba | bbbbbbbb | 0.38 |
| 0x0152 | furrows | furrows>grass | T | 27 | 0.11 | 0.22 | aabbbaaa | abbbbbaa | 0.75 |
| 0x0153 | furrows | furrows>grass | T | 24 | 0.0 | 0.0 | bbbaaaaa | bbbbbabb | 0.5 |
| 0x0154 | furrows | furrows>grass | T | 25 | 1.56 | 0.1 | baaaaabb | bbaaabbb | 0.75 |

### jungle <-> rock  (5 ids, 2875 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x00EC | jungle | rock>jungle | E | 1284 | 23.38 | 5.9 | aaaabbba | aaaaaaaa | 0.62 |
| 0x00FC | jungle | rock>jungle | E | 404 | 23.94 | 5.33 | aaaabbba | aaabbbba | 0.88 |
| 0x00FD | jungle | rock>jungle | E | 357 | 33.97 | 5.97 | baaaaabb | bbaaaabb | 0.88 |
| 0x00FE | jungle | rock>jungle | E | 477 | 22.88 | 5.42 | bbbaaaaa | bbbaaaab | 0.88 |
| 0x00FF | jungle | rock>jungle | E | 353 | 37.38 | 6.44 | aabbbaaa | aabbbaaa | 1.0 |

### grass <-> sandstone_floor  (16 ids, 2197 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x0456 | sand stone | sandstone_floor>grass | F | 108 | 4.12 | 0.32 | bbbaaaaa | bbbaaaaa | 1.0 |
| 0x0457 | sand stone | sandstone_floor>grass | F | 109 | 5.3 | 0.39 | bbbaaaaa | bbbaaaaa | 1.0 |
| 0x0458 | sand stone | sandstone_floor>grass | F | 125 | 4.04 | 0.35 | bbbaaaaa | bbbaaaaa | 1.0 |
| 0x0459 | sand stone | sandstone_floor>grass | F | 110 | 3.3 | 0.52 | bbbaaaaa | bbbaaaab | 0.88 |
| 0x045A | sand stone | sandstone_floor>grass | F | 151 | 3.93 | 0.14 | aaaabbba | aaaabbba | 1.0 |
| 0x045B | sand stone | sandstone_floor>grass | F | 168 | 3.3 | 0.16 | aaaabbba | aaaabbba | 1.0 |
| 0x045C | sand stone | sandstone_floor>grass | F | 152 | 3.3 | 0.22 | aaaabbba | aaaabbba | 1.0 |
| 0x045D | sand stone | sandstone_floor>grass | F | 140 | 3.36 | 0.31 | aaaabbba | aaabbbba | 0.88 |
| 0x045E | sand stone | sandstone_floor>grass | F | 120 | 5.42 | 0.68 | baaaaabb | baaaaabb | 1.0 |
| 0x045F | sand stone | sandstone_floor>grass | F | 115 | 6.12 | 0.52 | baaaaabb | baaaaabb | 1.0 |
| 0x0460 | sand stone | sandstone_floor>grass | F | 166 | 5.73 | 0.66 | baaaaabb | baaaaabb | 1.0 |
| 0x0461 | sand stone | sandstone_floor>grass | F | 134 | 6.19 | 0.46 | baaaaabb | baaaaabb | 1.0 |
| 0x0462 | sand stone | sandstone_floor>grass | F | 149 | 5.84 | 0.23 | aabbbaaa | aabbbaaa | 1.0 |
| 0x0463 | sand stone | sandstone_floor>grass | F | 151 | 7.92 | 0.21 | aabbbaaa | aabbbaaa | 1.0 |
| 0x0464 | sand stone | sandstone_floor>grass | F | 155 | 6.58 | 0.3 | aabbbaaa | aabbbaaa | 1.0 |
| 0x0465 | sand stone | sandstone_floor>grass | F | 144 | 6.19 | 0.25 | aabbbaaa | aabbbaaa | 1.0 |

### leaves <-> tree  (12 ids, 2171 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x2E76 | tree | tree>leaves | E | 54 | 0.0 | 0.0 | aaabbbaa | bbbbbbbb | 0.38 |
| 0x2E82 | tree | tree>leaves | E | 59 | 0.0 | 0.0 | aaabbbaa | bbbbbbbb | 0.38 |
| 0x2E9A | tree | tree>leaves | E | 46 | 0.0 | 0.0 | baaaaaab | bbbbabbb | 0.38 |
| 0x2E9C | tree | leaves>tree | E | 57 | 0.0 | 0.0 | aaaabaaa | aaaaaaaa | 0.88 |
| 0x2E9F | tree | tree>leaves | E | 118 | 0.0 | 0.0 | baaabbba | ababbbbb | 0.5 |
| 0x2EA7 | tree | tree>leaves | E | 1294 | 0.0 | 0.0 | aabaaaaa | bbbbbbbb | 0.12 |
| 0x2EBB | tree | tree>leaves | E | 66 | 0.0 | 0.0 | abbbbaaa | bbbbbbab | 0.62 |
| 0x2EC0 | tree | tree>leaves | E | 109 | 0.0 | 0.0 | aabbaaaa | bbbbbbab | 0.38 |
| 0x2EC5 | tree | tree>leaves | E | 26 | 0.0 | 0.0 | abbbaaaa | bbbbbbab | 0.5 |
| 0x2ED7 | tree | leaves>tree | E | 150 | 0.0 | 0.0 | aabaaaaa | aaaaaaaa | 0.88 |
| 0x2ED8 | tree | tree>leaves | E | 162 | 0.0 | 0.0 | aaaaabbb | bbabbbbb | 0.5 |
| 0x2EEE | tree | tree>leaves | E | 30 | 0.0 | 0.0 | baaaaaaa | bbbbbbbb | 0.12 |

### obsidian <-> rock  (1 ids, 1668 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x3FCC | Obsidian | obsidian>rock | E | 1668 | 39.79 | 9.89 | abaaaaaa | aaaabbba | 0.5 |

### planks <-> sand  (14 ids, 1494 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x029C | planks | planks>sand | F | 198 | 0.91 | 0.0 | aabbbaaa | aabbbbaa | 0.88 |
| 0x029D | planks | planks>sand | F | 196 | 1.05 | 0.01 | aabbbaaa | abbbbaaa | 0.88 |
| 0x029E | planks | planks>sand | F | 163 | 1.47 | 0.02 | baaaaabb | bbaaaabb | 0.88 |
| 0x029F | planks | planks>sand | F | 143 | 0.87 | 0.02 | baaaaabb | baaaabbb | 0.88 |
| 0x02A2 | planks | sand>planks | F | 22 | 3.18 | 0.06 | aaaaabbb | aaaaabbb | 1.0 |
| 0x02A6 | planks | planks>sand | F | 25 | 1.6 | 0.0 | aaaaaaba | aaaaaaba | 1.0 |
| 0x02A7 | planks | planks>sand | F | 20 | 0.25 | 0.06 | baaaaaaa | baaaaaaa | 1.0 |
| 0x02AD | planks | planks>sand | F | 189 | 0.37 | 0.0 | aaaabbba | aaaabbba | 1.0 |
| 0x02AE | planks | planks>sand | F | 168 | 0.36 | 0.0 | aaaabbba | aaaabbba | 1.0 |
| 0x02AF | planks | planks>sand | F | 161 | 0.43 | 0.0 | bbbaaaaa | bbbaaaaa | 1.0 |
| 0x02B0 | planks | planks>sand | F | 141 | 0.46 | 0.0 | bbbaaaaa | bbbaaaaa | 1.0 |
| 0x02B7 | planks | planks>sand | F | 24 | 0.42 | 0.0 | aabaaaaa | aabaaaaa | 1.0 |
| 0x02B8 | planks | planks>sand | F | 23 | 0.65 | 0.05 | aaaabaaa | baaabaaa | 0.88 |
| 0x02BA | planks | planks>sand | F | 21 | 0.48 | 0.06 | aaaaaaba | aaaaaaba | 1.0 |

### seafloor <-> snow  (1 ids, 916 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x010C | snow | snow>seafloor | E | 916 | 15.66 | 4.03 | aaaabaaa | aaabbbaa | 0.75 |

### dirt_dark <-> grass  (6 ids, 733 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x036F | grass | grass>dirt_dark | T | 124 | 3.5 | 0.12 | abbaaaaa | abbaaaaa | 1.0 |
| 0x0370 | grass | grass>dirt_dark | T | 112 | 3.02 | 0.21 | aaaaaabb | baaaaabb | 0.88 |
| 0x0371 | grass | grass>dirt_dark | T | 121 | 2.78 | 0.18 | aabbaaaa | aabbbaaa | 0.88 |
| 0x0372 | grass | grass>dirt_dark | T | 100 | 4.58 | 0.32 | aaaaabba | aaaabbba | 0.88 |
| 0x0374 | grass | grass>dirt_dark | T | 139 | 3.53 | 0.17 | baaaaaab | baaaaabb | 0.88 |
| 0x0375 | grass | grass>dirt_dark | T | 137 | 5.64 | 0.28 | aaabbaaa | aabbbaaa | 0.88 |

### black <-> rock  (7 ids, 396 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x01D3 | rock | rock>black | E | 61 | 26.18 | 6.64 | aaaabaaa | aaabbbaa | 0.75 |
| 0x01D4 | rock | black>rock | E | 110 | 26.34 | 6.12 | bbbaaaaa | bbbaaaab | 0.88 |
| 0x01D5 | rock | rock>black | E | 32 | 28.06 | 6.56 | aaaaaaba | aaaaaaba | 1.0 |
| 0x01D6 | rock | black>rock | E | 35 | 22.94 | 7.44 | aabbbaaa | aabbbaaa | 1.0 |
| 0x01D8 | rock | black>rock | E | 37 | 24.05 | 6.69 | aaaabbba | aaaabbba | 1.0 |
| 0x01D9 | rock | rock>black | E | 32 | 30.56 | 5.76 | aabaaaaa | aabbaaaa | 0.88 |
| 0x01DA | rock | black>rock | E | 89 | 26.66 | 6.08 | baaaaabb | bbaaaabb | 0.88 |

### jungle <-> sand  (6 ids, 224 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x0282 | sand | sand>jungle | T | 22 | 20.09 | 1.57 | aaaabbba | aaaabbba | 1.0 |
| 0x0283 | sand | sand>jungle | T | 87 | 27.82 | 0.0 | aabbbaaa | aabbbaaa | 1.0 |
| 0x0284 | sand | sand>jungle | T | 29 | 45.45 | 0.68 | bbbaaaaa | bbbaaaaa | 1.0 |
| 0x0285 | sand | sand>jungle | T | 31 | 30.16 | 1.03 | baaaaabb | baaaaabb | 1.0 |
| 0x0289 | jungle | jungle>sand | T | 24 | 35.83 | 0.02 | aaaaaaba | aaaaaaba | 1.0 |
| 0x028C | sand | sand>jungle | T | 31 | 33.55 | 0.06 | aabaaaaa | aabaaaaa | 1.0 |

### obsidian <-> void  (1 ids, 140 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x2745 | TerrainFallback | obsidian>void | T | 140 | -2.23 | 21.28 | abbbaaaa | bbbbaaaa | 0.88 |

### stone_floor <-> wood_floor  (1 ids, 130 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x0410 | wooden floor | stone_floor>wood_floor | F | 130 | 15.0 | 0.0 | baaaaaaa | aabbaaaa | 0.62 |

### dirt <-> dirt_dark  (2 ids, 89 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x0555 | dirt | dirt>dirt_dark | T | 38 | 2.05 | 0.23 | n/a | baaabbba | None |
| 0x0556 | dirt | dirt>dirt_dark | T | 51 | 1.49 | 0.38 | n/a | bbbbbaaa | None |

### dirt <-> swamp  (2 ids, 43 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x3DFB | NoName | swamp>dirt | T | 21 | -15.0 | 0.06 | baaaaabb | bbaaaabb | 0.88 |
| 0x3DFD | NoName | swamp>dirt | T | 22 | -15.0 | 0.0 | aaaabbba | aaaabbba | 1.0 |

### rock <-> seafloor  (1 ids, 30 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x07D3 | NoName | rock>seafloor | E | 30 | 15.47 | 11.12 | aabaaaaa | bbaaaabb | 0.38 |

### rock <-> sandstone_floor  (1 ids, 23 tiles)

| id | name | material | role | count | mean z | |dz| | sectors8 N,NE,E,SE,S,SW,W,NW (b=B) | nbr B-mask | ag |
|---|---|---|---|---|---|---|---|---|---|
| 0x044E | sand stone | sandstone_floor>rock | F | 23 | 32.57 | 0.86 | aaabaaaa | baaababb | 0.38 |

## Impassable land ids that are NOT rock/cave-wall/lava/void/water (where Britannia uses them)

| id | name | material | role | count | mean z | |dz| | water-static frac | context |
|---|---|---|---|---|---|---|---|---|
| 0x001A | sand | wetsand | pure | 9332 | -12.99 | 5.86 | 0.927 | seafloor:0.52 wetsand:0.26 grass:0.16 |
| 0x001B | sand | wetsand | pure | 7886 | -12.78 | 5.82 | 0.913 | seafloor:0.57 wetsand:0.21 grass:0.14 |
| 0x001C | sand | wetsand | pure | 15396 | -6.71 | 4.88 | 0.49 | seafloor:0.58 wetsand:0.21 grass:0.15 |
| 0x001D | sand | sand>grass | edge | 7153 | 2.04 | 2.52 | 0.004 | grass:0.51 wetsand:0.25 seafloor:0.17 |
| 0x001E | sand | grass>sand | edge | 6447 | -1.11 | 7.08 | 0.649 | grass:0.53 wetsand:0.25 seafloor:0.17 |
| 0x001F | sand | sand>grass | edge | 6274 | -0.66 | 6.93 | 0.602 | grass:0.55 wetsand:0.25 seafloor:0.17 |
| 0x0020 | sand | sand>grass | edge | 6065 | -14.62 | 6.53 | 0.982 | grass:0.51 wetsand:0.25 seafloor:0.17 |
| 0x0021 | sand | sand>grass | edge | 7195 | 0.63 | 6.15 | 0.189 | seafloor:0.42 grass:0.39 wetsand:0.13 |
| 0x0022 | sand | sand>grass | edge | 8904 | -13.94 | 4.43 | 0.957 | seafloor:0.43 grass:0.39 wetsand:0.12 |
| 0x0023 | sand | sand>grass | edge | 9283 | 1.03 | 6.11 | 0.173 | seafloor:0.43 grass:0.39 wetsand:0.13 |
| 0x0024 | sand | sand | edge | 6687 | -13.79 | 4.46 | 0.949 | seafloor:0.43 grass:0.39 wetsand:0.12 |
| 0x0025 | sand | sand>grass | edge | 2294 | 1.04 | 6.03 | 0.17 | seafloor:0.42 grass:0.39 wetsand:0.13 |
| 0x0026 | sand | sand>grass | edge | 3126 | -13.53 | 4.63 | 0.936 | seafloor:0.43 grass:0.39 wetsand:0.12 |
| 0x0027 | sand | sand>grass | edge | 2876 | 0.87 | 6.1 | 0.154 | seafloor:0.43 grass:0.39 wetsand:0.12 |
| 0x0028 | sand | sand>grass | edge | 2026 | -13.44 | 4.36 | 0.947 | seafloor:0.43 grass:0.39 wetsand:0.12 |
| 0x002A | sand | sand>grass | edge | 30 | 22.43 | 2.76 | 0.0 | grass:0.70 jungle:0.30 |
| 0x002D | sand | grass>sand | edge | 31 | 20.81 | 2.36 | 0.032 | grass:0.71 jungle:0.26 |
| 0x0030 | sand | grass>sand | edge | 39 | 15.46 | 3.62 | 0.154 | grass:0.76 jungle:0.12 seafloor:0.07 |
| 0x0032 | sand | grass>sand | edge | 134 | 23.45 | 2.63 | 0.022 | grass:0.82 jungle:0.17 |
| 0x0049 | sand | grass>sand | edge | 107 | 12.2 | 8.96 | 0.178 | grass:0.62 wetsand:0.16 sand:0.10 |
| 0x004B | sand | grass>sand | edge | 99 | 10.15 | 7.98 | 0.0 | grass:0.64 wetsand:0.20 sand:0.15 |
| 0x008D | dirt | dirt | edge | 2265 | -0.16 | 6.63 | 0.366 | seafloor:0.48 dirt:0.24 grass:0.08 |
| 0x008E | dirt | dirt | edge | 1215 | 7.74 | 5.72 | 0.09 | grass:0.49 seafloor:0.40 dirt:0.04 |
| 0x008F | dirt | dirt | edge | 1624 | -11.75 | 5.13 | 0.795 | seafloor:0.44 grass:0.35 dirt:0.06 |
| 0x0090 | dirt | dirt>grass | edge | 1628 | 22.42 | 5.49 | 0.007 | grass:0.74 forest:0.20 jungle:0.04 |
| 0x0091 | dirt | dirt | edge | 2699 | 0.96 | 6.41 | 0.301 | seafloor:0.43 dirt:0.24 grass:0.09 |
| 0x0092 | dirt | dirt>grass | edge | 1884 | -11.31 | 4.95 | 0.792 | seafloor:0.44 grass:0.36 dirt:0.07 |
| 0x0093 | dirt | dirt>grass | edge | 1528 | 7.83 | 6.04 | 0.055 | grass:0.47 seafloor:0.35 dirt:0.06 |
| 0x0094 | dirt | dirt>grass | edge | 1634 | 24.05 | 5.82 | 0.001 | grass:0.78 forest:0.17 jungle:0.03 |
| 0x0095 | dirt | dirt | edge | 3004 | 1.95 | 5.26 | 0.343 | seafloor:0.61 grass:0.15 dirt:0.10 |
| 0x0096 | dirt | dirt>grass | edge | 278 | -4.26 | 8.67 | 0.468 | grass:0.48 seafloor:0.29 forest:0.12 |
| 0x0097 | dirt | dirt>grass | edge | 482 | 17.76 | 8.18 | 0.048 | grass:0.89 forest:0.05 jungle:0.02 |
| 0x0098 | dirt | dirt>grass | edge | 852 | 6.31 | 2.33 | 0.38 | grass:0.64 seafloor:0.21 dirt:0.04 |
| 0x0099 | dirt | dirt>grass | edge | 696 | -10.07 | 5.66 | 0.727 | seafloor:0.42 grass:0.39 dirt:0.09 |
| 0x009A | dirt | dirt>grass | edge | 609 | 8.45 | 5.29 | 0.057 | grass:0.50 seafloor:0.32 dirt:0.06 |
| 0x009B | dirt | dirt>grass | edge | 479 | 6.75 | 5.54 | 0.065 | grass:0.49 seafloor:0.39 dirt:0.05 |
| 0x009C | dirt | dirt>grass | edge | 935 | 15.5 | 4.54 | 0.003 | grass:0.74 forest:0.21 jungle:0.03 |
| 0x009D | dirt | dirt>grass | edge | 992 | 15.52 | 4.39 | 0.002 | grass:0.73 forest:0.22 |
| 0x009E | dirt | dirt>grass | edge | 1388 | 15.43 | 4.33 | 0.004 | grass:0.69 forest:0.27 jungle:0.03 |
| 0x009F | dirt | dirt>grass | edge | 869 | 14.33 | 5.17 | 0.008 | grass:0.75 forest:0.17 jungle:0.06 |
| 0x00A0 | dirt | dirt>grass | edge | 4491 | 13.45 | 7.08 | 0.193 | grass:0.64 forest:0.18 jungle:0.10 |
| 0x00A1 | dirt | dirt>grass | edge | 3668 | 6.75 | 6.04 | 0.055 | grass:0.71 forest:0.20 jungle:0.06 |
| 0x00A2 | dirt | grass>dirt | edge | 3687 | 6.85 | 7.7 | 0.046 | grass:0.70 forest:0.20 jungle:0.05 |
| 0x00A3 | dirt | dirt>grass | edge | 4450 | 6.79 | 2.68 | 0.012 | grass:0.66 forest:0.19 jungle:0.10 |
| 0x00A4 | dirt | dirt>grass | edge | 80 | 23.73 | 5.21 | 0.05 | grass:0.87 forest:0.05 jungle:0.04 |
| 0x00A5 | dirt | dirt>grass | edge | 98 | 20.52 | 4.15 | 0.0 | grass:0.83 forest:0.15 |
| 0x00A6 | dirt | dirt>grass | edge | 92 | 25.86 | 3.98 | 0.0 | grass:0.79 jungle:0.10 forest:0.08 |
| 0x00A7 | dirt | dirt>grass | edge | 92 | 26.33 | 3.26 | 0.0 | grass:0.84 jungle:0.07 forest:0.07 |
| 0x010D | snow | snow | edge | 629 | 21.78 | 4.24 | 0.008 | snow:0.77 rock:0.21 |
| 0x010E | snow | snow | edge | 545 | 22.52 | 4.18 | 0.002 | snow:0.76 rock:0.23 |
| 0x010F | snow | snow | edge | 527 | 20.16 | 4.23 | 0.002 | snow:0.79 rock:0.20 |
| 0x0114 | snow | snow | edge | 3086 | 19.7 | 5.28 | 0.004 | snow:0.56 rock:0.42 |
| 0x0115 | snow | snow | edge | 1977 | 21.05 | 6.16 | 0.001 | snow:0.55 rock:0.44 |
| 0x0116 | snow | snow | edge | 3241 | 21.98 | 6.01 | 0.001 | snow:0.54 rock:0.46 |
| 0x0117 | snow | snow | edge | 1819 | 19.44 | 5.35 | 0.003 | snow:0.56 rock:0.42 |
| 0x017C | snow | snow | edge | 98 | 1.41 | 4.38 | 0.01 | snow:0.69 seafloor:0.31 |
| 0x017D | snow | snow | edge | 249 | -1.92 | 6.85 | 0.618 | snow:0.78 seafloor:0.22 |
| 0x017E | snow | snow | edge | 199 | -2.16 | 5.99 | 0.432 | snow:0.77 seafloor:0.21 |
| 0x017F | snow | snow | edge | 125 | -13.83 | 6.3 | 0.96 | snow:0.76 seafloor:0.22 |
| 0x0180 | snow | snow | edge | 143 | -1.25 | 6.25 | 0.308 | seafloor:0.50 snow:0.50 |
| 0x0181 | snow | snow | edge | 215 | -14.73 | 4.33 | 0.986 | snow:0.50 seafloor:0.50 |
| 0x0182 | snow | snow | edge | 307 | -0.83 | 6.28 | 0.248 | snow:0.50 seafloor:0.49 |
| 0x0183 | snow | snow | edge | 44 | -0.7 | 6.31 | 0.205 | snow:0.52 seafloor:0.48 |
| 0x0184 | snow | snow | edge | 159 | -13.36 | 4.21 | 0.969 | seafloor:0.49 snow:0.40 water:0.12 |
| 0x0185 | snow | snow | edge | 171 | -6.55 | 5.51 | 0.561 | snow:0.50 seafloor:0.49 |
| 0x0188 | snow | snow | edge | 89 | 22.09 | 8.86 | 0.112 | snow:0.83 seafloor:0.16 |
| 0x0189 | snow | snow | edge | 167 | 20.08 | 7.4 | 0.054 | snow:0.86 seafloor:0.10 rock:0.03 |
| 0x018A | snow | snow | edge | 83 | 22.48 | 7.49 | 0.0 | snow:0.92 seafloor:0.08 |
| 0x01BA | sand | sand | edge | 47 | 2.43 | 7.14 | 0.426 | seafloor:0.41 wetsand:0.20 grass:0.17 |
| 0x01BB | sand | sand | edge | 115 | 0.29 | 7.41 | 0.017 | seafloor:0.52 sand:0.25 wetsand:0.21 |
| 0x01BC | sand | sand | edge | 66 | 7.02 | 1.73 | 0.045 | sand:0.67 wetsand:0.18 seafloor:0.15 |
| 0x01BE | sand | sand | edge | 32 | 4.25 | 8.52 | 0.719 | sand:0.55 wetsand:0.34 seafloor:0.07 |
| 0x01C0 | sand | sand | edge | 37 | 2.54 | 6.61 | 0.486 | seafloor:0.37 sand:0.21 wetsand:0.15 |
| 0x01C2 | sand | sand | edge | 54 | 17.67 | 9.62 | 0.093 | sand:0.47 seafloor:0.28 wetsand:0.26 |
| 0x01C3 | sand | sand | edge | 48 | -2.9 | 7.79 | 0.667 | seafloor:0.45 sand:0.19 grass:0.15 |
| 0x01C6 | sand | sand | edge | 22 | 10.14 | 7.74 | 0.227 | sand:0.57 seafloor:0.32 wetsand:0.07 |
| 0x01CA | sand | sand | edge | 20 | 25.8 | 8.91 | 0.15 | sand:0.88 seafloor:0.11 |
| 0x02E5 | dirt | dirt | edge | 652 | 6.96 | 9.08 | 0.075 | dirt:0.57 forest:0.33 seafloor:0.06 |
| 0x02E6 | dirt | dirt | edge | 834 | 24.34 | 7.59 | 0.06 | forest:0.56 dirt:0.31 seafloor:0.11 |
| 0x02E7 | dirt | dirt>forest | edge | 634 | 5.17 | 6.65 | 0.068 | forest:0.56 dirt:0.36 grass:0.05 |
| 0x02E8 | dirt | dirt>forest | edge | 1317 | 23.13 | 8.67 | 0.016 | forest:0.86 rock:0.10 grass:0.02 |
| 0x02E9 | dirt | dirt | edge | 539 | 7.71 | 7.74 | 0.052 | dirt:0.56 forest:0.36 grass:0.03 |
| 0x02EA | dirt | dirt>forest | edge | 840 | 3.06 | 7.57 | 0.057 | forest:0.56 dirt:0.38 grass:0.04 |
| 0x02EB | dirt | dirt>forest | edge | 790 | 21.02 | 6.35 | 0.038 | forest:0.55 dirt:0.34 seafloor:0.07 |
| 0x02EC | dirt | dirt>forest | edge | 1453 | 21.71 | 8.39 | 0.012 | forest:0.86 rock:0.10 grass:0.02 |
| 0x02ED | dirt | dirt | edge | 1088 | 14.94 | 7.08 | 0.019 | dirt:0.54 forest:0.38 grass:0.05 |
| 0x02EE | dirt | dirt>forest | edge | 320 | 2.21 | 6.6 | 0.084 | forest:0.56 dirt:0.37 grass:0.05 |
| 0x02EF | dirt | dirt>forest | edge | 2745 | 11.27 | 9.99 | 0.009 | forest:0.86 grass:0.10 |
| 0x02F0 | dirt | dirt>forest | edge | 2638 | 25.0 | 1.55 | 0.003 | forest:0.86 grass:0.09 dirt:0.03 |
| 0x02F1 | dirt | dirt>forest | edge | 386 | 2.91 | 7.53 | 0.026 | forest:0.54 dirt:0.40 grass:0.03 |
| 0x02F2 | dirt | dirt>forest | edge | 358 | 22.69 | 6.61 | 0.003 | forest:0.56 dirt:0.40 seafloor:0.03 |
| 0x02F3 | dirt | dirt>forest | edge | 308 | 24.37 | 7.12 | 0.036 | forest:0.55 dirt:0.39 seafloor:0.05 |
| 0x02F4 | dirt | forest>dirt | edge | 1451 | 22.47 | 8.45 | 0.015 | forest:0.85 rock:0.11 |
| 0x02F5 | dirt | dirt>forest | edge | 1482 | 22.36 | 8.3 | 0.015 | forest:0.86 rock:0.09 |
| 0x02F6 | dirt | dirt>forest | edge | 1356 | 22.75 | 8.52 | 0.013 | forest:0.87 rock:0.10 |
| 0x02F7 | dirt | dirt>forest | edge | 1339 | 23.49 | 8.6 | 0.012 | forest:0.86 rock:0.10 grass:0.02 |
| 0x02F8 | dirt | forest>dirt | edge | 728 | 28.35 | 10.34 | 0.018 | forest:0.75 rock:0.21 |
| 0x02F9 | dirt | dirt>forest | edge | 2767 | 22.72 | 10.23 | 0.02 | forest:0.84 grass:0.08 rock:0.04 |
| 0x02FA | dirt | forest>dirt | edge | 2695 | 16.68 | 10.45 | 0.022 | forest:0.84 grass:0.08 rock:0.04 |
| 0x02FB | dirt | forest>dirt | edge | 739 | 17.62 | 8.28 | 0.015 | forest:0.79 rock:0.14 jungle:0.04 |
| 0x02FC | dirt | dirt>forest | edge | 137 | 33.36 | 6.63 | 0.007 | forest:0.94 grass:0.03 |
| 0x02FD | dirt | dirt>forest | edge | 191 | 33.58 | 4.52 | 0.0 | forest:0.92 grass:0.05 |
| 0x02FE | dirt | dirt>forest | edge | 143 | 34.71 | 6.95 | 0.0 | forest:0.96 grass:0.02 |
| 0x02FF | dirt | dirt>forest | edge | 166 | 31.6 | 4.22 | 0.006 | forest:0.94 grass:0.05 |
| 0x0303 | dirt | dirt | edge | 172 | 54.55 | 15.34 | 0.0 | furrows:0.56 swamp:0.29 black:0.10 |
| 0x0304 | dirt | dirt | edge | 77 | 45.17 | 7.4 | 0.0 | swamp:0.18 rock:0.18 furrows:0.17 |
| 0x0305 | dirt | dirt | edge | 47 | 13.64 | 15.27 | 0.0 | forest:0.33 furrows:0.25 grass:0.12 |
| 0x06FB | rock | cave | edge | 150 | 1.01 | 8.99 | 0.0 | rock:0.73 cave:0.23 |
| 0x076D | snow | snow | edge | 156 | 31.46 | 10.07 | 0.019 | snow:0.89 seafloor:0.10 |
| 0x0770 | snow | snow | edge | 64 | 30.16 | 3.41 | 0.0 | snow:0.92 seafloor:0.07 |
| 0x0771 | snow | snow | edge | 46 | 31.52 | 15.58 | 0.022 | snow:0.79 seafloor:0.17 rock:0.03 |
| 0x0772 | snow | snow | edge | 195 | 26.43 | 10.3 | 0.051 | snow:0.89 seafloor:0.11 |
| 0x0773 | snow | snow | edge | 152 | 27.39 | 8.33 | 0.0 | snow:0.94 seafloor:0.03 rock:0.03 |
| 0x0777 | dirt | dirt | edge | 783 | 1.77 | 9.14 | 0.011 | dirt:0.58 jungle:0.23 grass:0.10 |
| 0x0778 | dirt | dirt | edge | 1104 | 15.56 | 6.2 | 0.009 | jungle:0.51 dirt:0.38 rock:0.05 |
| 0x0779 | dirt | dirt>jungle | edge | 1263 | -1.94 | 7.48 | 0.027 | jungle:0.51 dirt:0.36 grass:0.08 |
| 0x077A | dirt | dirt>jungle | edge | 927 | 13.14 | 7.32 | 0.01 | jungle:0.65 rock:0.20 swamp:0.10 |
| 0x077B | dirt | dirt | edge | 740 | 5.71 | 7.64 | 0.008 | dirt:0.58 jungle:0.23 grass:0.09 |
| 0x077C | dirt | dirt | edge | 1345 | 0.77 | 6.97 | 0.019 | jungle:0.52 dirt:0.30 grass:0.09 |
| 0x077D | dirt | dirt>jungle | edge | 1344 | 15.52 | 6.08 | 0.009 | jungle:0.51 dirt:0.39 rock:0.05 |
| 0x077E | dirt | dirt>jungle | edge | 924 | 11.76 | 7.41 | 0.012 | jungle:0.68 rock:0.14 swamp:0.12 |
| 0x077F | dirt | dirt | edge | 1813 | 7.48 | 6.25 | 0.002 | dirt:0.49 jungle:0.35 grass:0.09 |
| 0x0780 | dirt | dirt>jungle | edge | 624 | -2.91 | 7.39 | 0.053 | jungle:0.52 dirt:0.35 grass:0.08 |
| 0x0781 | dirt | dirt>jungle | edge | 2237 | 2.11 | 9.08 | 0.006 | jungle:0.83 grass:0.10 dirt:0.04 |
| 0x0782 | dirt | dirt>jungle | edge | 2119 | 18.29 | 1.34 | 0.003 | jungle:0.83 grass:0.10 dirt:0.05 |
| 0x0783 | dirt | dirt>jungle | edge | 641 | 1.35 | 7.15 | 0.005 | jungle:0.52 dirt:0.31 grass:0.09 |
| 0x0784 | dirt | dirt>jungle | edge | 557 | 15.91 | 6.08 | 0.007 | jungle:0.50 dirt:0.38 rock:0.06 |
| 0x0785 | dirt | dirt>jungle | edge | 556 | 16.7 | 6.13 | 0.005 | jungle:0.51 dirt:0.35 grass:0.06 |
| 0x0786 | dirt | jungle>dirt | edge | 897 | 11.39 | 7.57 | 0.008 | jungle:0.67 rock:0.16 swamp:0.11 |
| 0x0787 | dirt | jungle>dirt | edge | 890 | 11.26 | 7.55 | 0.009 | jungle:0.67 rock:0.15 swamp:0.12 |
| 0x0788 | dirt | dirt>jungle | edge | 961 | 12.52 | 7.55 | 0.01 | jungle:0.67 rock:0.17 swamp:0.11 |
| 0x0789 | dirt | dirt>jungle | edge | 868 | 12.56 | 7.37 | 0.008 | jungle:0.67 rock:0.18 swamp:0.10 |
| 0x078A | dirt | dirt>jungle | edge | 513 | 19.26 | 9.31 | 0.006 | jungle:0.53 swamp:0.24 rock:0.20 |
| 0x078B | dirt | jungle>dirt | edge | 2232 | 15.15 | 8.31 | 0.006 | jungle:0.74 grass:0.09 swamp:0.06 |
| 0x078C | dirt | jungle>dirt | edge | 2282 | 9.18 | 8.85 | 0.013 | jungle:0.72 grass:0.09 rock:0.07 |
| 0x078D | dirt | jungle>dirt | edge | 574 | 4.61 | 6.35 | 0.003 | jungle:0.51 rock:0.23 swamp:0.21 |
| 0x078E | dirt | dirt>jungle | edge | 62 | 17.95 | 6.5 | 0.0 | jungle:0.77 swamp:0.13 grass:0.07 |
| 0x078F | dirt | dirt>jungle | edge | 87 | 17.31 | 3.53 | 0.0 | jungle:0.83 grass:0.09 swamp:0.06 |
| 0x0790 | dirt | dirt>jungle | edge | 76 | 17.33 | 6.06 | 0.0 | jungle:0.78 swamp:0.12 grass:0.07 |
| 0x0791 | dirt | dirt>jungle | edge | 57 | 19.86 | 3.34 | 0.0 | jungle:0.82 swamp:0.10 grass:0.06 |
| 0x098C | embank | dirt>jungle | edge | 865 | 18.14 | 4.89 | 0.001 | jungle:0.50 grass:0.47 cave_wall:0.03 |
| 0x098D | embank | dirt>jungle | edge | 846 | 1.97 | 6.4 | 0.002 | jungle:0.51 grass:0.49 |
| 0x098E | embank | dirt>jungle | edge | 1006 | 2.32 | 5.75 | 0.002 | jungle:0.48 grass:0.46 cave:0.03 |
| 0x098F | embank | dirt>jungle | edge | 793 | 17.82 | 4.86 | 0.0 | jungle:0.52 grass:0.48 |
| 0x0990 | embank | dirt>jungle | edge | 936 | 1.74 | 6.14 | 0.004 | jungle:0.51 grass:0.48 |
| 0x0991 | embank | dirt>jungle | edge | 816 | 17.89 | 4.83 | 0.004 | jungle:0.52 grass:0.48 |
| 0x0992 | embank | jungle>dirt | edge | 816 | 17.94 | 4.84 | 0.004 | jungle:0.52 grass:0.48 |
| 0x0993 | embank | dirt>jungle | edge | 917 | 1.76 | 6.18 | 0.003 | jungle:0.51 grass:0.48 |
| 0x0994 | embank | dirt>jungle | edge | 878 | 2.25 | 6.52 | 0.003 | jungle:0.52 grass:0.48 |
| 0x0995 | embank | dirt>jungle | edge | 784 | 18.46 | 4.94 | 0.001 | jungle:0.52 grass:0.48 |
| 0x0996 | embank | dirt>jungle | edge | 774 | 19.02 | 4.95 | 0.003 | jungle:0.51 grass:0.48 |
| 0x0997 | embank | dirt>jungle | edge | 859 | 2.45 | 6.34 | 0.0 | jungle:0.52 grass:0.48 |
| 0x0998 | embank | dirt>jungle | edge | 117 | 17.0 | 5.66 | 0.0 | jungle:0.52 grass:0.48 |
| 0x099B | embank | jungle>dirt | edge | 95 | 16.13 | 4.27 | 0.0 | jungle:0.57 grass:0.43 |
| 0x099C | embank | dirt>jungle | edge | 114 | 16.57 | 5.47 | 0.0 | jungle:0.54 grass:0.45 |
| 0x099F | embank | jungle>dirt | edge | 96 | 17.27 | 4.29 | 0.0 | jungle:0.56 grass:0.44 |
| 0x09AC | embank | dirt>forest | edge | 1052 | 24.72 | 6.16 | 0.003 | forest:0.54 grass:0.46 |
| 0x09AD | embank | dirt>forest | edge | 1387 | 7.85 | 6.51 | 0.004 | forest:0.53 grass:0.47 |
| 0x09AE | embank | dirt>forest | edge | 1484 | 8.55 | 6.74 | 0.003 | forest:0.53 grass:0.47 |
| 0x09AF | embank | dirt>forest | edge | 1212 | 24.81 | 6.09 | 0.004 | forest:0.54 grass:0.46 |
| 0x09B0 | embank | dirt>forest | edge | 1437 | 7.88 | 6.65 | 0.004 | forest:0.53 grass:0.46 |
| 0x09B1 | embank | dirt>forest | edge | 1141 | 24.44 | 6.09 | 0.006 | forest:0.54 grass:0.45 |
| 0x09B2 | embank | dirt>forest | edge | 1380 | 7.95 | 6.84 | 0.006 | forest:0.54 grass:0.46 |
| 0x09B3 | embank | dirt>forest | edge | 1177 | 23.93 | 5.98 | 0.002 | forest:0.54 grass:0.46 |
| 0x09B4 | embank | dirt>forest | edge | 1291 | 7.42 | 6.84 | 0.002 | forest:0.53 grass:0.47 |
| 0x09B5 | embank | dirt>forest | edge | 1100 | 24.31 | 6.21 | 0.003 | forest:0.55 grass:0.45 |
| 0x09B6 | embank | dirt>forest | edge | 1281 | 8.47 | 6.54 | 0.002 | forest:0.54 grass:0.47 |
| 0x09B7 | embank | dirt>forest | edge | 1106 | 24.39 | 6.18 | 0.003 | forest:0.54 grass:0.46 |
| 0x09B9 | embank | dirt>forest | edge | 178 | 22.7 | 5.86 | 0.0 | forest:0.51 grass:0.49 |
| 0x09BA | embank | dirt>forest | edge | 132 | 22.2 | 4.91 | 0.0 | forest:0.55 grass:0.45 |
| 0x09BD | embank | dirt>forest | edge | 175 | 24.26 | 5.88 | 0.0 | forest:0.50 grass:0.49 |
| 0x09BF | embank | dirt>forest | edge | 138 | 21.75 | 4.72 | 0.0 | forest:0.56 grass:0.44 |