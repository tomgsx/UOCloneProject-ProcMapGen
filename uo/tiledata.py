"""tiledata.mul parser: the flags, names and sizes of every land and static id.

The file has the post-High-Seas layout with 64-bit flags: 512 groups of 32 land
records (4-byte group header, then per record flags u64, TexID u16, name
char[20]), followed by groups of 32 static records (4-byte header, then per
record flags u64, weight u8, layer u8, count u32, animation id u16, hue u16,
light index u16, height u8, name char[20]).

The client folder comes from the UO_CLIENT_DIR environment variable; the app
sets it from the folder the user selects before it starts the generator.
"""
import os, struct, numpy as np

UO = os.environ.get("UO_CLIENT_DIR", "")
LAND_TOTAL = 512 * (4 + 32 * 30)

class TileFlag:
    """The tiledata flag bits shared by land and static records."""
    Background=1<<0; Weapon=1<<1; Transparent=1<<2; Translucent=1<<3; Wall=1<<4
    Damaging=1<<5; Impassable=1<<6; Wet=1<<7; Unknown1=1<<8; Surface=1<<9
    Bridge=1<<10; Generic=1<<11; Window=1<<12; NoShoot=1<<13; ArticleA=1<<14
    ArticleAn=1<<15; Internal=1<<16; Foliage=1<<17; PartialHue=1<<18; NoHouse=1<<19
    Map=1<<20; Container=1<<21; Wearable=1<<22; LightSource=1<<23; Animation=1<<24
    HoverOver=1<<25; NoDiagonal=1<<26; Armor=1<<27; Roof=1<<28; Door=1<<29
    StairBack=1<<30; StairRight=1<<31
    @classmethod
    def names(cls, f):
        """The set flags of `f` as 'A|B|C', or '-' when none is set."""
        return "|".join(k for k, v in vars(cls).items() if isinstance(v, int) and f & v) or "-"

class TileData:
    """The parsed file: land_flags/land_texid/land_names indexed by land id (16384
    entries) and static_flags/static_height/static_weight/static_names indexed by
    static id (n_static entries)."""
    def __init__(self, path=f"{UO}/tiledata.mul"):
        if not UO and path == "/tiledata.mul":
            raise FileNotFoundError(
                "UO client data is not configured. Select a folder containing tiledata.mul."
            )
        with open(path, "rb") as f:
            d = f.read()
        self.land_flags = np.zeros(16384, np.uint64)
        self.land_texid = np.zeros(16384, np.uint16)
        self.land_names = []
        off = 0
        for g in range(512):
            off += 4
            for i in range(32):
                fl, tex = struct.unpack_from("<QH", d, off)
                self.land_flags[g*32+i] = fl; self.land_texid[g*32+i] = tex
                self.land_names.append(d[off+10:off+30].split(b"\0")[0].decode("ascii", "replace"))
                off += 30
        n = (len(d) - LAND_TOTAL) // (4 + 32*41)
        self.static_flags = np.zeros(n*32, np.uint64)
        self.static_height = np.zeros(n*32, np.uint8)
        self.static_weight = np.zeros(n*32, np.uint8)
        self.static_names = []
        off = LAND_TOTAL
        for g in range(n):
            off += 4
            for i in range(32):
                fl, = struct.unpack_from("<Q", d, off)
                self.static_flags[g*32+i] = fl
                self.static_weight[g*32+i] = d[off+8]
                self.static_height[g*32+i] = d[off+20]
                self.static_names.append(d[off+21:off+41].split(b"\0")[0].decode("ascii", "replace"))
                off += 41
        self.n_static = n*32

    def land_has(self, ids, flag): return (self.land_flags[ids] & np.uint64(flag)) != 0
    def static_has(self, ids, flag): return (self.static_flags[ids] & np.uint64(flag)) != 0
