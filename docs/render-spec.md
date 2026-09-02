# render-spec — CentrED# 0.6.11.31 rendering geometry (for a faithful software renderer)

Sources read (all read-only): `CentrED/Camera.cs`, `Renderer/MapRenderer.cs`, `Renderer/MapEffect.cs`,
`Renderer/Shaders/MapEffect.fx`, `Map/LandObject.cs`, `Map/StaticObject.cs`, `Map/MapObject.cs`,
`Map/TileObject.cs`, `Map/MapManager.cs`, `Map/StaticsManager.cs`, `Map/Epsilon.cs`, `HuesManager.cs`,
`Lights/LightsManager.cs`, `Config.cs`, `UI/Windows/OptionsWindow.cs`, `Shared/StaticTile.cs`, `Shared/StaticBlock.cs`;
ClassicUO (`ClassicUO.Renderer/Arts/Art.cs`, `Texmaps/Texmap.cs`,
`ClassicUO.Assets/ArtLoader.cs`, `TexmapsLoader.cs`, `HuesLoader.cs`, `HuesHelper.cs`, `ClassicUO.Client/Game/Pathfinder.cs`,
`GameObjects/Land.cs`); RunUO 3.1 / ServUO 57 `Movement.cs`, `Map.GetAverageZ`, `TileData.CalcHeight`.
Verification scripts: `analysis/render-spec_0{1..4}_*.py`, data in `out/render-spec/*.json`.

Constants (`Constants.cs`): `RSQRT2 = 0.70710678`, `TILE_SIZE = 44*RSQRT2 = 31.1127`, `TILE_Z_SCALE = 4`.
World units: x,y in "world px" (1 tile = TILE_SIZE), z in px (1 map z = 4 px).

## 1. Defaults that determine the "normal" appearance
| Option | Default | Effect |
|---|---|---|
| `Config.PreferTexMaps` | **false** | flat tiles use 44x44 land art; texmap only when stretched / no art |
| `Config.ObjectBrightHighlight` | false | only affects hover-highlight alpha (0.5 vs 2.0); not default appearance |
| `MapManager.FlatView` | false | when true: all land z=0, static z=0, no stretching, no hidden-static rule |
| `LightsManager.ClassicUONormals` | false | alternate normal formula (see 6.2) |
| `LightsManager.GlobalLightLevel` | 30 (= `MaxGlobalLight`) | light-map pass skipped entirely; **no global darkening, no light sources** |
| `AltLights`, `DarkNights`, `ColoredLights` | false,false,true | irrelevant while GlobalLightLevel==30 |
| `ShowNoDraw` | false | hides land id<=2 and static ids 0x0001,0x21BC,0x63D3,0x2198-0x2199,0x21A0-0x21A4 (+0x9E4C/0x9E64/0x9E65/0x9E7D unless they are non-Background non-Surface) |
| `ShowGrid`, `WalkableSurfaces`, `ShowVirtualLayer` | false | off |
| `AnimatedStatics` | true | statics with tiledata Animation flag cycle art id + animdata frame (static renderer: use frame 0 = base id; `AnimOffset` from `art` index is 0 for all non-animating entries) |
| `MinZ/MaxZ` | -128/127 | z-range filter off |
| Render target clear | `Color.Black` | background is black |
| Sampler | `PointClamp` | nearest-neighbour texturing, no filtering |
| Rasterizer | `CullNone` | winding irrelevant |
| Blend | `AlphaBlend` (premultiplied: src*1 + dst*(1-srcA)) | alpha==0 texels are `discard`ed in PS anyway |
| Depth | `DepthBufferEnable`, write on, `CompareFunction.Less` | see 5 |
| Zoom | 1.0 (clamped 0.2..4) | pure 2D scale about screen centre |

## 2. World -> screen projection (exact; verified numerically to 6e-11, `render-spec_02_projection.py`)
Camera: `view = LookAt(Position, (Pos.x,Pos.y,0), up=(-1,-1,0))`, `proj = mirrorX * oblique * translate(0,768,0) * ortho(W,H,0,1536) * scale(Zoom)`;
Position.z = 768; yaw/pitch/roll = 0. With `cx,cy = Camera.Position.xy` (world px) and viewport W x H:

```
screen_x = W/2 + Zoom * ( (wx - cx) - (wy - cy) ) / sqrt2
screen_y = H/2 + Zoom * ( ((wx - cx) + (wy - cy)) / sqrt2  -  wz )        (y grows downward)
depth    = (768 - wz) / 1536                                             (NDC z in [0,1]; INDEPENDENT of x,y; smaller = nearer)
```
In tile units (world = tile*TILE_SIZE, wz = 4*z): **22 px per tile on both axes, 4 px per z**:
```
sx = W/2 + Zoom*22*(tx - ty - (cxT - cyT))
sy = H/2 + Zoom*22*(tx + ty - (cxT + cyT)) - Zoom*4*z
```
Land vertex 0 of tile (X,Y) is at world ((X-1)*T, (Y-1)*T) — i.e. CentrED draws the diamond of tile (X,Y) **one tile up-left of the "natural" origin**; a static at (X,Y) sits at world (X*T, Y*T) which is vertex 3 (bottom tip) of that same diamond. Net effect: the static's bottom-centre is the bottom tip of its own tile's diamond (same as the classic client).
A land diamond is **44 px wide x 44 px tall** (top tip v0, right v1 = v0+(22,22), left v2 = v0+(-22,22), bottom v3 = v0+(0,44)) when flat. (The earlier "44x22" note is wrong.)

## 3. Land quad
`LandObject.UpdateCorners` (non-FlatView):
```
v0 = ((X-1)T, (Y-1)T, 4*z(X,Y))        # top    (tile's own z)
v1 = ( X   T, (Y-1)T, 4*z(X+1,Y))      # right
v2 = ((X-1)T,  Y   T, 4*z(X,Y+1))      # left
v3 = ( X   T,  Y   T, 4*z(X+1,Y+1))    # bottom
```
Neighbour lookups are clamped to map bounds (missing -> own z). **AlwaysFlat** tiles (tiledata `TexID == 0` OR `Wet` flag) use their own z for all 4 corners (a flat diamond at z). Water land 0xA8-0xAB (TexID 0, Wet), 0x136/0x137 (Wet) are always flat. Note a *non-water* neighbour still takes the water tile's z for the shared corner, so a stretched shore tile "drapes" down/up to the water tile's z while the water diamond stays flat -> the gap must be covered by water statics (Britannia does this with 0x1796-0x17B2 at z=-5 over seafloor at -15).

Index buffer (`GenerateIndexArray`): per quad `(0,1,2),(3,2,1)` -> triangle A = (top,right,left), triangle B = (bottom,left,right). **The shared diagonal is the left–right edge (the (X,Y+1)–(X+1,Y) line = the horizontal screen diagonal of the diamond).** Depth and UV are interpolated linearly per triangle (orthographic, so screen-space-linear == world-linear).

Texture choice (`UpdateId`), with `isTexMapValid = texidx entry at index **landId** (NOT TexID!) is non-empty`, `isLandTileValid = artidx[landId] non-empty`:
```
isStretched = corners differ
if isTexMapValid and not alwaysFlat:  isStretched |= CalculateNormals()  -> true if ANY of the 4 corner tiles (X,Y),(X+1,Y),(X,Y+1),(X+1,Y+1) has a 4-neighbour at a different z
useTexMap = !alwaysFlat && isTexMapValid && (PreferTexMaps || isStretched || !isLandTileValid)
texture   = useTexMap ? texmaps[TexID]  (64x64 or 128x128, Color16To32, opaque) : landart[landId] (44x44 diamond, alpha 0 outside)
fallback  = texmap 0x0001 (pink) if the chosen sprite is empty
```
Measured on Felucca (non-void, non-wet land): 31.2 % of tiles have differing corners, **38.6 % are texmapped** under CentrED's rule (7.3 % are geometrically flat but texmapped+lit because a neighbour slopes).

**Quirk (important for seafloor):** because validity is checked at index = land id, ids **0x4D–0x66** (TexID 0x4C shared; only 0x4C itself has a texmap entry) and **0x3DC1–0x3DF1, 0x3FF0** are *never* texmapped: they are always drawn with their 44x44 land art stretched over the quad, no lighting (960,501 Felucca tiles; 14.4 % of the 830,693 seafloor 0x4C–0x66 tiles are stretched). Conversely 0x2E0E/0x2E0F/0x2E1E/0x2E2A–0x2E39 have TexID 0 -> always flat art.

UVs (Epsilon = 2^-24, negligible; `bounds` = atlas rect of the sprite, normalised):
```
texmap : v0=(u0,v0)  v1=(u1,v0)  v2=(u0,v1)  v3=(u1,v1)          # full square -> 4 corners (top,right,left,bottom)
art    : v0=(um,v0)  v1=(u1,vm)  v2=(u0,vm)  v3=(um,v1)          # diamond tips of the 44x44 art; um,vm = centre
```
So for a flat tile the art maps 1:1 onto the 44x44 screen diamond; on a stretched tile the art diamond is affinely warped per triangle. `Vertex.Texture.z` = `applyLightingFlag` = 0.00001 when texmap else 0 (doubles as "apply lighting" flag and as a depth bias, see 5).

## 4. Static billboard
`StaticObject`: 8 vertices = two quads. `W,H` = full art sprite size (atlas UV rect of `art[id+0x4000]`, includes transparent margins; `RealBounds` = tight bbox, used only for lights/picking). `P = (X*T, Y*T, 4*z)`, `pw = W/sqrt2`, `hw = W/2`:
```
left half : v0=(Px-pw, Py,    Pz+H-hw)  v1=(Px, Py, Pz+H)  v2=(Px-pw, Py,    Pz-hw)  v3=(Px, Py, Pz)
right half: v4=(Px,    Py,    Pz+H)     v5=(Px, Py-pw, Pz+H-hw)  v6=(Px, Py, Pz)  v7=(Px, Py-pw, Pz-hw)
UV: left half = left 50 % of the sprite, right half = right 50 %; top row at v0/v1, bottom row at v2/v3.
Normal = 0 (unused). Indices per quad (0,1,2),(3,2,1).
```
Projected: an axis-aligned **W x H screen rectangle whose bottom-centre is the bottom tip of the tile diamond** (the z decrement of the outer vertices exactly cancels the screen-y shift of the x/y offset). Pixel (u,h) of the sprite (u = px right of centre column, -W/2..W/2; h = px above the bottom row, 0..H) has world depth key
```
Zs(u,h) = 4*z_static + h - |u|         (world px)   ->  depth = (768 - Zs)/1536 + CellIndex*0.00001
```
i.e. the billboard is folded along its centre column: the left half lies along world -x, the right half along world -y, each descending 1 px of z per px of |u|. This makes the depth plane coincide with the ground plane exactly along the edges of the static's own footprint diamond (h = |u|).

## 5. Depth test, bias, draw order, occlusion rules
* Draw order per frame: `DrawLand` (all land tiles in view, x-major then y), then `DrawStatics` (cells x-major/y, statics within a cell in **ascending PriorityZ** order), then overlays. Land/static occlusion is therefore purely the depth test. Ties (`Less` fails on equal depth) keep the earlier fragment: land beats statics, earlier static beats later.
* Depth of a fragment = `(768 - Zworld)/1536 + Vertex.Texture.z`, where `Texture.z` = 0.00001 for texmapped land (pushes it 0.01536 world px away), 0 for art land, `CellIndex*0.00001` for statics. `CellIndex` (`StaticBlock`): statics in a cell sorted by PriorityZ ascending, CellIndex = count..1 descending -> the lowest static in a cell gets the largest push-away; only matters for exact ties inside one cell. TerrainGrid technique subtracts 0.01 (not drawn by default).
* `PriorityZ = z - (Background?1:0) + (Height>0?1:0)` (`StaticTile.UpdatePriority`).
* **Static-hidden rule** (`MapManager.CanDrawStatic`, not FlatView): static not drawn if its land tile is drawable and `landTile.AverageZ() >= PriorityZ + 5`.  `AverageZ()` = `(zTop+zBottom)>>1` if `|zTop-zBottom| <= |zLeft-zRight|` else `(zLeft+zRight)>>1`, using the 4 corner z's of section 3 (for AlwaysFlat tiles all corners = own z). Arithmetic shift (floor). So a static must be at z >= AverageZ - 4 (+1 if Background, -1 if Height>0) to be visible at all.
* **Nodraw**: land ids 0,1,2 not drawn (black background shows through). Static ids listed in section 1. Land ids >= 0x4000 are drawn as id 1 when `DebugInvalidTiles`.
* Consequence for land vs static (derived from the formulas, not visually verified): at a screen pixel where a land fragment of world height Zl overlaps a static fragment with key Zs(u,h), **land wins iff 4*Zl > 4*z_s + h - |u|** (or equal). Flat ground at the same z as the static clips any opaque sprite pixel with h < |u| (pixels outside the 45° cone above the base, e.g. the lower corners of sprites wider than their footprint). Raised ground behind a static (north-west on screen) that projects over the sprite at height h beats it only if it is higher than z_s + (h - |u|)/4. Per-pixel depth for statics vs statics is the same key comparison.
* Land pass covers the whole view range ± margin; anything not covered by a drawn land tile is black.

## 6. Pixel shader (Terrain / Statics techniques)
Land art / static art texels: 16-bit 1555 -> `Color16To32` via the 5->8 table `[0,8,16,24,32,41,49,57,65,74,82,90,98,106,115,123,131,139,148,156,164,172,180,189,197,205,214,222,230,238,246,255]`; raw 16-bit value 0 = transparent (alpha 0 -> `discard`), everything else opaque. Texmaps are fully opaque. No black border post-process in this version.

### 6.1 Terrain PS
```
color = tex(uv)            ; discard if a==0
if useTexMap: color.rgb *= get_light(normal)         # ONLY texmapped tiles are lit; art tiles drawn as-is ("prebaked")
if hueMode==RGB: color.rgb += hue.rgb                 # only WalkableSurfaces/ghost overlays; off by default
```
`get_light(n)`: `L = normalize(0,1,1)`, `base = max(dot(normalize(n),L),0)/2 + 0.5`, `light = base + 0.5*(base - 0.853553) = 1.5*base - 0.4267767`. Flat normal (0,0,1) -> dot = 0.7071 -> **light = 0.853553**; range [0.323, 1.073]. (Frame-buffer clamps >1.) Normals are interpolated across the quad then normalised per pixel.
Measured consequence: lit-flat texmap vs land art luminance for the top land ids: art ≈ 0.93 (grass 0x3-0x6), 0.91-0.96 (jungle), 0.96 (forest), 0.98-0.99 (rock/cave) of `texmap*0.8536` — so a texmapped flat tile is ~1-8 % brighter than its art neighbour, which is the faint "patchwork" seen near slopes.

### 6.2 Land normals (`CalculateNormals`, default mode `ClassicUONormals=false`)
For corner k the normal is computed for "corner tile" Ck = (X,Y),(X+1,Y),(X,Y+1),(X+1,Y+1) from Ck's 4-neighbours (top=(x,y-1), right=(x+1,y), bottom=(x,y+1), left=(x-1,y); missing -> own z). If all 4 neighbours have Ck's z -> n=(0,0,1) and this corner does not force stretching. Otherwise sum of `cross(u,v)` over pairs (left,top),(top,right),(right,bottom),(bottom,left) with u,v = neighbour - tile in world px, which reduces in closed form to
```
n_k ∝ ( 4*(z_left - z_right),  4*(z_top - z_bottom),  2*TILE_SIZE=62.225 )   then normalise
```
(surfaces descending toward world +y, i.e. toward screen bottom-left, are lit; descending toward -y are dark).
ClassicUO mode (off by default): `ret = cross(v,u)` summed over the 4 pairs with u,v from the table in `LandObject.cs` lines 246-289 (offsets ±22 in x/y and `(neighbour.z - z)*4` in z), normalised; gives the same sign conventions with different weights.

### 6.3 Statics PS (hue handling, `HuesManager.GetHueVector`)
Vertex `Hue = (hueIndex, 0, alpha, mode)`; `alpha = 178/255` if tiledata `Translucent` else 1; `partial = tiledata PartialHue`. Hue value 0x8000 bit forces partial; `hue &= 0x7FFF`; if hue != 0: `hueIndex = hue-1`, mode = PARTIAL(2) if partial else HUED(1); else mode NONE(0).
```
if mode==HUED or (mode==PARTIAL and r==g==b): rgb = hues[hueIndex].table[ clamp(floor(r*32),0,31) ]   # gray = red channel, 32-entry table, point sampled
elif mode==LIGHT: rgb = light-colour LUT (only light-map pass)
elif mode==RGB: rgb += hue.rgb
if mode != RGB: color *= alpha        # all 4 channels (premultiplied) -> translucent statics blend 69.8 %
```
Hue texture: 16 hues x 32 entries per row, 1024 rows; entry = `Color16To32(hues.mul ColorTable[i])`. `ObjectBrightHighlight` only changes the alpha used while an object is hover-highlighted (2.0 -> over-bright, vs 0.5).

## 7. Software-renderer recipe (what to implement)
1. For each land tile in view (skip id<=2): build the 4 corners (sec. 3), choose texture (art vs texmap with the **id-index validity quirk**), compute per-corner normals if texmapped, rasterise triangles (top,right,left) and (bottom,left,right) with z-buffer key `Zworld` (bigger wins), per-pixel UV (texmap: bilinear-in-triangle of square corners; art: diamond tips), point sampling, discard alpha 0, multiply by `get_light` if texmapped.
2. For each static (ascending PriorityZ within cell) that passes `CanDrawStatic` (hidden rule with `AverageZ`, nodraw ids): blit the full sprite as a rectangle with bottom-centre at the tile's bottom tip minus 4*z in y; per-pixel key `4*z + h - |u|` (+ tiny cell-index bias); apply hue/partial-hue/translucency; opaque test "key > zbuffer" (strict; equal loses).
3. No global light, no shadows, black background, Zoom=1 (nearest scaling for other zooms).

## 8. Walkability
### 8.1 What CentrED computes (`MapManager.IsWalkable`) — only used for the `WalkableSurfaces` colour overlay
```
IsWalkable(land):   land not Impassable  AND  for every static s on the cell:
                    ok = (s.z + s.Height <= land.Z) or (land.Z + 16 <= s.z)
                    fail if (!ok && !s.Surface && s.Impassable)
IsWalkable(static): this static not Impassable AND for every static s on the cell (including itself):
                    top = this.z + (this.Bridge ? this.Height/2 : this.Height)
                    ok = (s.z + s.Height <= top) or (this.z + 16 <= s.z)
                    fail if (!ok && !s.Surface && s.Impassable)
```
Uses the tile's own `Z` (not the corner average), a 16-unit person height, and ignores `Surface` statics even when Impassable. Wet land is not coloured at all. Note this is CentrED's heuristic, not the server rule.

### 8.2 Server rule (RunUO 3.1 / ServUO 57 `Movement.cs`, read from source — CERTAIN)
Constants `PersonHeight=16`, `StepHeight=2`. Land ignored ids ("Ignored"): 2, 0x1DB, 0x1AE–0x1B5. `CalcHeight = Bridge ? Height/2 : Height`.
`GetAverageZ(x,y)`: corners zTop=z(x,y), zLeft=z(x,y+1), zRight=z(x+1,y), zBottom=z(x+1,y+1); `landZ=min`, `landTop=max`, `landCenter = FloorAverage(top,bottom)` if `|top-bottom| <= |left-right|` else `FloorAverage(left,right)` (floor toward -inf).
Start (`GetStartZ`, standing on land): `startZ = landZ(min corner)`, `startTop = landTop(max corner)` (or a surface static's z / z+Height if standing on one). Destination (`Check`): `stepTop = startTop + 2`, `checkTop = startZ + 16`.
* **Land destination OK iff**: land not Ignored, not Impassable (Wet+Impassable only for swimmers), `stepTop >= landZ_dest(min corner)`, and `IsOk(ourZ = landCenter_dest, ourTop = max(checkTop, ourZ+16))`: no static/item on the dest cell with flags Impassable|Surface such that `s.z + s.CalcHeight > ourZ && ourTop > s.z` (doors/fields exempt for some). Surface statics also count here as blockers, i.e. a floor/bridge tile hovering 1..15 z above the ground blocks walking on the ground.
* **Surface-static destination OK iff**: static has Surface and not Impassable (Wet for swimmers), `stepTop >= s.z + (Bridge ? 0 : Height)`, not under-cut by land (`landCheck = s.z + min(Height,2)`: rejected if `landCheck < landCenter && landCenter > ourZ && testTop > landZ`), and `IsOk(ourZ = s.z + CalcHeight, ...)`. Among several candidates the one with z closest to the mobile's current z wins.
* **Diagonals**: a diagonal step (NE/SE/SW/NW) additionally requires `Check` to succeed on **both** orthogonal side cells (`Check(left) && Check(right)`) — with the same startZ/startTop, land+statics alike. (This version: both must pass; a later ServUO variant accepts either.)
* No falling limit; moving down is always allowed.
* **Empirical consequence**: because every two 8-neighbouring tiles share at least one corner, `min(dest corners) <= max(src corners)` always holds, so **pure land-to-land steps are never z-blocked by the server** (0 blocked pairs out of 7.58 M E/S pairs and 7.50 M SE pairs on Felucca, `render-spec_03`). Land walkability on the server is entirely: land flags + statics.

### 8.3 Client-side rule (ClassicUO `Pathfinder.CalculateNewZ`, read from source — CERTAIN for CUO; the original client is believed equivalent)
The client refuses to send the step if its own check fails, so the generator must satisfy it too. With player z = `AverageZ` of the source tile (CUO `Land.AverageZ`, same formula as CentrED's `AverageZ()`; = own z for flat/Wet-TexID0/texmap-invalid tiles):
```
maxZ = max(srcAverageZ, srcEdgeAvg(dir)) + 2     # srcEdgeAvg only if the source tile is stretched: N=(top+right)>>1, E=(right+bottom)>>1, S=(left+bottom)>>1, W=(top+left)>>1, NE=right, SE=bottom, SW=left, NW=top
dest land walkable iff dest land not Impassable (ids 2, 0x1AE-0x1B5, 0x1DB ignored) and destAverageZ <= maxZ,
and (approximately; exact loop in Pathfinder.CalculateNewZ lines 440-505) no Impassable-or-Surface static with z in [destAverageZ, destAverageZ+16) (DEFAULT_BLOCK_HEIGHT=16)
surface static: walk target = s.z + (Bridge ? Height/2 : Height), must be <= maxZ, with 16 clearance above
```
Measured on Felucca passable non-wet land: uphill-blocked pairs under this rule are **0.55 % of cardinal pairs and ~1.0 % of diagonal pairs** (41–78 k of 7.5 M per direction) — these are the intentional cliff edges; `|destAvg - srcAvg| > 2` alone occurs in 3.8 % (cardinal) / 5.2 % (diagonal) of pairs, so the edge-average term matters.

### 8.4 Practical rules for the generator (combine 8.2 + 8.3)
1. Walkable terrain = land ids without `Impassable` (check tiledata; e.g. 0x1C/0x20 sand, 0x4C–0x66 seafloor, 0x244 void are Impassable; water 0xA8–0xAB, 0x136–0x137 Impassable|Wet).
2. Along any path that must be walkable, keep **`AverageZ(dest) <= max(AverageZ(src), edgeAvg(src,dir)) + 2`** in the walking direction. Simplest sufficient condition: **adjacent tile z (tile origin z) differs by <= 2** along paths, and cliffs/ramps steeper than that must be made deliberately impassable (rock/cliff ids) or bridged with Surface/Bridge statics (stairs: `Bridge` flag, CalcHeight = Height/2; each step raises the walk z by Height/2 so steps of Height<=4 chain). Uphill steps of 3–4 can be hidden behind diagonal geometry but avoid relying on it.
3. Impassable non-Surface statics (trees Height 20, walls 20, rocks, water statics 0x1796-0x17B2 Height 0 but Impassable|Wet...) block a cell when their [z, z+Height) intersects [groundZ, groundZ+16). A Height-0 Impassable static at exactly ground z does **not** block on the server (`checkTop > ourZ` fails) — the water statics at z=-5 over seafloor at -15 block only because the seafloor land is itself Impassable. Keep trees/rocks at exactly the land z so they block (they have Height 20).
4. Surface statics (floors, docks, bridges) at z in [groundCenter+1, groundCenter+15] **block the ground** beneath and become the walking surface only if their top is reachable (`<= srcTop+2`). Put floor statics at exactly the land z (or land avg z) on flat ground.
5. Diagonal moves need both flanking cells passable too: a 1-tile-wide diagonal corridor is not walkable.
6. Surface/Bridge semantics: `Surface` = can stand on (walk z = z+Height); `Bridge` = same but walk z = z+Height/2 and the "stepTop >= top" test uses z instead of z+Height (so ramps/stairs of Height up to ~4*2 are climbable from below). `Impassable` on a Surface static still blocks.
7. Rendering-driven constraints: a static at z < AverageZ(tile) - 4 (±1 by Background/Height) is invisible in CentrED (sec. 5) — place statics at z >= land z; on slopes use the corner average, not the min corner.

## 9. The static height field of `tiledata.mul`
Static record (HS format, 41 B): flags u64 @0, weight @8, layer @9, count u32 @10, animid u16 @14, hue u16 @16, lightindex u16 @18, **height @20**, name[20] @21. An earlier reader took the height from offset 36, a byte **inside the name field**, which returned 0 for trees and walls and garbage (e.g. 115 for 0xC8A) elsewhere. `uo/tiledata.py` reads offset 20: trees 0xCD0/0xCE0 = 20, stone wall 0xE8 = 20, water statics 0x1796 = 0. All static-height-based reasoning (walkability, CanDrawStatic PriorityZ `Height>0` term) depends on this field, which is why `tools/cedrender.py` re-reads it straight from the file as a cross-check.
