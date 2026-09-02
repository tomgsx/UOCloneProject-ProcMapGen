# Macro-structure of Felucca (Britannia, x < 5120) — measured targets for the generator

Source: `analysis/macro_structure.py` (+ `analysis/macro_roads.py`), raw numbers in `out/macro-structure/macro.json`,
per-tile material map in `out/macro-structure/material.npz` (`material[x,y]` uint8, `classes` list, `mat_of_id` land-id -> class),
1/8-scale overview `docs/macro_overview.png` (yellow = detected settlement clusters, brightness = elevation).

Region analysed: x 0..5119, y 0..4095 = 20,971,008 tiles (no 0x244 void inside this window).
Note: the 261k-tile landmass in the SE corner (bbox 4106..4853 x 3080..3982) is the west part of the T2A *Lost Lands* (Delucia), and the NE white island is Dagger Isle. Both are included in the numbers below unless stated.

## Material classification used
| class | land ids |
|---|---|
| water | tiledata name "water" (0xA8-0xAB, 0x136-0x137), seafloor 0x4C-0x66, **plus any land tile carrying a water static 0x1796-0x17B2** |
| grass | name "grass" (0x3-0x6 dominant, 1.37M of 1.62M), plus 0x3DC2-0x3DE8 (swamp-edge grass) |
| forest | name "forest" (0xC4-0xC7 dominant: 2.07M of 2.29M) |
| jungle | name "jungle" (0xAC-0xAF dominant) |
| sand | name "sand" (0x16-0x19 beach, 0x1A-0x28 sand/grass transitions, 0x1C/0x20 impassable) |
| snow | name "snow" (0x11A-0x11D dominant) |
| rock | name "rock" (0x22C-0x22F = 628k of 631k; 0xE4-0xF7 / 0x235-0x238 are rock/forest transitions) |
| swamp | 0x3DE9-0x3DF0 (ML swamp, dark green, "NoName") |
| dirt | name "dirt" (0x71-0x78 road core, 0x79-0xA3/0xDC-0xE3/0x169-0x170/0x3FA-0x401 transitions) + 0x3FF8-0x3FFB (dark mud, NoName) |
| paved | wooden floor, cobblestones, stone, brick, marble, planks, tile, flagstone, sand stone |
| farm | furrows |
| cave | void 0x1FA-0x1FF, cave, lava |
Only 726 tiles (0.003%) remained unclassified.

## 1. Land / water
| quantity | value |
|---|---|
| land fraction of the 5120x4096 window | **26.9 %** (5.64M tiles); water 73.1 % |
| land fraction inside the main continent's bounding box (111..3526 x 7..3659, 12.5M tiles) | **35 %** |
| landmasses (8-connected dry components) | 84 total; 55 >= 100 tiles; 43 >= 1000; **34 >= 2000**; 22 >= 10,000 |
| main continent | 4,403,154 tiles = **78 % of all land**; bbox 3415 x 3652 |
| islands (excluding main) size percentiles (>=100 tiles) | p25 1.2k, p50 5.8k, p75 19k, p90 61k |
| major islands | Lost Lands fragment 262k (4554,3570); Moonglow/Verity 169k (4491,1206); Ocllo 151k (3582,2626); Dagger Isle 125k (4071,456); Buc's Den 66k (2711,2176); Nujel'm 54k (3681,1226); Jhelom 43k (1392,3763); Magincia 38k (3687,2140); Trinsic-south isle 30k (1888,2752); 27k (1144,3531); Skara Brae 27k (600,2159) |
| lakes (water components not connected to the sea) | 1523 components but only **32 >= 50 tiles, 3 >= 500, 0 >= 2000**; largest 1081 tiles at (1891,2778) near Trinsic; lake median (>=50) 185 tiles |

=> Britannia has essentially **no inland lakes**: all significant water touches the sea. Small ponds 50-500 tiles (about 30 of them).

Water z: 14.57M sea tiles at z=-5 (the water land tiles), 0.70M at z=-15 (sunk land tiles under water statics), a few thousand at -14..-1; 10k at +15 (elevated water ponds).

## 2. Coastline shape
| quantity | value |
|---|---|
| main continent perimeter (4-neighbour edges) | 83,562 tile-edges; 85,246 coast tiles |
| roughness P/sqrt(A) of main continent | **39.8** (a circle = 3.54; a 3:1 rectangle = 4.6) |
| roughness of all land together | 60.1 |
| box-counting fractal dimension of the coast (box 2..256) | **D = 1.23** (counts: 2->42,483, 8->10,165, 32->2,101, 128->297, 256->103) |
| peninsulas (land removed by morphological opening, disk r, area >= r^2) | r=16: 121 (median 570 tiles); r=32: 74 (median 2.2k); **r=64: 37 (median 12k)** |
| bays (water added by closing) | r=16: 97 (median 500); r=32: 74 (median 2.6k); **r=64: 39 (median 11k)** |
| biggest peninsulas (r=64) | 393k tiles the whole southern Trinsic/jungle lobe (1767,3182); 95k NW lobe (1297,377); 51k Minoc (2519,454); 43k (3204,308); 41k (1442,1583); 39k (3053,183) |
| biggest bays (r=64) | 59k Britain bay (1466,1627); 59k Cove/Lake-of-Britain bay (2168,1106); 41k (3100,298); 37k (2076,457); 32k (2671,489); 30k (1272,2871) |

Interpretation: the continent is a fat "C"/lobed shape with 30-40 peninsula/bay features at the 64-tile scale and ~120 at the 16-tile scale, with a coast that is only mildly fractal (D 1.23, i.e. Perlin/ridged-noise coast with 3-4 octaves, not a very rough one).

## 3. Biomes (fractions of land, patch statistics)
Patch = 8-connected component of the class after a 3x3 closing; only patches >= 200 tiles counted. Roughness = perimeter/sqrt(area).

| biome | % of land | patches >=200 / >=2k / >=20k | patch area p50 / p75 / p90 / p99 | largest | roughness median (p25-p75) | z mean / p50 / p95 |
|---|---|---|---|---|---|---|
| forest | **40.6** | 263 / 70 / 20 | 580 / 2.4k / 9.4k / 175k | 334k | 7.6 (6.4-10.6) | 2.5 / 0 / 15 |
| grass | **28.7** | 388 / 82 / 14 | 590 / 1.6k / 5.3k / 89k | 197k | 8.0 (5.0-15.3) | 4.3 / 0 / 25 |
| rock (mountain) | **11.2** | 36 / 18 / 10 | 2.2k / 24k / 46k / 139k | 177k | 7.4 (5.5-10.3) | 42.3 / 46 / 60 |
| jungle | **7.3** | 73 / 20 / 2 | 810 / 2.9k / 7.3k / 94k | 221k | 8.7 | 3.5 / 0 / 20 |
| dirt (roads, mud) | 4.0 | 85 / 18 / 1 | 770 / 1.7k / 4.7k / 24k | 51k | 12.8 (linear) | 4.1 |
| paved (towns) | 3.4 | 106 / 15 / 1 | 380 / 880 / 4.0k / 17.6k | 22.8k (Britain) | 5.0 | 7.0 |
| sand | 2.0 | 29 / 4 / 2 | 450 / 1.2k / 3.8k / 27k | 27.5k | 13.8 (beach strips) | 2.3, p5 = -4 |
| snow | 1.5 | 2 / 1 / 1 | (Dagger Isle 81k + Ice Isle) | 81k | 10.4 | **0.5 (flat!)** |
| swamp | 1.1 | 4 / 3 / 2 | 18k / 24k / 30k | 35k | 5.8 | 0.0 (flat) |
| farm (furrows) | 0.3 | 22 / 0 / 0 | 620 / 840 / 1.0k | 1024 (32x32 fields) | 4.1 | |
| cave/void | 0.07 | 1 | | 3.6k | | |

Key facts for the generator:
* Forest+grass = 69 % of land, in large interlocking patches; the p99 forest patch is 175k tiles; median patch only ~600 tiles, i.e. the landscape is a few huge regions plus hundreds of small clearings/groves of 200-2000 tiles.
* Jungle is the southern biome: 50 % of land in band y 3072-3584, 27 % in y>3584, 11 % in y 2560-3072, ~0 north of y 2048.
* Snow is **not** tied to elevation (mean z 0.5): it exists only as two flat northern/north-eastern islands (Dagger Isle, x 3864-4297 y 175-759, and Ice Isle) — 6 % of land in y<512, 3 % in y 512-1024, zero south of y 1024.
* Sand is rare (2 %) and almost entirely coastal beach (z p5 = -4, p50 = 0): there is no desert on the main continent (the desert is in the Lost Lands, x>5120). Beaches are thin strips (roughness 13.8).
* Swamp: 3 flat patches of 14-35k tiles at (1932,2334), (1161,2881), (2029,1010), all at z=0.
* Rock z: p5 10, p25 36, p50 46, p75 52, p95 60, p99 66. Mountain interiors sit at z 36-60, i.e. a plateau, not a peaked ridge.

### Biome vs elevation (fraction of land tiles in the z band)
| z band | land tiles | grass | forest | jungle | sand | rock |
|---|---|---|---|---|---|---|
| < -1 | 47k | .33 | .05 | .02 | **.36** | .07 |
| [-1,1) | **3.62M (64 % of land)** | .31 | .46 | .09 | .02 | .002 |
| [1,5) | 272k | .38 | .38 | .12 | .05 | .03 |
| [5,10) | 467k | .24 | .65 | .04 | .03 | .03 |
| [10,20) | 362k | .34 | .37 | .07 | .01 | .08 |
| [20,40) | 364k | .26 | .14 | .04 | .03 | **.39** |
| [40,80) | 496k | .08 | .03 | .02 | 0 | **.86** |
| >= 80 | 7k | .42 | 0 | .26 | 0 | .31 |

Land z overall: mean 7.7; p50 0; p75 6; p95 49; p99 59; p99.9 80; max 125. **64 % of land is exactly z=0**, 20 % is z>10, 11 % is z>30.
=> Generator rule: z=0 lowlands everywhere, gentle hills to z 5-20 mostly forested, rock starts dominating above z 20 and is nearly exclusive above z 40; peaks 60-80.

### Biome vs latitude (fraction of land in each y band)
| y band | land frac | grass | forest | jungle | sand | snow | rock | swamp |
|---|---|---|---|---|---|---|---|---|
| 0-512 | .27 | .39 | .36 | 0 | .01 | .06 | .16 | 0 |
| 512-1024 | .47 | .25 | .52 | 0 | .03 | .03 | .08 | .01 |
| 1024-1536 | .45 | .18 | .52 | 0 | .03 | 0 | .18 | .01 |
| 1536-2048 | .20 | .21 | .46 | .01 | .01 | 0 | .16 | 0 |
| 2048-2560 | .29 | .32 | .49 | .06 | .02 | 0 | .01 | .04 |
| 2560-3072 | .20 | .32 | .30 | .11 | .01 | 0 | .13 | .03 |
| 3072-3584 | .18 | .39 | .01 | **.51** | .02 | 0 | .03 | 0 |
| 3584-4096 | .09 | .44 | 0 | .27 | .02 | 0 | .13 | 0 |

Longitude: the west (x<1024) is 67 % forest (Yew); the centre x 1024-2048 holds 61 % land coverage (densest part of the continent); the east (x>3072) is islands only (land 12 %).

## 4. Mountain ranges (rock patches after disk-3 closing, >= 500 tiles)
23 ranges >= 500 tiles, 12 >= 5000. Length = extent along PCA major axis; mean width = area/length; core width = 2 x p95 of the inner distance transform.

| area | centre | length | mean width | core width | orient (deg from +x) | z mean | z p95 | z max |
|---|---|---|---|---|---|---|---|---|
| 259,768 | (1273,1295) central "Britain-Yew" massif | 1275 | 204 | 111 | 126 | 43 | 55 | 76 |
| 68,066 | (1319,2719) south-west (Destard) | 691 | 99 | 76 | 40 | 46 | 60 | 75 |
| 52,836 | (577,1564) west coast | 512 | 103 | 103 | 24 | 41 | 58 | 73 |
| 41,401 | (4069,432) Dagger Isle | 456 | 91 | 78 | 43 | 46 | 59 | 90 |
| 40,203 | (2572,92) north Minoc | 437 | 92 | 62 | 1 | 43 | 65 | 85 |
| 32,874 | (1993,280) | 309 | 106 | 65 | 143 | 48 | 60 | 73 |
| 31,948 | (1823,983) Wrong/Britain-N | 452 | 71 | 56 | 96 | 43 | 60 | 69 |
| 26,239 | (4722,3714) Lost Lands | 347 | 76 | 60 | 128 | 29 | 60 | 78 |
| 24,027 | (2460,875) Minoc-Covetous | 325 | 74 | 27 | 6 | 40 | 66 | 123 |
| 14,700 | (341,1418) | 196 | 75 | 84 | 170 | 30 | 54 | 84 |
| 7.8k, 6.7k, 4.7k, 4.6k ... | | 100-200 | 25-40 | 20-40 | | 34-66 | | up to 125 |

Targets: one dominant massif ~250k tiles, ~1300 long x ~200 wide (it is a branched blob, not a line); 8-10 secondary ranges of 25-70k tiles, 300-700 long, 70-100 wide; a dozen hills of 1-8k tiles. Plateau height z 40-55, ridge tops 60-90, rare spikes to 125. Rock patch roughness 7.4 (fairly smooth outline).

## 5. Towns
Detected as 16x16 cells with >= 12 wall/roof/door statics + paved land tiles, closed and 8-connected: 48 clusters, 21 with >= 6000 tiles.

| town | centre | area (tiles) | wall/roof/door statics |
|---|---|---|---|
| Britain | (1474,1630) | 105,728 (bbox 512x432) | 32,767 |
| Trinsic | (1921,2783) | 68,096 | 18,093 |
| Vesper | (2890,834) | 63,232 | 17,185 |
| Nujel'm | (3685,1230) | 52,224 | 10,424 |
| Ocllo | (3670,2664) | 41,472 | 8,553 |
| Buccaneer's Den | (2689,2172) | 39,424 | 5,983 |
| Minoc | (2505,531) | 36,608 | 9,931 |
| Jhelom | (1392,3773) | 35,584 | 15,556 |
| Serpent's Hold | (2978,3431) | 33,536 | 10,454 |
| Moonglow | (4445,1130) | 25,600 | 8,086 |
| Skara Brae | (601,2181) | 16,896 | 9,329 |
| Yew (3 clusters: abbey/town/Empath) | (603,980),(334,837),(607,833) | 11.5k / 10.8k / 7.7k | 2.9k / 4.1k / 2.1k |
| Cove | (2241,1189) | 5,888 | 1,904 |
| Magincia | (3725,2244) | 7,424 | 1,717 |
| unnamed (1155,2233) (Destard area keep) | | 12,800 | 1,912 |
| unnamed (986,741) (Shrine/keep north of Britain) | | 9,216 | 2,203 |

Inter-town distances (21 major clusters): nearest-neighbour min 147, **median 424**, mean 513, max 1303 tiles; all-pairs p10 1015, p25 1500, p50 2330, p75 3220, p90 3810 (Yew/Moonglow sub-clusters inflate the small end; between distinct towns the nearest-neighbour spacing is ~500-900 tiles). Roughly 9 major cities (>30k tiles) + 6 small towns (5-17k) + 30 hamlets/keeps (1-5k) for a 4.4M-tile continent; 6 of the 15 named settlements are on islands.

## 6. Roads
Road core = dirt road ids 0x71-0x78 / 0x3F8-0x401 / 0x3FF8-0x3FFB + cobblestones (204,030 tiles), plus 9,342 bridge static tiles.
* Skeleton length of the road network: **36,600 tiles**; width along the skeleton p10 2, p25 4, **p50 5.7**, p75 8, p90 10 tiles (mean area/length 5.6).
* 60 components >= 300 tiles; largest skeleton lengths 8.7k, 4.1k, 4.0k, 3.6k, 2.2k, 1.4k...
* Town connectivity by continuous road (including dirt transitions and bridges): **one connected system Britain - Yew (3 clusters) - Vesper - Minoc** (the northern loop); Trinsic, Skara Brae and all island towns (Jhelom, Moonglow, Nujel'm, Ocllo, Magincia, Buc's Den, Serpent's Hold) only have local streets. The nearest road tile of Trinsic's network is 1031 tiles from Britain's: the Britain-Trinsic route crosses plain grass.
=> Generator target: a dirt road 4-8 wide linking the 3-4 mainland cities in the densest region, ~35k tiles of skeleton total including streets; do not try to connect every town.

## 7. Rivers
River = water minus morphological opening (disk r=8), components >= 400 tiles with skeleton >= 60.
* **22 rivers (>= 60 long), 9 >= 200 long**, total skeleton length 6,530 tiles. Width (area/length) 5-10 tiles, typical **7**.
* Longest: 1565 tiles (Trinsic river, (1867,2823), source at (1654,2897) in a z~18 rocky area); 779 (Skara Brae / Spiritwood river, source z 0); 736 (Vesper canals (3272,417)); 593 (Britain river from (1291,1584), source land z 16); 388 (1899,683, source z 12 with 31 % rock nearby); 300 (Buc's Den).
* 21 of 22 reach the sea; one (138 long) ends in the 1081-tile lake near Trinsic. None connects two lakes.
* Sources: only 5 of 22 have rock within 40x40 of the source; 12 start at flat z~0 land (they simply fade out / begin in forest or swamp). Median source land z = 1. So rivers in UO are short coastal inlets/estuaries that start in lowland, NOT mountain-fed.
* Water z inside rivers: median -15 (land sunk under water statics, same as coast), land banks at z 0-3.

## 8. Suggested target table for a 5120x4096 (or scaled) generator
| parameter | target |
|---|---|
| land fraction (whole window) | 27 % (35 % of the continent's bbox) |
| landmasses | 1 main continent = 78 % of land + ~10 islands of 25k-260k + ~25 of 2k-25k + ~20 < 2k |
| lakes | ~30 ponds of 50-500 tiles; none > 1.1k |
| coast | P/sqrt(A) ~ 40; box-count D ~ 1.23; ~37 peninsulas and ~39 bays at r=64 (median 11-12k tiles), ~120/~100 at r=16 |
| elevation | 64 % of land z=0; p75 6; p95 49; p99 59; max ~125; mountains plateau z 36-60 |
| forest | 41 % of land; 20 patches > 20k (largest 330k), ~250 patches 200-20k, roughness ~7.6 |
| grass | 29 %; 14 patches > 20k, ~390 patches >= 200, roughness ~8 |
| rock | 11 %; 1 massif 260k (1300x200), ~9 ranges 25-70k (300-700 x 70-100), ~12 hills 1-8k; 86 % of z>=40 land is rock |
| jungle | 7 %; confined to the southern 25 % of the map (50 % of land there); 2 patches > 20k |
| sand | 2 %; thin beach strips, roughness ~14, z -4..3; no inland desert |
| snow | 1.5 %; one/two flat northern islands, never on mountains |
| swamp | 1 %; 3 flat patches of 15-35k |
| dirt/road | 4 % (204k tiles), skeleton ~36k, width 4-8 |
| paved | 3.4 %; ~9 cities of 30-105k tiles, 6 towns of 5-17k, ~30 hamlets 1-5k; nearest-town spacing ~500-900 tiles |
| rivers | ~20, 7 wide, 100-1500 long (total ~6.5k), starting in lowland (z 0-18) and ending in the sea |
