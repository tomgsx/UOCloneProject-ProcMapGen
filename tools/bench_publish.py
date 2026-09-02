"""Re-encode the six shoreline bench scenes and render them for review.

The bench scenes are small (19 x 19) wet masks in docs/island-tests/*.npz: a
square island, a diamond, a staircase, a plus, a notch and a blob. Each
exercises a different set of corner patterns of the shoreline rules in
gen/water.py. This tool runs encode_water on every mask with a fixed seed,
stores the resulting land ids, z and statics back into the .npz, renders each
scene with tools/cedrender.py and pastes the six renders into one montage,
docs/island-tests/all-islands.png.

The renders need the UO client's art, so set UO_CLIENT_DIR before running:

    UO_CLIENT_DIR="/path/to/client" python3 tools/bench_publish.py

The PNGs are derived from the client's copyrighted art and are therefore not
tracked in the repository (see .gitignore); regenerate them locally when you
want to eyeball a change to the water rules.
"""
import os, sys, tempfile
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gen.water import encode_water
from gen import materials as M
from tools.cedrender import render
from PIL import Image, ImageDraw

BASE = os.path.join(ROOT, "docs", "island-tests")
NAMES = ("square", "diamond", "staircase2", "plus", "notch", "blob")
CELL = 1040          # side of one montage cell in pixels

def build(wet):
    """Run the water rules on a wet mask over flat grass. Returns (land ids, z, statics)."""
    mat = np.full(wet.shape, M.GRASS, np.uint8)
    mat[wet] = M.WATER
    lid = np.full(wet.shape, 0x3, np.uint16)
    z = np.zeros(wet.shape, np.int16)
    st = encode_water(wet, z, lid, np.random.default_rng(42), mat)
    return lid, z, st

def to_cell(path):
    """Centre a raw render (932 x 1176) on a black CELL x CELL square."""
    img = Image.open(path)
    w, h = img.size
    canvas = Image.new("RGB", (CELL, CELL), (0, 0, 0))
    left = (CELL - w) // 2
    top = -(h - CELL) // 2 if h > CELL else (CELL - h) // 2
    canvas.paste(img, (left, top))
    return canvas

cells = {}
for name in NAMES:
    d = np.load(f"{BASE}/{name}.npz")
    wet = d["wet"].copy()
    lid, z, st = build(wet)
    np.savez(f"{BASE}/{name}.npz", wet=wet, z=z, lid=lid,
             st_x=st["x"], st_y=st["y"], st_id=st["id"], st_z=st["z"])
    raw = os.path.join(tempfile.gettempdir(), f"raw-{name}.png")
    sts = [(int(a), int(b), int(i), int(zz)) for a, b, i, zz in
           zip(st["x"], st["y"], st["id"], st["z"])]
    # the renderer reads one row and column past the window for corner heights
    lid_p = np.pad(lid, ((0, 2), (0, 2)), mode="edge")
    z_p = np.pad(z, ((0, 2), (0, 2)), mode="edge")
    render(lid_p, z_p, sts, wet.shape[0], wet.shape[1], raw)
    cell = to_cell(raw)
    cell.save(f"{BASE}/{name}.png")
    cells[name] = cell
    print(name, "written")

GAP = 36
mont = Image.new("RGB", (3 * CELL + 2 * GAP, 2 * CELL + GAP + 106), (16, 16, 16))
draw = ImageDraw.Draw(mont)
for i, name in enumerate(NAMES):
    cx = (i % 3) * (CELL + GAP)
    cy = (i // 3) * (CELL + GAP + 35) + 35
    mont.paste(cells[name], (cx, cy))
    draw.text((cx + 8, cy - 28), name, fill=(230, 210, 60))
mont.save(f"{BASE}/all-islands.png")
print("montage written")
