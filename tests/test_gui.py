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
            if setting.choices:
                self.assertIn(default, dict(setting.choices), setting.name)
                continue
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
        self.assertIn("Default:</b> 150 tiles", tip)
        for setting in SETTINGS:
            self.assertTrue(setting.tooltip.endswith("."), setting.name)

    def test_out_of_range_values_name_the_setting_and_its_range(self):
        for name, bad in (
            ("road_width", 0), ("coast_amp", 2.5), ("mountain_fraction", -0.1),
            ("centre", (0.4, 0.99)), ("radii", (0.6, 0.3)), ("hill_levels", (5, 200)),
            ("snow_band", (0.6, 0.4)), ("jungle_band", (0.2, 1.5)),
            ("temperature_profile", "sideways"), ("north_zones", (0.8, 0.2)),
        ):
            value = config_dict(Config())
            value[name] = bad
            with self.assertRaisesRegex(ValueError, SETTING_BY_NAME[name].label, msg=name):
                make_config(value)
        value = config_dict(Config())
        value["hill_levels"] = (10, 5)
        with self.assertRaisesRegex(ValueError, "ascending"):
            make_config(value)
        value = config_dict(Config())
        value["poles_cold"], value["poles_heat"] = (0.3, 0.7), (0.2, 0.8)
        with self.assertRaisesRegex(ValueError, "Heat zone must lie between"):
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
        expected = Config(
            seed=4242, centre=(0.35, 0.55), road_width=5, hill_levels=(4, 8),
            temperature_profile="poles", snow_band=(0.1, 0.5),
            north_zones=(0.1, 0.9), poles_cold=(0.1, 0.9), poles_heat=(0.4, 0.6),
        )
        form.set_value(expected)
        self.assertEqual(form.value(), expected)
        self.assertEqual(set(form.widgets), set(SETTING_BY_NAME))
        italic = {
            label.text() for label in form.findChildren(QLabel) if label.font().italic()
        }
        self.assertEqual(italic, {s.label for s in SETTINGS if s.advanced})
        form.set_seed(12)
        self.assertEqual(form.value().seed, 12)

    def test_profile_choices_are_the_generator_profiles(self):
        from gen.macro import TEMPERATURE_PROFILES

        choices = dict(SETTING_BY_NAME["temperature_profile"].choices)
        self.assertEqual(set(choices), set(TEMPERATURE_PROFILES))

    def test_overlays_follow_the_form_and_hide_when_generating(self):
        import gui.app as app_module
        from gui.app import MainWindow

        with tempfile.TemporaryDirectory() as directory:
            # keep the window's files out of the repository and every dialog closed
            original = (app_module.load_settings, app_module.save_settings, app_module.QMessageBox.warning)
            app_module.load_settings = lambda: {"output_root": directory}
            app_module.save_settings = lambda value: None
            app_module.QMessageBox.warning = lambda *args, **kwargs: None
            try:
                window = MainWindow()
                started = []
                window.start_process = lambda kind, target, args: started.append(kind)
                window.choose_uo = lambda: None
                self.assertTrue(window.bands_toggle.isChecked())
                self.assertTrue(window.temperature_toggle.isChecked())
                self.assertEqual(window.preview.values["snow_band"], (0.0, 1.0))
                spins = window.form.widgets["snow_band"]
                spins[1].setValue(0.5)
                self.assertEqual(window.preview.values["snow_band"], (0.0, 0.5))
                # the zone rows follow the profile: only the selected profile's show
                form_rows = window.form._rows
                def visible(name):
                    form, field = form_rows[name]
                    return form.isRowVisible(form.getWidgetPosition(field)[0])
                self.assertEqual(window.preview.profile, "poles")
                self.assertFalse(visible("north_zones"))
                self.assertTrue(visible("poles_cold") and visible("poles_heat"))
                combo = window.form.widgets["temperature_profile"]
                combo.setCurrentIndex(combo.findData("north"))
                self.assertEqual(window.preview.profile, "north")
                self.assertTrue(visible("north_zones"))
                self.assertFalse(visible("poles_cold"))
                combo.setCurrentIndex(combo.findData("poles"))
                # a dragged handle lands in the box, and the box feeds the overlay
                window.preview.handle_dragged.emit("snow_band", 1, 0.62)
                self.assertEqual(spins[1].value(), 0.62)
                self.assertEqual(window.preview.values["snow_band"], (0.0, 0.62))
                window.preview.handle_dragged.emit("poles_heat", 0, 0.4)
                self.assertEqual(window.form.widgets["poles_heat"][0].value(), 0.4)
                self.assertEqual(window.preview.values["poles_heat"], (0.4, 0.5))

                window.preview_button.click()
                self.assertEqual(started, ["preview"])
                self.assertFalse(window.bands_toggle.isChecked())
                self.assertFalse(window.preview.show_bands)
                self.assertFalse(window.preview.show_temperature)
                window.bands_toggle.setChecked(True)
                self.assertTrue(window.preview.show_bands)
                window.world_button.click()      # refused for want of a UO folder, hides anyway
                self.assertFalse(window.preview.show_bands)
            finally:
                app_module.load_settings, app_module.save_settings, app_module.QMessageBox.warning = original

    def test_overlay_draws_over_the_outline_before_any_image(self):
        from gui.app import PreviewView

        view = PreviewView()
        view.resize(400, 300)
        view.set_overlay({"snow_band": (0.0, 0.35), "swamp_band": (0.3, 1.0), "north_zones": (0.0, 1.0)}, "north")
        view.show()
        self.application.processEvents()
        image = view.grab().toImage()
        self.assertFalse(image.isNull())
        # the temperature bar is drawn first, then the bars in placement order
        tracks = view._tracks(view._area())
        self.assertEqual([t.key for t in tracks], ["temperature", "snow", "swamp"])
        probe = tracks[0].rect.center()
        colour = image.pixelColor(int(probe.x()), int(probe.y()))
        self.assertNotEqual((colour.red(), colour.green(), colour.blue()), (0, 0, 0))
        view.set_overlay_visible(bands=False, temperature=False)
        colour = view.grab().toImage().pixelColor(int(probe.x()), int(probe.y()))
        self.assertEqual((colour.red(), colour.green(), colour.blue()), (0, 0, 0))

    def test_hovering_and_dragging_a_bar(self):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from gui.app import PreviewView

        view = PreviewView()
        view.resize(600, 400)
        values = {"snow_band": (0.0, 0.35), "swamp_band": (0.3, 1.0), "north_zones": (0.0, 1.0),
                  "poles_cold": (0.0, 1.0), "poles_heat": (0.5, 0.5)}
        view.set_overlay(values, "north")
        view.show()
        self.application.processEvents()
        emitted = []
        view.handle_dragged.connect(lambda name, index, value: emitted.append((name, index, value)))
        area = view._area()
        tracks = {t.key: t for t in view._tracks(area)}
        snow, temperature = tracks["snow"].rect, tracks["temperature"].rect

        def send(kind, pos, button=Qt.MouseButton.NoButton, buttons=Qt.MouseButton.NoButton):
            event = QMouseEvent(kind, pos, view.viewport().mapToGlobal(pos.toPoint()).toPointF(),
                                button, buttons, Qt.KeyboardModifier.NoModifier)
            self.application.sendEvent(view.viewport(), event)

        def drag(x, from_value, to_value):
            start = QPointF(x, area.top() + from_value * area.height())
            end = QPointF(x, area.top() + to_value * area.height())
            send(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
            send(QEvent.Type.MouseMove, end, buttons=Qt.MouseButton.LeftButton)
            send(QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.LeftButton)

        # hovering the bar names it; the pane's middle is nobody's bar
        send(QEvent.Type.MouseMove, QPointF(snow.center().x(), area.center().y()))
        self.assertEqual(view.hover, "snow")
        send(QEvent.Type.MouseMove, area.center())
        self.assertIsNone(view.hover)
        # the bottom handle of snow sits at 0.35 of the height; drag it to 0.60
        drag(snow.center().x(), 0.35, 0.6)
        self.assertIsNone(view.drag)
        self.assertEqual(emitted[-1], ("snow_band", 1, 0.6))
        # the top handle can never pass the bottom one
        view.set_overlay({**values, "snow_band": (0.0, 0.6)}, "north")
        drag(snow.center().x(), 0.0, 0.9)
        self.assertEqual(emitted[-1], ("snow_band", 0, 0.6))
        # dragging the band itself moves both edges, keeping its length, up to the map edge
        view.set_overlay({**values, "snow_band": (0.1, 0.4)}, "north")
        emitted.clear()
        drag(snow.center().x(), 0.25, 0.95)
        self.assertEqual(emitted, [("snow_band", 1, 1.0), ("snow_band", 0, 0.7)])
        # the temperature bar: the top-cold profile's hot handle at 1.00 dragged up to 0.70
        drag(temperature.center().x(), 1.0, 0.7)
        self.assertEqual(emitted[-1], ("north_zones", 1, 0.7))
        # the two-pole profile's coincident heat handles part in the direction of the drag
        view.set_overlay(values, "poles")
        emitted.clear()
        drag(temperature.center().x(), 0.5, 0.3)
        self.assertEqual(emitted[-1], ("poles_heat", 0, 0.3))
        drag(temperature.center().x(), 0.5, 0.7)
        self.assertEqual(emitted[-1], ("poles_heat", 1, 0.7))

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
