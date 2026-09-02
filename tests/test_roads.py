"""Roads and bridges: straight crossings, decks, aprons and approaches.

The scenes are small synthetic worlds (a vertical river band across a dry
field) and diagonal roads, which is the geometry that produces every bad
bridge: a road meeting a river at an angle becomes a ladder of offset planks
unless the crossing is straightened first (gen/roads.py).
"""
import unittest

import numpy as np

from gen.roads import RUNUP, APRON, AHEAD_MIN, _best_crossing, straighten_crossings, plan_decks, deck_apron
from gen.pipeline import build_bridges


def river_scene(n=80, x0=36, width=4):
    """Dry field with a vertical river band wet[x0:x0+width, :]."""
    wet = np.zeros((n, n), bool)
    wet[x0:x0 + width, :] = True
    return wet


def diagonal_path(a, b):
    """8-connected raster of the straight line a-b (what a wandered road looks like at a river)."""
    n = max(abs(b[0] - a[0]), abs(b[1] - a[1])) + 1
    xs = np.round(np.linspace(a[0], b[0], n)).astype(int)
    ys = np.round(np.linspace(a[1], b[1], n)).astype(int)
    return [(int(x), int(y)) for x, y in zip(xs, ys)]


def wet_runs(path, wet):
    """The maximal stretches of `path` over water, in order."""
    runs, i = [], 0
    while i < len(path):
        if wet[path[i]]:
            j = i
            while j < len(path) and wet[path[j]]:
                j += 1
            runs.append(path[i:j])
            i = j
        else:
            i += 1
    return runs


class StraightCrossingTests(unittest.TestCase):
    def test_diagonal_road_gets_one_straight_crossing_with_runups(self):
        # A road hitting the river at 45 degrees must become one axis-aligned crossing
        # with RUNUP straight land tiles on both banks.
        wet = river_scene()
        raw = diagonal_path((10, 10), (70, 70))
        path, ok = straighten_crossings(raw, wet)
        self.assertTrue(ok)
        runs = wet_runs(path, wet)
        self.assertEqual(len(runs), 1)
        run = runs[0]
        ys = {y for _, y in run}
        self.assertEqual(len(ys), 1, "crossing must be a single row")
        y = ys.pop()
        i = path.index(run[0]); j = path.index(run[-1])
        before = path[i - RUNUP:i]
        after = path[j + 1:j + 1 + RUNUP]
        self.assertEqual(len(before), RUNUP); self.assertEqual(len(after), RUNUP)
        for (x, yy) in before + after:
            self.assertEqual(yy, y, "run-up must be colinear with the crossing")
            self.assertFalse(wet[x, yy])
        xs = [x for x, _ in before + run + after]
        self.assertEqual(xs, list(range(xs[0], xs[0] + len(xs))), "run-up + crossing must be consecutive")
        # the road still starts and ends where it was
        self.assertEqual(path[0], raw[0]); self.assertEqual(path[-1], raw[-1])

    def test_runups_avoid_blocked_ground(self):
        # rock right against the bank on one row pushes the crossing to another row
        wet = river_scene()
        rock = np.zeros_like(wet)
        rock[30:36, 38:42] = True          # rock on the near bank around the midpoint row
        raw = diagonal_path((10, 10), (70, 70))
        path, ok = straighten_crossings(raw, wet, blocked=rock)
        self.assertTrue(ok)
        for (x, y) in path:
            self.assertFalse(rock[x, y], f"road on rock at {(x, y)}")

    def test_uncrossable_water_is_reported_not_bridged(self):
        wet = river_scene(n=120, x0=20, width=70)   # wider than max_len at every row
        raw = diagonal_path((5, 5), (115, 115))
        path, ok = straighten_crossings(raw, wet)
        self.assertFalse(ok)
        self.assertIsNone(_best_crossing(wet, (10, 10), (110, 110)))

    def test_bridge_builder_refuses_crooked_runs(self):
        wet = river_scene()
        raw = diagonal_path((10, 10), (70, 70))
        zi = np.zeros(wet.shape, np.int16)
        core = np.zeros(wet.shape, bool)
        st, tiles, crooked = build_bridges([raw], core, wet, zi, np.random.default_rng(1))
        self.assertEqual(crooked, 1)
        self.assertEqual(len(st), 0)
        path, ok = straighten_crossings(raw, wet)
        st, tiles, crooked = build_bridges([path], core, wet, zi, np.random.default_rng(1))
        self.assertEqual(crooked, 0)
        self.assertGreater(len(st), 0)
        # An east-west bridge: a full 5-wide plank rectangle over every column bank to
        # bank, rails at deck z + 1 on both outer rows reading, along +x, 8F9 (first
        # tile), 8FB..., 8F9 every 4th tile, and the 8F7 corner post on the last.
        deck = st[np.isin(st["id"], [0x7C9, 0x7CA, 0x7CB, 0x7CC])]
        run = wet_runs(path, wet)[0]
        y = run[0][1]
        planks = {(int(r["x"]), int(r["y"])) for r in deck}
        x0 = min(x for x, _ in planks); x1 = max(x for x, _ in planks)   # deck extent, shore cleared
        self.assertLess(x0, run[0][0] - 1); self.assertGreater(x1, run[-1][0] + 1)
        for x in range(x0, x1 + 1):
            for o in range(-2, 3):
                self.assertIn((x, y + o), planks, f"missing plank at {(x, y + o)}")
        rails = {(int(r["x"]), int(r["y"])): (int(r["id"]), int(r["z"])) for r in st
                 if int(r["id"]) in (0x8F7, 0x8F9, 0x8FB)}
        L = x1 - x0 + 1
        expect = [0x8FB] * L
        expect[-1] = 0x8F7
        # post-and-rail pieces spread evenly by length, ~4 tiles apart, the first on tile 0
        # (a 9-long deck reads start, middle, end)
        nseg = max(1, int(round((L - 1) / 4.0)))
        for k in range(nseg):
            expect[int(round(k * (L - 1) / nseg))] = 0x8F9
        deck_z = int(deck["z"][0])
        for o in (-2, 2):
            got = [rails.get((x, y + o), (None, None)) for x in range(x0, x1 + 1)]
            self.assertEqual([g[0] for g in got], expect, f"rail sequence on row {y + o}")
            self.assertTrue(all(g[1] == deck_z + 1 for g in got), "rails sit at deck z + 1")
        # the inner three rows carry planks only
        inner = {(int(r["x"]), int(r["y"])) for r in st if int(r["id"]) in (0x8F7, 0x8F8, 0x8F9, 0x8FA, 0x8FB, 0x8FC)}
        for x in range(x0, x1 + 1):
            for o in (-1, 0, 1):
                self.assertNotIn((x, y + o), inner)

    def test_deck_grows_until_its_full_width_is_on_land(self):
        # A jagged bank: the crossing row reaches land one tile before its two flank rows
        # do, which would leave holes at both deck ends. The deck must extend along the
        # straight corridor until all five tiles across each end are dry.
        raw = diagonal_path((10, 10), (70, 70))
        plain = river_scene(n=80, x0=36, width=4)
        y = wet_runs(straighten_crossings(raw, plain)[0], plain)[0][0][1]   # the crossing row
        wet = plain.copy()
        for yy in (y - 2, y - 1, y + 1, y + 2):   # bank column x=35 wet on the flank rows only
            wet[35, yy] = True
        path, ok = straighten_crossings(raw, wet)
        self.assertTrue(ok)
        run = wet_runs(path, wet)[0]
        self.assertEqual(run[0][1], y, "the notch must not move the crossing row")
        zi = np.zeros(wet.shape, np.int16)
        st, tiles, crooked = build_bridges([path], np.zeros(wet.shape, bool), wet, zi, np.random.default_rng(1))
        self.assertEqual(crooked, 0)
        deck = st[np.isin(st["id"], [0x7C9, 0x7CA, 0x7CB, 0x7CC])]
        xs = sorted({int(x) for x in deck["x"]})
        x0, x1 = xs[0], xs[-1]
        # the notched bank column 35 is shore, so is 34 (it touches the notch): the deck ends at 33
        self.assertEqual(x0, 33, "west end grows past the notched bank and its shore tile")
        self.assertEqual(x1, 41, "east end clears the bank tile touching the water")
        from gen.roads import shore_mask
        shore = shore_mask(wet)
        for x in (x0, x1):
            for o in range(-2, 3):
                self.assertFalse(shore[x, y + o], f"deck end {(x, y + o)} still on the shore")
        posts = {(int(r["x"]), int(r["y"])): int(r["id"]) for r in st if int(r["id"]) in (0x8F7, 0x8F9, 0x8FB)}
        self.assertEqual(posts[(x0, y - 2)], 0x8F9)
        self.assertEqual(posts[(x1, y + 2)], 0x8F7)
        # the straight run-up still lies beyond the extended end
        i = path.index((x0, y))
        self.assertTrue(all(p[1] == y for p in path[i - RUNUP:i]))

    def test_road_meets_the_deck_at_full_width(self):
        # For APRON tiles beyond each deck end the road is the deck's full 5-tile width
        # (edges on the post columns), then the 3-wide run-up.
        wet = river_scene()
        path, ok = straighten_crossings(diagonal_path((10, 10), (70, 70)), wet)
        decks, crooked = plan_decks([path], wet)
        self.assertEqual((len(decks), crooked), (1, 0))
        (seg, ew) = decks[0]
        self.assertTrue(ew)
        apron = deck_apron(decks, wet.shape)
        (x0, y), (x1, _) = seg[0], seg[-1]
        for k in range(1, APRON + 1):
            for o in range(-2, 3):
                self.assertTrue(apron[x0 - k, y + o]); self.assertTrue(apron[x1 + k, y + o])
            self.assertFalse(apron[x0 - k, y - 3]); self.assertFalse(apron[x1 + k, y + 3])
        self.assertFalse(apron[x0 - APRON - 1, y]); self.assertFalse(apron[x1 + APRON + 1, y])
        self.assertFalse(apron[x0, y], "the deck itself is not apron")

    def test_approach_flows_into_the_corridor_head_on(self):
        # A road that reached the river obliquely must not double back in a V to the
        # corridor start: the anchor is walked along the original road until it is ahead
        # of the corridor end, so every approach tile lies outward of that end.
        wet = river_scene(n=90, x0=44, width=4)
        raw = diagonal_path((5, 60), (85, 20))      # comes from the south-west, heading north-east
        path, ok = straighten_crossings(raw, wet)
        self.assertTrue(ok)
        (seg, ew) = plan_decks([path], wet)[0][0]
        i0 = path.index(seg[0]); i1 = path.index(seg[-1])
        c0 = i0 - (RUNUP + 2); c1 = i1 + (RUNUP + 2)          # corridor ends
        s0, s1 = path[c0], path[c1]
        for p in path[:c0]:
            self.assertLessEqual(p[0], s0[0], f"approach tile {p} lies behind the west corridor end {s0}")
        for p in path[c1 + 1:]:
            self.assertGreaterEqual(p[0], s1[0], f"approach tile {p} lies behind the east corridor end {s1}")

    def test_approach_anchors_back_off_the_water(self):
        # The centreline must not keep the old diagonal approach up to the bank and then
        # double back to the run-up: no tile of the final path other than the crossing's
        # own run-up may touch the water.
        wet = river_scene()
        raw = diagonal_path((10, 10), (70, 70))
        path, ok = straighten_crossings(raw, wet)
        self.assertTrue(ok)
        run = wet_runs(path, wet)[0]
        i = path.index(run[0]); j = path.index(run[-1])
        corridor = set(path[i - RUNUP:j + 1 + RUNUP])
        near = np.zeros_like(wet)
        near[wet] = True
        from scipy import ndimage as ndi
        near = ndi.binary_dilation(near, np.ones((3, 3)))
        for p in path:
            if p not in corridor:
                self.assertFalse(near[p], f"approach tile {p} touches the water outside the run-up")
