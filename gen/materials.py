"""Material codes used throughout the generator, and their names in the learned transition tables.

A material is what a tile is made of before it gets a concrete land id: the
generator's stages pass around uint8 arrays of these codes, and gen/tiles.py
turns them into ids at the end. LAKE is water that gets the same treatment as
WATER; ROAD and DIRT are the same dark dirt art, ROAD for the road surface and
DIRT for town plazas; SWAMP_RIM is the lighter ring around a swamp's dark core.
"""
WATER, GRASS, FOREST, JUNGLE, SAND, SNOW, SWAMP, ROCK, DIRT, ROAD, LAKE, COBBLE, SWAMP_RIM = range(13)
NAMES = {WATER: "water", GRASS: "grass", FOREST: "forest", JUNGLE: "jungle", SAND: "sand", SNOW: "snow",
         SWAMP: "swamp", ROCK: "rock", DIRT: "dirt", ROAD: "dirt_dark", LAKE: "water", COBBLE: "cobble", SWAMP_RIM: "swamp_rim"}
CODES = {v: k for k, v in NAMES.items() if k not in (LAKE, SWAMP_RIM)}
# fallback pure ids if the learned variant table lacks a material
PURE_FALLBACK = {GRASS: [3, 4, 5, 6], FOREST: [0xC4, 0xC5, 0xC6, 0xC7], JUNGLE: [0xAC, 0xAD, 0xAE, 0xAF],
                 SAND: [0x16, 0x17, 0x18, 0x19], SNOW: [0x11A, 0x11B, 0x11C, 0x11D], SWAMP: [0x3DE9, 0x3DEA, 0x3DEB, 0x3DEC],
                 ROCK: [0x22C, 0x22D, 0x22E, 0x22F], DIRT: [0x75, 0x76, 0x77, 0x78], ROAD: [0x3FF8, 0x3FF9, 0x3FFA, 0x3FFB],
                 COBBLE: [0x3E9, 0x3EA, 0x3EB, 0x3EC], SWAMP_RIM: [0x3DED, 0x3DEE, 0x3DEF, 0x3DF0], WATER: [0xA8, 0xA9, 0xAA, 0xAB], LAKE: [0xA8, 0xA9, 0xAA, 0xAB]}
