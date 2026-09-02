# Elevation in Britannia (Felucca, x < 5120, void 0x244 excluded)

Scripts: `analysis/elevation_ids.py` (id usage), `analysis/elevation_stats.py` (per-material histograms),
`analysis/elevation_shape.py` (mountain/hill shape, cross-sections), `analysis/elevation_extra.py` (corner-diff fix, more sections).
Data: `out/elevation/land_id_usage.json`, `elevation_stats.json` (z / |dz4| / |dz8| / corner-diff histograms per material,
boundary dz histograms, impassable-vs-passable dz, per-rock-id slope), `elevation_shape.json`, `elevation_extra.json`, `cornerdiff.npz`.

Definitions: dz4/dz8 = |z(nb) - z(self)| over 4/8 neighbours; "corner diff" = max-min of the 4 corner z of the CentrED land quad
(z at (x,y),(x+1,y),(x,y+1),(x+1,y+1)); "stretched" = corner diff > 0.

## Material ranges used (from tiledata names + usage)
| material | ids | tiles |
|---|---|---|
| grass | 0x3-0x6 (+0x7D-0x7E, 0xC0-0xC3, 0xD8-0xDB edge variants) | 1,595,118 |
| forest | 0xC4-0xC7 (+0xC8-0xD7, 0xF0-0xF3, 0x161-0x168) | 2,286,405 |
| jungle | 0xAC-0xBF, 0x100-0x103 | 421,505 |
| dry sand | 0x16-0x19 | 76,373 |
| impassable sand (coast trench / underwater) | 0x1A-0x2A | 98,843 |
| dirt | 0x71-0x7C, 0x82-0x8C | 137,999 |
| impassable dirt (dirt cliff/edge set) | 0x8D-0xA3, 0xDC-0xE3 | 21,512 |
| mountain rock (Impassable) | 0x22C-0x22F | 628,143 |
| rock edge variants (Impassable) | 0x21F-0x22B, 0x230, 0x235-0x238, 0xE4-0xE7, 0xF4-0xF7, 0x1D3-0x1DA | 7,149 |
| grass/rock edge (Impassable, name "grass") | 0x231-0x234, 0x239-0x23C | 12,190 |
| snow | 0x11A-0x11D (impassable 0x10C-0x117, 0x17D-0x185) | 80,253 |
| swamp | 0x3DC2-0x3DF0 | 75,928 |
| cave floor | 0x245-0x249 | 379 |
| town floors | 0x406-0x411, 0x3E9-0x3EC, 0x442-0x449, 0x486-0x489 | 159,164 |

**There is no walkable rock in Britannia.** Every "rock" land id is Impassable. Mountains are solid impassable masses of
0x22C-0x22F; walkable ground on mountains is grass/forest/jungle at high z (at z>=40: grass 38k, forest 10k, jungle 9k tiles).

## Per-material statistics (z, slope, stretching)
| material | z p50 / p95 / p99 | mean dz4 | dz4 p90 / p99 | stretched | cd>=2 | cd>=5 | cd>=10 | cd>=20 | max cd |
|---|---|---|---|---|---|---|---|---|---|
| grass | 0 / 25 / 50 | 0.35 | 1 / 7 | 16.3% | 12.1% | 4.0% | 0.5% | 0.03% | 71 |
| forest | 0 / 15 / 30 | 0.17 | 0 / 5 | 9.7% | 7.4% | 2.8% | 0.2% | 0.01% | 65 |
| jungle | 0 / 20 / 60 | 0.22 | 0 / 5 | 13.4% | 9.8% | 3.1% | 0.2% | 0.01% | 35 |
| dry sand | 0 / 20 / 20 | 0.63 | 1 / 12 | 20.7% | 17.6% | 10.4% | 2.5% | 0.18% | 44 |
| dirt | 0 / 30 / 40 | 0.23 | 0 / 5 | 9.6% | 6.7% | 2.0% | 0.4% | 0.04% | 45 |
| snow | 0 / 1 / 15 | 0.13 | 0 / 3 | 7.4% | 4.1% | 1.2% | 0.2% | 0.09% | 50 |
| swamp | 0 / 0 / 0 | 0.00 | 0 / 0 | 0.3% | 0.1% | 0 | 0 | 0 | 11 |
| town floors | 0 / 30 / 50 | 0.03 | 0 / 1 | 2.3% | 1.3% | 0.2% | 0.1% | 0 | 35 |
| mountain rock 0x22C-F | 46 / 60 / 66 | 3.23 | 8 / 16 | 91.8% | 86.6% | 57.2% | 19.5% | 1.9% | 73 |
| grass/rock edge 0x231-0x23C | 3 / 26 / 100 | 4.52 | 12 / 24 | 98.5% | 97.7% | 84.8% | 39.5% | 5.5% | 55 |
| rock edge variants | 9 / 40 / 99 | 6.30 | 13 / 24 | 99.4% | 99.1% | 94.7% | 69.2% | 18.3% | 59 |
| impassable dirt | 2 / 30 / 50 | 4.84 | 15 / 35 | 98.5% | 98.5% | 94.0% | 75.2% | 17.9% | 54 |
| impassable sand (coast) | -5 / 4 / 17 | 5.42 | 14 / 27 | 99.2% | 99.2% | 98.9% | 97.3% | 7.4% | 66 |
| seafloor 0x4C-0x66 | -15 / -5 / 15 | 0.80 | 0 / 13 | 14.7% | 14.4% | 14.0% | 13.8% | 0.03% | 51 |
| water 0xA8-0xAB | -5 / -5 / -5 | 0.01 | 0 / 0 | 0.0% | - | - | - | - | - |

Whole map (20.97M valid quads): corner diff p95=3, p99=11, p99.9=20, p99.99=35, max=73; >=30: 7,142 quads, >=40: 1,279, >=50: 258, >=60: 39, >=80: 0.
Walkable-only quads (all 4 corners passable, 4.88M): p90=1, p95=3, p99=6, p99.9=12, max 55; >=5: 2.7%, >=10: 0.24%, >=20: 0.016%.

## Answers
**(1) Plains / towns and z range.** Plains are flat at exactly z=0: 3.59M of 4.96M walkable tiles (72%) are at z=0; walkable z p75=1,
p90=11, p95=20, p99=44, p99.9=79. Town floors p50=0, p95=30 (towns on terraces: Britain 0, some at 20/30, z 0..50). Overall z range
-60 (seafloor) to 125 (rock). Snow biome (Dagger Isle) is at z 0 (p95 = 1) - snow is a latitude biome, NOT a mountain cap; no snow caps exist.
Walkable z bands: -30..-5: 15k, -5..0: 45k, 0: 3.59M, 1-2: 133k, 3-5: 373k, 6-9: 189k, 10-19: 325k, 20-39: 215k, 40-59: 58k, 60-79: 12k, 80-99: 3.4k, >=100: 1.4k.
Grass z>0 is strongly quantised at plateau levels: spikes at z=1 (61k), 5 (35k), 6 (44k), 10 (26k), 15 (42k), 20 (27k), 30 (14k), 40 (8k), 60 (3k), 80 (1.9k), 100 (0.7k).
So the designers used flat terraces at 5/10/15/20/30/40/60/80/100 with short ramps between them.

**(2) Hills.** Walkable ground is mostly flat: along +x only 7.3% of walkable tile pairs have dz != 0. When non-zero, |dz| p50=2, p75=3,
p90=5, p95=7, p99=10 (histogram of non-zero |dz|: 1:149k, 2:74k, 3:51k, 4:28k, 5:26k, 6:11k, 7:8.5k, 8:4k, 10:2k, 15:0.8k, 20:0.2k).
Monotonic climbs of >=10 z on walkable ground (sampled rows/columns, 1,279 climbs): length p25=2, p50=3, p75=6, p90=9 tiles; rise p50=14,
p90=23; slope p10=2, p50=4, p90=11 z/tile. I.e. climbing 10 z typically takes 2-4 tiles (4 z/tile), rarely more than 9 tiles.
Surface is smooth, not noisy: only 4.6% of hill tiles (z 1..60) are strict local extrema along x. Hills = flat terrace, 2-6 tile ramp at 3-5 z/tile,
flat terrace. Example (hill x=815..854,y=2298, id/z): `0x4/0 0x6/0 0x3/2 0x6/5 0x3/7 0x3/8 0x6/12 0x4/17 0x6/21 0x5/22 0x6/19 0x3/15 0x5/12 0x6/10 0x6/9 0x6/7 0x4/4 0x6/1 0x4/0` - a 22-z grass knoll, ~8 tiles each side, no id change.

**(3) Mountains.** Built from impassable 0x22C-0x22F only (the 4 ids are used uniformly, identical slope stats: mean corner diff 6.2, p50 5, p90 13, p99 22, 8% flat).
Profile vs. distance into the rock mass (chessboard distance d, medians): d=1: z 15 (p10 3, p90 34), d=2: 26, d=3: 33, d=4: 38, d=5: 41, d=6: 44, d=8: 47, d=12: 50,
d>=14: 50 (p10 ~36, p90 ~60). So a mountain rises ~45 z in the first ~8 tiles (11, 7, 5, 3, 3, 2, ... z per ring: steepest at the foot, flattening inward)
then becomes an undulating plateau at z 45-55 (interior noise dz4 mean 3.2, p90 8 - rock interiors are deliberately bumpy, 92% stretched).
Rock components (35 of >=200 tiles): thickness p50 14, p90 42 tiles; max z p50 65, p90 85, p99 124. Rock z overall: p50 46, p95 60, p99 66, p99.9 97, max 125.
Cliff foot: rock foot tile minus adjacent passable tile: p25 0, p50 +2, p75 +9, p95 +18, p99 +25 (31% of foot tiles are level with the ground; 5% are lower, i.e. rock sunk below a raised road).
Second ring minus foot: p50 +8, p75 +11, p95 +17. The edge ids 0x231-0x234/0x239-0x23C ("grass" with rock corners) and 0x235-0x238 (rock with grass corners)
form a 1-tile-wide transition band around ~4% of the mountain perimeter only (12k + 2.5k tiles vs 36k foot tiles); most of the perimeter is plain grass touching plain 0x22C-F
(the land-art blend is done by the texture). Edge ids carry larger slopes: 0x231-0x234 mean cd 6-8, 0x239-0x23C 9-12, 0x235-0x238 10-17, 0xE4-0xE7/0xF4-0xF7 9-17.
Mountain tops: the rock plateau itself (z~50), with walkable grass/forest/jungle terraces inset at z=60/80/100 (see high_plateau section). No snow caps.
Section (x=1260, y=896..935, grass -> mountain): `0x3/0 0x3/0 0x239/2 0x22e/7 0x22e/11 0x22e/14 0x22d/16 0x22d/18 0x22c/20 0x22d/24 0x22f/30 0x22f/32 0x22d/37 0x22f/38 0x22c/40 0x22f/44 0x22d/44 0x22c/50 0x22f/51 0x22d/50 0x22d/47 0x22d/49 ...`
Section (x=2540..2579, y=480, sea -> mountain): `0x64/-5 0xaa/-5 0x64/-15 0x26/-15 0x20/-15 0x26/-3 0x26/2 0x4/15 0x6/15 0x22d/17 0x22f/24 0x22f/33 0x22d/45 0x22e/53 0x22e/57 0x22e/62 0x22c/69 0x22e/76 0x22d/78 0x22d/82 0x22f/83 0x22c/78 ... 0x22d/93 0x22e/95 0x22c/98 0x22d/100`
Mountain interior (x=1245..1284, y=1168): `0x22e/50 0x22c/43 0x22d/43 0x22c/51 0x22d/51 0x22d/46 0x22e/45 0x22c/41 0x22e/41 0x22e/55 0x22e/47 0x22d/41 0x22d/56 0x22d/42 0x22d/52 0x22e/54 0x22e/44 0x22c/58 ...` (random +-6 around 48).
High plateau (x=4633, y=3638..3677): `0x3/80 ... 0x6/80 0x6/86 0x22e/83 0x22d/83 0x235/96 0x233/102 0x6/100 0x5/100 ... 0xae/100 0xad/100 ... 0x239/100 0x22e/113 0x236/80 0x234/80 0x6/80` - a z=100 jungle/grass terrace inside a z=80 terrace, separated by 2-3 tile rock rims rising 13-20 z above the terrace.

**(4) Material boundaries (signed dz = z(B) - z(A) over 4-neighbour edges).**
| A -> B | n | flat | |dz|<=2 | |dz| p90 / p99 | B higher | B lower |
|---|---|---|---|---|---|---|
| grass -> dirt | 53,935 | 91.8% | 96.6% | 0 / 5 | 3.9% | 4.3% |
| grass -> forest | 261,699 | 87.5% | 95.1% | 1 / 6 | 6.7% | 5.8% |
| grass -> jungle | 94,607 | 80.9% | 93.7% | 2 / 6 | 9.9% | 9.3% |
| grass -> swamp | 4,025 | 99.1% | 100% | 0 / 0 | | |
| grass -> dry sand | 604 | 88.6% | 90.2% | 2 / 20 | 0.8% | 10.6% |
| dry sand -> impassable sand (coast) | 4,155 | 16.1% | 39% | 15 / 35 | 19% | 65% (mean -4.9) |
| grass -> grass/rock edge 0x231-0x23C | 15,875 | 31.9% | 59.6% | 11 / 25 | 65.7% | 2.3% (mean +3.8) |
| grass/rock edge -> rock 0x22C-F | 10,635 | 2.4% | 10.2% | 16 / 26 | 94.9% | 2.7% (mean +8.4) |
| grass -> rock 0x22C-F (direct) | 1,241 | 15.8% | 30.9% | 19 / 30 | 77.5% | 6.7% (mean +6.1) |
| dirt -> rock | 825 | 30.5% | 47.4% | 15 / 23 | 66.5% | 2.9% |
| forest -> rock | 319 | 20.1% | 32.9% | 18 / 30 | 61% | 19% |
| dry sand -> rock | 416 | 48.1% | 56.7% | 11 / 32 | 45% | 6.5% |
| dirt -> impassable dirt 0x8D-0xA3 | 8,759 | 32.1% | 53.5% | 15 / 25 | 64% | 4% |
Conclusion: soft-material transitions (grass/forest/jungle/dirt/sand/swamp) are placed on FLAT ground (81-99% dz=0, 94-100% |dz|<=2) - the texture changes,
the height does not. Only transitions into Impassable classes (rock, impassable dirt, coast trench) carry a height step, and it is a step UP into rock (+6..+8 mean,
p90 15-19) or DOWN into the sea trench (-15 typical).

**(5) Impassable land ids.** Apart from water/seafloor and the coast trench, Impassable ids are: mountain rock (628k), grass/rock and rock edge variants (19k),
impassable dirt 0x8D-0xA3/0xDC-0xE3 (21.5k: the dirt-cliff set used at raised roads, dungeon rims, and as cliff edges between terraces - see section y=1620 where a z=30 terrace
drops through 0x9b/30 0x8d/10 0x64/-15 into a moat), impassable forest 0xEC-0xEF (3.3k), impassable snow (2.8k). Across 64,436 impassable/passable 4-neighbour edges
(rock, dirt-cliff etc. vs passable land): |dz| p50 2, p75 9, p90 15, p95 18, p99 30; passable neighbour lower 49%, equal 34%, higher 17%. All these impassable ids are
>=92% stretched with mean corner diff 4.5-6.3 (vs 0.1-0.6 for walkable materials): in Britannia, "impassable" is where the slope lives.

**(6) Extreme corner diffs.** p99 = 11 (whole map), max = 73 (never >= 80). Only 1,279 quads (0.006%) reach >= 40 and 94% of them are Impassable:
dirt-cliff 0x96/0x8F/0x99 and coast sand 0x1C/0x23/0x24/0x20 (corners like [-15,30,-15,30] at a moat/trench next to a z=30 terrace, or [-15,-15,-15,35] at a cliff coast),
plus a few hundred rock quads. Walkable quads never exceed 55 and p99.9 = 12.
Water ids are always flat (corner diff p99 = 0 except at the x=5119/5120 seam).

## Recipe for the generator (target slope statistics)
1. **Base plains**: z = 0 exactly everywhere that is "plains/town". Do not add noise to plains (Britannia plains have mean dz4 0.17-0.35 and 84-90% of walkable quads are perfectly flat).
2. **Walkable rolling terrain / hills**: terraces at quantised levels (5, 6, 10, 15, 20, 30, 40) joined by ramps of 2-6 tiles at 3-5 z/tile (never > 10 z/tile on walkable ground;
   corner diff on walkable quads: >=5 in ~3%, >=10 in ~0.25%, >=20 in ~0.02%, cap at 15-20). Keep the surface monotone along ramps (local-extrema fraction < 5%);
   a knoll of 20 z should span ~16 tiles. Change materials (grass/forest/dirt/sand/jungle) only where dz=0 (keep >= 90% of soft boundaries flat and >= 95% within |dz|<=2).
3. **Mountains with cliff faces**: rasterise the mountain footprint as impassable 0x22C-0x22F (random choice of the 4 ids). Height by distance-to-edge d: z(d) ~ ground + {1:15, 2:26, 3:33, 4:38, 5:41, 6:44, 8:47, 12+:50}
   (rise ~45 over 8 tiles: 11, 7, 5, 3, 3, 2, 1.5 ... z per ring), then plateau at 45-55 with +-5 random bumps (rock interior corner diff p50 5, p90 13, p99 22; 8% flat).
   Foot tile: 0 to +9 above the adjacent ground (p50 +2; 30% level). Optionally use 0x231-0x234/0x239-0x23C on the grass side and 0x235-0x238 on the rock side for a few
   % of the perimeter (Britannia does it on ~4%). For peaks 60-125: keep rising at 2-4 z/tile (section y=480 reaches 100 in 25 tiles). Walkable mountain passes/terraces
   are grass/forest/jungle at 60/80/100 surrounded by a 2-3 tile rock rim 13-20 z higher than the terrace. No snow caps; snow is a flat (z 0) biome.
4. **Cliffs on walkable terrain (terrace rims, moats, dungeon rims)**: use the impassable dirt set 0x8D-0xA3 / 0xDC-0xE3 as a 1-tile band with corner diff 10-25 (p50 ~15) and up to 45.
5. **Absolute caps**: corner diff <= 35 for 99.99% of quads, never > 73; water land ids perfectly flat at their own z; coast trench per the coast anatomy (-15 floor vs 0..-4 beach).
