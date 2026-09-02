"""Write a Felucca-sized test world that is all ocean except the six bench islands.

Usage:
    python3 tools/island_test_map.py <output_dir>

The bench islands (docs/island-tests/*.npz, 19 x 19 wet masks) are stamped 40
tiles apart along y = 2048, starting at x = 2000, and encoded with the current
shoreline rules. Load the resulting map0.mul / staidx0.mul / statics0.mul in
CentrED or a client to inspect each island's coast in the real renderer.
"""
import os, sys
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gen.water import encode_water, check_water
from gen import materials as M
from uo.map import write_map_mul, write_statics

if len(sys.argv) != 2:
    sys.exit(__doc__)
OUT = sys.argv[1]
BASE = os.path.join(ROOT, "docs", "island-tests")
NAMES = ("square", "diamond", "staircase2", "plus", "notch", "blob")
W_, H_ = 7168, 4096

wet = np.ones((W_, H_), bool)
for i, name in enumerate(NAMES):
    d = np.load(f"{BASE}/{name}.npz")
    scene_wet = d["wet"]          # 19 x 19, island centred at (9, 9)
    cx, cy = 2000 + 40 * i, 2048
    x0, y0 = cx - 9, cy - 9
    wet[x0:x0 + 19, y0:y0 + 19] &= scene_wet

mat = np.full((W_, H_), M.GRASS, np.uint8)
mat[wet] = M.WATER
lid = np.full((W_, H_), 0x3, np.uint16)
z = np.zeros((W_, H_), np.int16)
st = encode_water(wet, z, lid, np.random.default_rng(42), mat)
chk = check_water(wet, z, lid, st)
print("check:", chk)
assert chk["sunk_without_static"] == 0 and chk.get("notch_shapes", 0) == 0

os.makedirs(OUT, exist_ok=True)
write_map_mul(f"{OUT}/map0.mul", lid, z)
write_statics(f"{OUT}/staidx0.mul", f"{OUT}/statics0.mul", st)
print("island test map written")
