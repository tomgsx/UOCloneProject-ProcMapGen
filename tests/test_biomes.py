"""Biome bands and the temperature profile: a band is a fence the biome never
crosses, its front stands in from the fence irregularly rather than along one
straight row, and the profile decides where the cold ground lies.

The scene is a small all-land world with no hills, so the only things that shape
the snow are the band (gen/macro.py `band_mask`) and the temperature, read
through `biomes`.
"""
import unittest

import numpy as np

from gen.config import Config
from gen.macro import (
    BAND_BAYS,
    BAND_FRAY_SEED,
    BAND_INSET,
    BAND_RAGGED,
    BAND_SEEDS,
    BAND_WANDER,
    band_edge,
    band_mask,
    biomes,
    coldness,
)
from gen.noise import fbm

W, H = 1024, 512
LAT = np.broadcast_to((np.arange(H, dtype=np.float32) / H)[None, :], (W, H))


def depth(value):
    """A bound on how far a front can stand in from a fence at `value`, as a fraction
    of the map height: the noise never leaves [-1, 1], so its range is at most 2."""
    return 4 * value * (1 - value) * BAND_INSET * 2 * (BAND_WANDER + BAND_BAYS + BAND_RAGGED)


def flat_world(**settings):
    """(config, land, snow) for an all-land, all-flat world that asks for all snow
    unless `settings` says otherwise."""
    settings.setdefault("snow_fraction", 1.0)
    cfg = Config(width=W, height=H, seed=3, **settings)
    land = np.zeros((W, H), bool)
    land[8:-8, 8:-8] = True
    empty = np.zeros((W, H), bool)
    z = np.zeros((W, H), np.float32)
    return cfg, land, biomes(cfg, land, empty, empty, z) == 5


def southmost_rows(snow):
    """The southernmost snow row of every column that has snow, as latitudes."""
    columns = np.nonzero(snow.any(axis=1))[0]
    return np.array([np.nonzero(snow[x])[0].max() for x in columns]) / H


class BandEdgeTest(unittest.TestCase):
    def test_front_touches_its_fence_and_never_crosses_it(self):
        cfg = Config(width=W, height=H, seed=3)
        fray = fbm((W, H), cfg.seed + BAND_FRAY_SEED, 3, 50.0)
        bottom = band_edge(cfg, 0.35, BAND_SEEDS["snow"][1], fray, inward=-1.0)
        self.assertEqual(bottom.shape, (W, H))
        self.assertAlmostEqual(float(bottom.max()), 0.35, places=5)     # touches the fence
        self.assertGreaterEqual(float(bottom.min()), 0.35 - depth(0.35))
        self.assertGreater(float(bottom.std()), 0.01)                   # and is not flat
        top = band_edge(cfg, 0.35, BAND_SEEDS["snow"][0], fray, inward=1.0)
        self.assertAlmostEqual(float(top.min()), 0.35, places=5)
        self.assertLessEqual(float(top.max()), 0.35 + depth(0.35))

    def test_map_edges_are_exact(self):
        # a band edge at 0 or 1 is the map edge itself: no noise, no cost
        cfg = Config(width=W, height=H, seed=3, snow_band=(0.0, 1.0))
        self.assertTrue(band_mask(cfg, "snow", LAT).all())
        cfg = Config(width=W, height=H, seed=3, snow_band=(0.0, 0.0))
        self.assertFalse(band_mask(cfg, "snow", LAT).any())
        cfg = Config(width=W, height=H, seed=3, snow_band=(1.0, 1.0))
        self.assertFalse(band_mask(cfg, "snow", LAT).any())

    def test_no_two_edges_share_their_noise(self):
        seeds = [pair for edges in BAND_SEEDS.values() for pair in edges]
        flat = [seed for pair in seeds for seed in pair]
        self.assertEqual(len(flat), len(set(flat)))
        self.assertNotIn(BAND_FRAY_SEED, flat)


class BiomeBandTest(unittest.TestCase):
    def test_full_band_covers_everything(self):
        _cfg, land, snow = flat_world(snow_band=(0.0, 1.0))
        self.assertTrue((snow == land).all())
        _cfg, _land, snow = flat_world(snow_band=(0.0, 0.0))
        self.assertFalse(snow.any())

    def test_front_wanders_inside_the_fence(self):
        _cfg, _land, snow = flat_world(snow_band=(0.0, 0.4))
        self.assertTrue(snow.any())
        rows = southmost_rows(snow)
        self.assertGreater(float(rows.std()) * H, 4)              # an irregular front
        self.assertGreater(float(rows.max() - rows.min()) * H, 12)
        self.assertLess(float(rows.max()), 0.4)                    # never past the fence
        self.assertGreater(float(rows.min()), 0.4 - depth(0.4))
        self.assertFalse(snow[:, int(0.4 * H) :].any())

    def test_middle_band_has_two_fronts_inside_it(self):
        # both fronts of a 0.3 to 0.6 band wander, each inside its fence
        _cfg, _land, snow = flat_world(snow_band=(0.3, 0.6))
        columns = np.nonzero(snow.any(axis=1))[0]
        north = np.array([np.nonzero(snow[x])[0].min() for x in columns]) / H
        south = southmost_rows(snow)
        self.assertGreater(float(north.std()) * H, 4)
        self.assertGreater(float(south.std()) * H, 4)
        self.assertGreaterEqual(float(north.min()), 0.3)
        self.assertLess(float(south.max()), 0.6)
        self.assertFalse(snow[:, : int(0.3 * H)].any())
        self.assertFalse(snow[:, int(0.6 * H) :].any())

    def test_widening_the_band_only_adds_snow(self):
        _cfg, _land, narrow = flat_world(snow_band=(0.0, 0.25))
        _cfg, _land, wide = flat_world(snow_band=(0.0, 0.6))
        self.assertGreater(int(wide.sum()), int(narrow.sum()))
        self.assertEqual(int((narrow & ~wide).sum()), 0)


class TemperatureProfileTest(unittest.TestCase):
    def test_profiles_place_the_cold(self):
        lat = np.array([0.0, 0.25, 0.5, 0.75, 1.0], np.float32)
        north = coldness(Config(temperature_profile="north"), lat)
        poles = coldness(Config(temperature_profile="poles", poles_cold=(0.0, 1.0)), lat)
        np.testing.assert_allclose(north, [1.0, 0.75, 0.5, 0.25, 0.0])
        np.testing.assert_allclose(poles, [1.0, 0.5, 0.0, 0.5, 1.0])
        # the top-cold profile's default zones reproduce the plain gradient bit for bit
        self.assertTrue(np.array_equal(coldness(Config(temperature_profile="north"), LAT), 1 - LAT))

    def test_zones_hold_the_full_cold_and_the_full_heat(self):
        lat = np.array([0.0, 0.1, 0.2, 0.5, 0.8, 0.9, 1.0], np.float32)
        north = coldness(Config(temperature_profile="north", north_zones=(0.2, 0.8)), lat)
        np.testing.assert_allclose(north, [1.0, 1.0, 1.0, 0.5, 0.0, 0.0, 0.0])
        poles = coldness(
            Config(temperature_profile="poles", poles_cold=(0.1, 0.9), poles_heat=(0.4, 0.6)),
            np.array([0.0, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0], np.float32),
        )
        np.testing.assert_allclose(poles, [1.0, 1.0, 0.5, 0.0, 0.0, 0.0, 0.5, 1.0, 1.0], atol=1e-6)
        # zones that meet make a step, cold on the cold side
        step = coldness(Config(temperature_profile="north", north_zones=(0.5, 0.5)), lat)
        np.testing.assert_allclose(step, [1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0])
        step = coldness(
            Config(temperature_profile="poles", poles_cold=(0.5, 0.5), poles_heat=(0.5, 0.5)), lat
        )
        np.testing.assert_allclose(step, [1.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0])

    def test_poles_profile_snows_at_both_ends(self):
        # with no fence, a third of the land as snow goes to both cold edges under the
        # poles profile and only to the top under the north profile
        settings = dict(snow_band=(0.0, 1.0), snow_fraction=0.34)
        _cfg, _land, poles = flat_world(temperature_profile="poles", **settings)
        self.assertTrue(poles[:, : H // 10].any())
        self.assertTrue(poles[:, -H // 10 :].any())
        self.assertFalse(poles[:, H // 2 - H // 20 : H // 2 + H // 20].any())
        _cfg, _land, north = flat_world(temperature_profile="north", **settings)
        self.assertTrue(north[:, : H // 10].any())
        self.assertFalse(north[:, -H // 10 :].any())


if __name__ == "__main__":
    unittest.main()
