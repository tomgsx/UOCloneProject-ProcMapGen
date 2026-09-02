"""The application layer: settings serialisation and validation, the Qt form
(offscreen), output paths, and progress parsing. Plus the generator-side checks
that every setting on the form does what its tooltip says.
"""
import json
import multiprocessing
import os
import tempfile
import time
import unittest
from dataclasses import fields
from datetime import datetime
from pathlib import Path

import numpy as np

from gen.config import Config
from gen.macro import _top_threshold
from gen.roads import pick_towns, rasterize_roads
from gui.config_io import (
    FIXED_FIELDS,
    GROUPS,
    SETTING_BY_NAME,
    SETTINGS,
    config_dict,
    load_preset,
    make_config,
    save_preset,
    tooltip_html,
    upgrade_legacy,
)
from gui.paths import (
    retain_cancelled_output,
    unique_world_paths,
    validate_uo_directory,
    world_directory_names,
)
from gui.progress import phase_progress
from gui.tasks import config_fingerprint


class ConfigTests(unittest.TestCase):
    def test_config_json_round_trip(self):
        expected = Config(seed=12345, islands=12, centre=(0.42, 0.48))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preset.json"
            save_preset(path, expected)
            actual = load_preset(path)
        self.assertEqual(actual, expected)

    def test_map_dimensions_are_protected(self):
        value = config_dict(Config())
        value["width"] = 1024
        with self.assertRaisesRegex(ValueError, "7168"):
            make_config(value)

    def test_fingerprint_is_stable(self):
        value = config_dict(Config())
        reordered = dict(reversed(list(value.items())))
        self.assertEqual(config_fingerprint(value), config_fingerprint(reordered))

    def test_old_preset_with_retired_keys_still_loads(self):
        # a preset written before sea_z/trench_z were dropped and lake_hole_range
        # became min_lake_size: the sea levels vanish, the range keeps its minimum
        old = config_dict(Config(seed=99))
        del old["min_lake_size"]
        old["lake_hole_range"] = [75, 900]
        old["sea_z"] = -5
        old["trench_z"] = -15
        config = make_config(old)
        self.assertEqual(config.seed, 99)
        self.assertEqual(config.min_lake_size, 75)
        self.assertEqual(set(upgrade_legacy(old)), set(config_dict(Config())))

    def test_every_config_field_is_a_setting_or_fixed(self):
        # a field added to Config without a Setting would silently vanish from the form
        names = {field.name for field in fields(Config)}
        self.assertEqual(names, set(SETTING_BY_NAME) | set(FIXED_FIELDS))
        self.assertEqual(len(SETTINGS), len(SETTING_BY_NAME))
        for setting in SETTINGS:
            self.assertIn(setting.group, GROUPS, setting.name)

    def test_defaults_sit_inside_every_range(self):
        for setting in SETTINGS:
            default = config_dict(Config())[setting.name]
            values = default if isinstance(default, tuple) else (default,)
            for value in values:
                self.assertGreaterEqual(value, setting.minimum, setting.name)
                self.assertLessEqual(value, setting.maximum, setting.name)

    def test_tooltip_quotes_range_and_default(self):
        tip = tooltip_html(SETTING_BY_NAME["forest_fraction"])
        self.assertIn("Range:</b> 0.00 to 1.00", tip)
        self.assertIn("Default:</b> 0.38", tip)
        tip = tooltip_html(SETTING_BY_NAME["centre"])
        self.assertIn("0.05 to 0.95 for each of x and y", tip)
        self.assertIn("Default:</b> 0.40, 0.50", tip)
        tip = tooltip_html(SETTING_BY_NAME["hill_levels"])
        self.assertIn("1 to 100 each, lowest first, up to 12 levels", tip)
        tip = tooltip_html(SETTING_BY_NAME["margin"])
        self.assertIn("0 tiles to 1000 tiles", tip)
        self.assertIn("Default:</b> 220 tiles", tip)
        for setting in SETTINGS:
            self.assertTrue(setting.tooltip.endswith("."), setting.name)

    def test_out_of_range_values_name_the_setting_and_its_range(self):
        for name, bad in (
            ("road_width", 0), ("coast_amp", 2.5), ("mountain_fraction", -0.1),
            ("centre", (0.4, 0.99)), ("radii", (0.6, 0.3)), ("hill_levels", (5, 200)),
        ):
            value = config_dict(Config())
            value[name] = bad
            with self.assertRaisesRegex(ValueError, SETTING_BY_NAME[name].label, msg=name):
                make_config(value)
        value = config_dict(Config())
        value["hill_levels"] = (10, 5)
        with self.assertRaisesRegex(ValueError, "ascending"):
            make_config(value)


class GeneratorSettingTests(unittest.TestCase):
    """Settings that were once dead or fragile do what their tooltips say."""

    def test_top_threshold_tolerates_extreme_fractions(self):
        values = np.arange(10, dtype=np.float64)
        self.assertEqual(_top_threshold(values, 0.3), np.quantile(values, 0.7))
        self.assertEqual(_top_threshold(values, 0.0), 9.0)      # nothing above the max
        self.assertEqual(_top_threshold(values, 1.0), 0.0)      # everything above the min
        self.assertEqual(_top_threshold(values, 2.5), 0.0)      # more than exists: everything
        self.assertEqual(_top_threshold(values[:0], 0.5), np.inf)   # nothing to choose from

    def test_road_width_changes_the_road(self):
        # without an rng the width noise is zero, which is the middle band: the road
        # runs two tiles wider than its narrowest width (the setting) everywhere
        shape = (40, 40)
        road = [[(x, 20) for x in range(5, 35)]]
        widths = {}
        for width in (1, 3, 5, 7):
            core, _centre = rasterize_roads(road, shape, width=width)
            widths[width] = int(core[20].sum())    # tiles across the road at x=20
        self.assertEqual(widths, {1: 3, 3: 5, 5: 7, 7: 9})

    def test_town_count_zero_places_no_town(self):
        shape = (200, 200)
        land = np.ones(shape, bool)
        wet = np.zeros(shape, bool)
        z = np.zeros(shape, np.int16)
        material = np.ones(shape, np.uint8)     # grass everywhere
        rock = np.zeros(shape, bool)
        rng = np.random.default_rng(1)
        none = pick_towns(Config(towns=0, town_min_spacing=100), land, wet, z, material, rock, rng)
        self.assertEqual(none, [])
        two = pick_towns(Config(towns=2, town_min_spacing=100), land, wet, z, material, rock, rng)
        self.assertEqual(len(two), 2)


class FormTests(unittest.TestCase):
    """The Qt form round-trips a config and shows every setting once, offscreen."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest("PySide6 is not installed")
        cls.application = QApplication.instance() or QApplication([])

    def test_form_round_trips_and_labels_fine_tuning_in_italics(self):
        from PySide6.QtWidgets import QLabel
        from gui.app import SettingsForm

        form = SettingsForm()
        expected = Config(seed=4242, centre=(0.35, 0.55), road_width=5, hill_levels=(4, 8))
        form.set_value(expected)
        self.assertEqual(form.value(), expected)
        self.assertEqual(set(form.widgets), set(SETTING_BY_NAME))
        italic = {
            label.text() for label in form.findChildren(QLabel) if label.font().italic()
        }
        self.assertEqual(italic, {s.label for s in SETTINGS if s.advanced})
        form.set_seed(12)
        self.assertEqual(form.value().seed, 12)

    def test_wheel_over_an_unfocused_box_changes_nothing(self):
        # scrolling the page must not turn whichever spin box the pointer crosses
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        from gui.app import SettingsForm

        form = SettingsForm()
        form.show()
        self.application.processEvents()   # focus is only granted to an active window
        spin = form.widgets["towns"]
        before = spin.value()

        def one_notch_up():
            return QWheelEvent(
                QPointF(5, 5), spin.mapToGlobal(QPoint(5, 5)), QPoint(), QPoint(0, 120),
                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase, False,
            )

        self.assertFalse(spin.hasFocus())
        self.application.sendEvent(spin, one_notch_up())
        self.assertEqual(spin.value(), before)
        spin.setFocus()
        self.application.processEvents()
        self.assertTrue(spin.hasFocus())
        self.application.sendEvent(spin, one_notch_up())
        self.assertEqual(spin.value(), before + 1)


class PathTests(unittest.TestCase):
    def test_uo_directory_requires_tiledata(self):
        with tempfile.TemporaryDirectory() as directory:
            valid, _ = validate_uo_directory(directory)
            self.assertFalse(valid)
            (Path(directory) / "tiledata.mul").write_bytes(b"\0" * 1_000_001)
            valid, message = validate_uo_directory(directory)
            self.assertTrue(valid, message)

    def test_timestamped_output_name(self):
        when = datetime(2026, 8, 27, 1, 2, 3)
        self.assertEqual(
            world_directory_names(77, when),
            ("seed_77_20260827-010203", ".seed_77_20260827-010203.partial"),
        )

    def test_output_name_collision_gets_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            when = datetime(2026, 8, 27, 1, 2, 3)
            final, _partial = unique_world_paths(root, 7, when)
            final.mkdir()
            second, _ = unique_world_paths(root, 7, when)
            self.assertTrue(second.name.endswith("_1"))

    def test_cancelled_partial_is_not_successful_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            final = root / "seed_7_20260827-010203"
            partial = root / ".seed_7_20260827-010203.partial"
            partial.mkdir()
            (partial / "map0.mul").write_bytes(b"incomplete")
            cancelled = retain_cancelled_output(partial, final)
            self.assertFalse(partial.exists())
            self.assertFalse(final.exists())
            self.assertTrue((cancelled / "CANCELLED.txt").is_file())


class ProgressTests(unittest.TestCase):
    def test_generator_phase_progress_never_moves_backwards(self):
        value, phase = phase_progress("[  81.7s] rivers", 0)
        self.assertEqual((value, phase), (25, "rivers"))
        value, phase = phase_progress("[  82.0s] detail", value)
        self.assertEqual((value, phase), (25, None))
        value, phase = phase_progress("[ 210.0s] tiles", value)
        self.assertEqual((value, phase), (72, "tiles"))

    def test_worker_process_can_be_cancelled(self):
        # the spawn context is the one the window uses, and the only one Windows has
        context = multiprocessing.get_context("spawn")
        process = context.Process(target=time.sleep, args=(10,))
        process.start()
        process.terminate()
        process.join(timeout=2)
        self.assertFalse(process.is_alive())


if __name__ == "__main__":
    unittest.main()
