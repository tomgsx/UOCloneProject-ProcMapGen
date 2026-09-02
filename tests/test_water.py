"""The shoreline rules (gen/water.py) on small synthetic scenes.

Each scene is a tiny wet mask over one beach material; encode_water runs on it
and the tests read back the land id, z and statics of one tile. The scene
helpers build a specific corner pattern or wet context at the centre tile.
"""
import os
import unittest

import numpy as np

from gen import materials as M
from gen.water import (
    DRY_OVERLAY_RULES,
    FAM_DIRT,
    FAM_GRASS,
    FAM_SAND,
    FAM_SNOW,
    INVISIBLE_BLOCKER,
    OBJW,
    SNOW_BLOCK_PATTERNS,
    check_water,
    encode_water,
    fix_tips,
    remove_wet_tips,
)
from uo.tiledata import TileData, TileFlag


def tiledata():
    """The client's tiledata.mul, from the UO_CLIENT_DIR environment variable.

    Only one test needs it (it checks the Impassable flag of the chosen shore
    ids); that test is skipped when no client install is configured, so the
    suite runs on a machine without Ultima Online.
    """
    client_dir = os.environ.get("UO_CLIENT_DIR", "")
    path = os.path.join(client_dir, "tiledata.mul")
    if client_dir and os.path.exists(path):
        return TileData(path)
    raise unittest.SkipTest("UO tiledata.mul is not available (set UO_CLIENT_DIR)")


def corner_pattern(wet):
    """The 4-bit corner pattern of every tile (own=1, E=2, S=4, D=8)."""
    out = wet.astype(np.uint8)
    out[:-1, :] |= wet[1:, :].astype(np.uint8) << 1
    out[:, :-1] |= wet[:, 1:].astype(np.uint8) << 2
    out[:-1, :-1] |= wet[1:, 1:].astype(np.uint8) << 3
    return out


def scene_for_pattern(pattern, material):
    """A 9 x 9 scene of `material` whose centre tile (4, 4) has the given corner pattern.
    Returns (wet, land ids, z, statics, centre position) after encode_water."""
    wet = np.zeros((9, 9), bool)
    x = y = 4
    for bit, (dx, dy) in {1: (0, 0), 2: (1, 0), 4: (0, 1), 8: (1, 1)}.items():
        if pattern & bit:
            wet[x + dx, y + dy] = True
    mat = np.full(wet.shape, material, np.uint8)
    mat[wet] = M.WATER
    pure = {M.SAND: 0x16, M.SNOW: 0x11A, M.DIRT: 0x75}.get(material, 0x03)
    lid = np.full(wet.shape, pure, np.uint16)
    z = np.zeros(wet.shape, np.int16)
    st = encode_water(wet, z, lid, np.random.default_rng(1000 + pattern), mat)
    return wet, lid, z, st, (x, y)


class CoastFamilyTests(unittest.TestCase):
    def test_sand_cliffs_use_matching_sand_topped_family(self):
        for pattern in range(1, 15):
            grass_ids, grass_probs = FAM_GRASS[pattern]
            sand_ids, sand_probs = FAM_SAND[pattern]
            self.assertEqual(sand_ids, [int(i) + 0x19F for i in grass_ids])
            self.assertEqual(sand_probs, grass_probs)

    def test_every_mixed_pattern_uses_its_oriented_family(self):
        td = tiledata()
        families = (
            (M.GRASS, FAM_GRASS),
            (M.SAND, FAM_SAND),
            (M.SNOW, FAM_SNOW),
            (M.DIRT, FAM_DIRT),
        )
        for material, family in families:
            for pattern in range(1, 15):
                with self.subTest(material=material, pattern=pattern):
                    wet, lid, _, st, pos = scene_for_pattern(pattern, material)
                    self.assertEqual(int(corner_pattern(wet)[pos]), pattern)
                    expected = family[pattern][0]
                    actual = int(lid[pos])
                    self.assertIn(actual, expected)
                    impassable = bool(int(td.land_flags[actual]) & TileFlag.Impassable)
                    if material == M.SNOW and pattern in SNOW_BLOCK_PATTERNS:
                        blockers = [
                            int(r["id"]) for r in st
                            if (int(r["x"]), int(r["y"])) == pos
                        ]
                        self.assertIn(INVISIBLE_BLOCKER, blockers)
                    else:
                        self.assertTrue(impassable, f"mixed coast id 0x{actual:X} is walkable")

    def test_pure_ids_never_fill_mixed_dropoffs(self):
        pure = {
            M.SAND: set(range(0x16, 0x1A)),
            M.SNOW: set(range(0x11A, 0x11E)),
            M.DIRT: set(range(0x75, 0x79)),
        }
        for material, forbidden in pure.items():
            for pattern in range(1, 15):
                _, lid, _, _, pos = scene_for_pattern(pattern, material)
                self.assertNotIn(int(lid[pos]), forbidden)


class FoamRuleTests(unittest.TestCase):
    @staticmethod
    def _static_ids(st):
        return {(int(r["x"]), int(r["y"])): int(r["id"]) for r in st}

    def test_directional_ring_foam_faces_land(self):
        n = 19
        for name, wet, pos, expected_land, expected_static in (
            (
                "land west",
                np.indices((n, n))[0] >= n // 2,
                (n // 2, n // 2),
                {0x53, 0x4F},
                {0x17A3, 0x17A4},
            ),
            (
                "land north",
                np.indices((n, n))[1] >= n // 2,
                (n // 2, n // 2),
                {0x50, 0x4D},
                {0x179F, 0x17A0},
            ),
        ):
            with self.subTest(name=name):
                mat = np.full((n, n), M.SAND, np.uint8)
                mat[wet] = M.WATER
                lid = np.full((n, n), 0x16, np.uint16)
                z = np.zeros((n, n), np.int16)
                st = encode_water(wet, z, lid, np.random.default_rng(7), mat)
                sid = self._static_ids(st)
                self.assertIn(int(lid[pos]), expected_land)
                self.assertIn(sid[pos], expected_static)

    def test_dry_side_foam_is_gated_by_full_wet_context(self):
        # Superset matching: each pattern has one required-bits context per
        # family, and the wet mask must contain all of them. The west family is
        # 17B2 only.
        N, R, E, S, L, W = 1, 2, 4, 16, 32, 64
        expected = {
            2: {N | R | E: {0x17A8, 0x17B0}},
            4: {S | L | W: {0x17B2}},
            10: {N | R | E: {0x17A8, 0x17B0}},
            12: {S | L | W: {0x17B2}},
            6: {N | R | E: {0x17A8, 0x17B0}, S | L | W: {0x17B2}},
            14: {N | R | E: {0x17A8, 0x17B0}, S | L | W: {0x17B2}},
        }
        self.assertEqual(set(DRY_OVERLAY_RULES), set(expected))
        for pattern, contexts in expected.items():
            self.assertEqual(set(DRY_OVERLAY_RULES[pattern]), set(contexts))
            for req, static_ids in contexts.items():
                ids, probs, chance = DRY_OVERLAY_RULES[pattern][req]
                self.assertEqual(set(ids), static_ids)
                self.assertEqual(chance, 1.0)
        # The historic floating-wedge contexts lack one of the required
        # cardinal bits, so superset matching still never fires on them.
        for pattern, wm in ((10, 0x0E), (4, 0x30), (12, 0x38), (2, 0x06)):
            for req in DRY_OVERLAY_RULES[pattern]:
                self.assertNotEqual(wm & req, req, (pattern, wm))

    def test_straight_mixed_edges_use_object_water(self):
        object_water = {int(i) for i in OBJW}
        for pattern in (3, 5):
            _, lid, z, st, pos = scene_for_pattern(pattern, M.GRASS)
            self.assertIn(int(lid[pos]), FAM_GRASS[pattern][0])
            self.assertEqual(int(z[pos]), -15)
            ids = {
                int(r["id"]) for r in st
                if (int(r["x"]), int(r["y"])) == pos
            }
            self.assertEqual(len(ids), 1)
            self.assertTrue(ids.issubset(object_water))

    def test_opposite_facing_mixed_corners_follow_wet_context(self):
        # (pattern, wet-neighbour mask, primary static ids, required curl on top)
        # Exact straight contexts get Felucca's straight strips; staircase runs
        # get the FULL arc pieces 17A9/17AB (Felucca's own answer - full water
        # diamonds with foam baked in, so nothing shows through); everything
        # else is plain object water.
        object_water = {int(i) for i in OBJW}
        cases = (
            (11, 0x8F, {0x17AB}, set()),              # staircase run: the arc alone, no curls
            (11, 0x0F, {0x17A3, 0x17A4}, set()),
            (11, 0xCF, object_water, set()),          # foot class stays plain
            (13, 0xF8, {0x17A9}, set()),              # staircase run: the arc alone, no curls
            (13, 0x78, {0x179F, 0x17A0}, set()),
            (13, 0xF9, object_water, set()),
            (3, 0x87, {0x17AB}, set()),
            (3, 0x07, {0x17A3, 0x17A4}, set()),
            (3, 0x27, object_water, set()),
            (5, 0xF0, {0x17A9}, set()),
            (5, 0x70, {0x179F, 0x17A0}, set()),
            (5, 0x72, object_water, set()),
            (5, 0xF1, object_water, set()),   # straight vertical shoreline stays bare-of-foam
        )
        offsets = (
            (1, 0, 0x04), (1, 1, 0x08), (0, 1, 0x10),
            (-1, 1, 0x20), (-1, 0, 0x40), (-1, -1, 0x80),
            (0, -1, 0x01), (1, -1, 0x02),
        )
        for pattern, wet_mask, expected, curls in cases:
            n = 9
            pos = (n // 2, n // 2)
            wet = np.zeros((n, n), bool)
            wet[pos] = True
            for dx, dy, bit in offsets:
                if wet_mask & bit:
                    wet[pos[0] + dx, pos[1] + dy] = True
            mat = np.full((n, n), M.GRASS, np.uint8)
            mat[wet] = M.WATER
            lid = np.full((n, n), 0x03, np.uint16)
            z = np.zeros((n, n), np.int16)
            st = encode_water(
                wet, z, lid, np.random.default_rng(1000 + wet_mask), mat
            )
            ids = {
                int(r["id"]) for r in st
                if (int(r["x"]), int(r["y"])) == pos
            }
            self.assertEqual(len(ids & expected), 1, (pattern, wet_mask, ids))
            extras = ids - expected
            if curls:
                self.assertEqual(len(extras), 1, (pattern, wet_mask, ids))
                self.assertTrue(extras.issubset(curls), (pattern, wet_mask, ids))
            else:
                self.assertEqual(extras, set(), (pattern, wet_mask, ids))
            expected_pattern = (
                int(wet[pos])
                | int(wet[pos[0] + 1, pos[1]]) << 1
                | int(wet[pos[0], pos[1] + 1]) << 2
                | int(wet[pos[0] + 1, pos[1] + 1]) << 3
            )
            self.assertEqual(expected_pattern, pattern)

    def test_side_facing_dry_vertices_stay_above_waterline(self):
        # -4..-3 only: a side bank above -3 lets the wet quads' stretched tips
        # out-draw the -5 foam statics
        for pattern, dry_offset in ((11, (0, 1)), (13, (1, 0))):
            _, _, z, _, pos = scene_for_pattern(pattern, M.GRASS)
            dry_pos = (pos[0] + dry_offset[0], pos[1] + dry_offset[1])
            self.assertIn(int(z[dry_pos]), {-4, -3})

    def test_side_banks_never_rise_above_the_foam(self):
        # every dry tile with wet at N or W across a large ragged shore
        n = 25
        rng = np.random.default_rng(5)
        x, y = np.indices((n, n))
        wet = (x + rng.integers(0, 3, (n, n))) < 12
        wet = fix_tips(remove_wet_tips(wet))
        mat = np.full((n, n), M.GRASS, np.uint8)
        mat[wet] = M.WATER
        lid = np.full((n, n), 0x3, np.uint16)
        z = np.zeros((n, n), np.int16)
        encode_water(wet, z, lid, np.random.default_rng(6), mat)
        dry = ~wet
        side = np.zeros_like(wet)
        side[:, 1:] |= wet[:, :-1]
        side[1:, :] |= wet[:-1, :]
        side &= dry
        self.assertGreater(int(side.sum()), 0)
        self.assertLessEqual(int(z[side].max()), -3)

    def test_wedge_junctions_sit_on_the_shelf(self):
        # The wedge: a trench tile touching both a water-land foot tile (-5)
        # and dry land folds open an unpaintable gap in the client. Those
        # tiles step onto the -8 shelf - z only, so their dropoff art and
        # statics stay exactly as they were.
        n = 19
        x, y = np.indices((n, n))
        wet = ~((abs(x - 9) <= 1) & (abs(y - 9) <= 1) & (x >= 9) & (y >= 9))
        mat = np.full((n, n), M.GRASS, np.uint8)
        mat[wet] = M.WATER
        lid = np.full((n, n), 0x3, np.uint16)
        z = np.zeros((n, n), np.int16)
        st = encode_water(wet, z, lid, np.random.default_rng(42), mat)
        result = check_water(wet, z, lid, st)
        self.assertEqual(result["wedge_shapes"], 0)
        shelf = np.argwhere(wet & (z == -8))
        self.assertGreater(len(shelf), 0)
        covered = {(int(r["x"]), int(r["y"])) for r in st}
        water_land = {0xA8, 0xA9, 0xAA, 0xAB}
        for xx, yy in shelf:
            pos = (int(xx), int(yy))
            self.assertIn(pos, covered, pos)
            # the shelf keeps its seafloor/dropoff art - never flat water-land
            self.assertNotIn(int(lid[pos]), water_land, pos)

    def test_diagonal_only_ring_contact_uses_sunk_object_water(self):
        n = 11
        c = n // 2
        object_water = {int(i) for i in OBJW}
        for name, dry_pos, expected_land, expected_static in (
            ("R only", (c + 1, c - 1), {0x64, 0x65}, None),
            ("L only", (c - 1, c + 1), {0x64, 0x65}, None),
        ):
            with self.subTest(name=name):
                wet = np.ones((n, n), bool)
                wet[dry_pos] = False
                mat = np.full((n, n), M.WATER, np.uint8)
                mat[dry_pos] = M.SAND
                lid = np.full((n, n), 0xA8, np.uint16)
                lid[dry_pos] = 0x16
                z = np.zeros((n, n), np.int16)
                st = encode_water(wet, z, lid, np.random.default_rng(31), mat)
                self.assertIn(int(lid[c, c]), expected_land)
                self.assertEqual(int(z[c, c]), -15)  # mid-ocean construction: sunk + objw
                ids = {
                    int(r["id"]) for r in st
                    if (int(r["x"]), int(r["y"])) == (c, c)
                }
                self.assertEqual(len(ids), 1)
                self.assertTrue(ids.issubset(object_water))

    def test_water_invariants_hold(self):
        x, y = np.indices((31, 31))
        wet = (x - 15) ** 2 + (y - 15) ** 2 <= 9 ** 2
        mat = np.full(wet.shape, M.SAND, np.uint8)
        mat[wet] = M.WATER
        lid = np.full(wet.shape, 0x16, np.uint16)
        z = np.zeros(wet.shape, np.int16)
        st = encode_water(wet, z, lid, np.random.default_rng(22), mat)
        result = check_water(wet, z, lid, st)
        self.assertEqual(result["sunk_without_static"], 0)
        self.assertEqual(result["waterland_adjacent_dry"], 0)
        sid = self._static_ids(st)
        for pos, static_id in sid.items():
            if not wet[pos]:
                # dry foam is allowed up to z=0: Felucca's grass river banks keep
                # z=0 and still carry their overlay curls
                self.assertLessEqual(int(z[pos]), 0, f"hidden dry foam 0x{static_id:X}")


class CoastMaskCleanupTests(unittest.TestCase):
    def test_wet_and_dry_tips_are_removed(self):
        wet = np.zeros((9, 9), bool)
        wet[4, 4] = True
        self.assertFalse(remove_wet_tips(wet)[4, 4])

        wet = np.zeros((9, 9), bool)
        wet[5, 4] = True
        wet[4, 5] = True
        fixed = fix_tips(wet)
        self.assertTrue(fixed[4, 4])
        east = np.roll(fixed, -1, axis=0)
        south = np.roll(fixed, -1, axis=1)
        diagonal = np.roll(east, -1, axis=1)
        invalid = ~fixed & east & south & ~diagonal
        invalid[-1, :] = False
        invalid[:, -1] = False
        self.assertFalse(invalid.any())


if __name__ == "__main__":
    unittest.main()
