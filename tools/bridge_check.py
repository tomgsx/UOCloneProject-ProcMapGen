"""Bridge acceptance sweep over a generated world.

Every plank-deck cluster (static ids 0x7C9-0x7CC) must be an axis-aligned full
5-wide rectangle with the rail sequence build_bridges() lays (gen/pipeline.py),
and the road must run straight and centred for RUNUP tiles beyond each end: the
deck's full width for APRON tiles, then the 3-wide walkway. Prints every
violation with the deck's corner tile and exits 1 when there is one.

Usage: python3 tools/bridge_check.py <world_dir>
"""
import os, sys
import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from uo.map import load_mul
from gen import materials as M
from gen.roads import RUNUP, APRON

root = sys.argv[1]
lid, lz, st = load_mul(f"{root}/map0.mul", f"{root}/staidx0.mul", f"{root}/statics0.mul")
state = np.load(f"{root}/gen_state.npz")
material, wet = state["material"], state["wet"]
W, H = wet.shape

deck = np.zeros((W, H), bool)
m = np.isin(st["id"], [0x7C9, 0x7CA, 0x7CB, 0x7CC])
deck[st["x"][m], st["y"][m]] = True
lab, n = ndi.label(deck, np.ones((3, 3)))
road = material == M.ROAD

bad = []
for k in range(1, n + 1):
    xs, ys = np.nonzero(lab == k)
    w, h = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    ew = w >= h                      # long axis east-west
    if min(w, h) > 5:
        bad.append((int(xs.min()), int(ys.min()), "crooked deck (bbox %dx%d)" % (w, h)))
        continue
    # the deck is a full 5-wide plank rectangle bank to bank
    if min(w, h) != 5 or not deck[xs.min():xs.max() + 1, ys.min():ys.max() + 1].all():
        bad.append((int(xs.min()), int(ys.min()), "deck is not a full 5-wide rectangle (bbox %dx%d)" % (w, h)))
        continue
    # rails along both outer lines: a post-and-rail on the first tile and evenly ~4 apart,
    # plain rail between, the family's corner post last (the first post at low x/y)
    POST, RAIL, CORNER = (0x8F9, 0x8FB, 0x8F7) if ew else (0x8FA, 0x8FC, 0x8F8)
    L = w if ew else h
    nseg = max(1, int(round((L - 1) / 4.0)))
    posts = {int(round(k * (L - 1) / nseg)) for k in range(nseg)}
    want = [CORNER if i == L - 1 else (POST if i in posts else RAIL) for i in range(L)]
    rail_at = {(int(r["x"]), int(r["y"])): int(r["id"]) for r in st
               if int(r["id"]) in (0x8F7, 0x8F8, 0x8F9, 0x8FA, 0x8FB, 0x8FC)}
    rail_ok = True
    for side in (-2, 2):
        if ew:
            cy = int(np.median(ys)); got = [rail_at.get((xs.min() + i, cy + side)) for i in range(L)]
        else:
            cx = int(np.median(xs)); got = [rail_at.get((cx + side, ys.min() + i)) for i in range(L)]
        if got != want:
            rail_ok = False
    if not rail_ok:
        bad.append((int(xs.min()), int(ys.min()), "rail sequence differs from the reference layout"))
        continue
    # run-ups: RUNUP straight road tiles beyond each end, on the centre line
    if ew:
        cy = int(np.median(ys)); x0, x1 = int(xs.min()), int(xs.max())
        ends = [[(x0 - d, cy) for d in range(1, RUNUP + 1)], [(x1 + d, cy) for d in range(1, RUNUP + 1)]]
    else:
        cx = int(np.median(xs)); y0, y1 = int(ys.min()), int(ys.max())
        ends = [[(cx, y0 - d) for d in range(1, RUNUP + 1)], [(cx, y1 + d) for d in range(1, RUNUP + 1)]]
    for tiles in ends:
        if not all(0 <= x < W and 0 <= y < H and road[x, y] for x, y in tiles):
            bad.append((int(xs.min()), int(ys.min()), "run-up not straight road at " + str(tiles[0])))
            break
        # the road meets the deck at its full 5-tile width for APRON tiles, then is exactly the
        # walkway's 3 tiles wide, centred on the deck
        for k, (x, y) in enumerate(tiles):
            if ew:
                band = road[x, y - 3:y + 4]
            else:
                band = road[x - 3:x + 4, y]
            want = 5 if k < APRON else 3
            lo, hi = 3 - want // 2, 4 + want // 2
            if band.sum() != want or not band[lo:hi].all():
                bad.append((int(xs.min()), int(ys.min()), "run-up road not %d wide/centred at %s" % (want, str((x, y)))))
                break

print(f"bridges: {n}, violations: {len(bad)}")
for b in bad[:40]:
    print("  <%d,%d> %s" % b)
sys.exit(1 if bad else 0)
