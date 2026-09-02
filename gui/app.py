"""The desktop application: the settings form, the preview pane, the log, and the
buttons that start and cancel generation.

The window never generates anything itself. Generate Preview and Generate World
start a child process (multiprocessing, spawn context, so Linux and Windows
behave the same) running one of the entry points in gui/tasks.py; the child
streams log and progress events back over a queue that poll_process() drains
on a timer, and Cancel simply terminates the child. Everything the user sets -
the UO folder, the output folder, the last settings - is saved to
portable-settings.json beside the executable (gui/paths.py).
"""
from __future__ import annotations

import json
import multiprocessing
import secrets
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gen.config import Config
from gui.config_io import (
    BIOMES,
    COAST,
    CONTINENT,
    ELEVATION,
    FIXED_FIELDS,
    GROUPS,
    SETTINGS,
    TOWNS,
    WATER,
    WORLD,
    Setting,
    config_dict,
    fixed_note,
    load_preset,
    make_config,
    save_preset,
    settings_in,
    tooltip_html,
)
from gui.paths import (
    default_output_root,
    load_settings,
    resource_root,
    retain_cancelled_output,
    save_settings,
    unique_world_paths,
    validate_uo_directory,
)
from gui.progress import phase_progress
from gui.tasks import (
    config_fingerprint,
    drain_queue,
    preview_task,
    world_task,
)


class PreviewView(QGraphicsView):
    """The overview image pane: fits the image on load, drags to pan, wheel zooms."""

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.item = QGraphicsPixmapItem()
        self.scene().addItem(self.item)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self._has_image = False

    def set_image(self, path: Path) -> bool:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return False
        self.item.setPixmap(pixmap)
        self.scene().setSceneRect(self.item.boundingRect())
        self._has_image = True
        self.fit_image()
        return True

    def fit_image(self) -> None:
        if self._has_image:
            self.fitInView(self.item, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        if not self._has_image:
            return super().wheelEvent(event)
        factor = 1.18 if event.angleDelta().y() > 0 else 1 / 1.18
        self.scale(factor, factor)


# the setting groups, in reading order down the left column and then the right
COLUMNS = ((WORLD, CONTINENT, COAST, TOWNS), (WATER, ELEVATION, BIOMES))


class WheelGuard(QObject):
    """Ignore wheel events on a box that is not focused. Qt otherwise lets the wheel
    turn any spin box the pointer crosses while the page is being scrolled, which
    changes a setting without the user noticing; a click first makes it deliberate."""

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Wheel and not watched.hasFocus():
            event.ignore()
            return True
        return super().eventFilter(watched, event)


class SettingsForm(QWidget):
    """One page of every world setting, grouped by what it shapes.

    Each row is built from its `Setting` entry in gui/config_io.py: the box's
    range, the tooltip (which quotes that range and the default) and the italic
    label of a fine-tuning setting all come from that one record.
    """

    def __init__(self):
        super().__init__()
        # a scalar setting maps to its box; a pair setting to a tuple of boxes
        self.widgets: dict[str, QWidget | tuple[QWidget, ...]] = {}
        self._wheel_guard = WheelGuard(self)
        defaults = config_dict(Config())
        content = QWidget()
        columns = QHBoxLayout(content)
        columns.setContentsMargins(0, 0, 8, 0)
        # Two columns so the whole page fits a laptop screen without scrolling: the
        # groups keep their reading order down the first column and then the second,
        # split where the row counts balance.
        for groups in COLUMNS:
            column = QVBoxLayout()
            column.setSpacing(6)
            for group in groups:
                box = QGroupBox(group)
                form = QFormLayout(box)
                form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
                form.setVerticalSpacing(4)
                form.setContentsMargins(8, 6, 8, 6)
                for setting in settings_in(group):
                    form.addRow(
                        self._label(setting), self._field(setting, defaults[setting.name])
                    )
                column.addWidget(box)
            column.addStretch(1)
            columns.addLayout(column, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll, 1)
        note = QLabel(fixed_note())
        note.setWordWrap(True)
        layout.addWidget(note)

    @staticmethod
    def _label(setting: Setting) -> QLabel:
        label = QLabel(setting.label)
        if setting.advanced:
            font = label.font()
            font.setItalic(True)
            label.setFont(font)
        label.setToolTip(tooltip_html(setting))
        return label

    def _spin(self, setting: Setting, value: float) -> QSpinBox | QDoubleSpinBox:
        if setting.decimals:
            spin = QDoubleSpinBox()
            spin.setDecimals(setting.decimals)
        else:
            spin = QSpinBox()
        spin.setRange(setting.minimum, setting.maximum)
        spin.setSingleStep(setting.step)
        spin.setSuffix(setting.suffix)
        spin.setValue(value)
        spin.setToolTip(tooltip_html(setting))
        spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)   # the wheel does not focus it
        spin.installEventFilter(self._wheel_guard)
        return spin

    def _field(self, setting: Setting, default: Any) -> QWidget:
        if setting.parts:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            boxes = []
            for part, value in zip(setting.parts, default):
                layout.addWidget(QLabel(part))
                spin = self._spin(setting, value)
                layout.addWidget(spin, 1)
                boxes.append(spin)
            self.widgets[setting.name] = tuple(boxes)
            return row
        if setting.is_list:
            line = QLineEdit(setting.format_value(default))
            line.setToolTip(tooltip_html(setting))
            self.widgets[setting.name] = line
            return line
        spin = self._spin(setting, default)
        self.widgets[setting.name] = spin
        if setting.name != "seed":
            return spin
        # the seed keeps its Random button beside it, where the number it changes is
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(spin, 1)
        random_button = QPushButton("Random")
        random_button.setToolTip("Pick a new seed at random.")
        random_button.clicked.connect(
            lambda: self.set_seed(secrets.randbelow(2_147_483_648))
        )
        layout.addWidget(random_button)
        return row

    def value(self) -> Config:
        """The form's current settings as a validated Config (raises ValueError with a
        message naming the setting when a value is out of range or malformed)."""
        defaults = config_dict(Config())
        result: dict[str, Any] = {name: defaults[name] for name in FIXED_FIELDS}
        for setting in SETTINGS:
            widget = self.widgets[setting.name]
            if setting.parts:
                result[setting.name] = tuple(spin.value() for spin in widget)
            elif setting.is_list:
                assert isinstance(widget, QLineEdit)
                parts = [part.strip() for part in widget.text().split(",") if part.strip()]
                try:
                    result[setting.name] = tuple(int(part) for part in parts)
                except ValueError:
                    raise ValueError(
                        f"{setting.label} must be whole numbers separated by commas."
                    ) from None
            else:
                assert isinstance(widget, (QSpinBox, QDoubleSpinBox))
                result[setting.name] = widget.value()
        return make_config(result)

    def set_value(self, config: Config) -> None:
        """Show a Config in the form."""
        values = config_dict(config)
        for setting in SETTINGS:
            widget = self.widgets[setting.name]
            value = values[setting.name]
            if setting.parts:
                for spin, part in zip(widget, value):
                    spin.setValue(part)
            elif setting.is_list:
                assert isinstance(widget, QLineEdit)
                widget.setText(setting.format_value(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            else:
                assert isinstance(widget, QSpinBox)
                widget.setValue(int(value))

    def set_seed(self, seed: int) -> None:
        widget = self.widgets["seed"]
        assert isinstance(widget, QSpinBox)
        widget.setValue(seed)


class MainWindow(QMainWindow):
    """The main window. `process`/`queue` are the running child process and its event
    queue (None when idle); `active_*` describe the job it is running."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ultima Online Procedural Map Generator")
        self.resize(1280, 860)
        self.settings = load_settings()
        self.uo_directory = str(self.settings.get("uo_directory", ""))
        self.output_root = Path(
            self.settings.get("output_root", str(default_output_root()))
        ).expanduser()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.process = None
        self.queue = None
        self.active_kind: str | None = None
        self.active_partial: Path | None = None
        self.active_final: Path | None = None
        self.started_at = 0.0
        self.progress_value = 0
        self.exit_wait_ticks = 0

        self.form = SettingsForm()
        saved_config = self.settings.get("config")
        if isinstance(saved_config, dict):
            try:
                self.form.set_value(make_config(saved_config))
            except (TypeError, ValueError):
                pass

        self.preview = PreviewView()
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.elapsed = QLabel("Ready")
        self.uo_label = QLabel()
        self.uo_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.output_label = QLabel(str(self.output_root))
        self.output_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.preview_button = QPushButton("Generate Preview")
        self.world_button = QPushButton("Generate World")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.fit_button = QPushButton("Fit Preview")
        self.open_button = QPushButton("Open Output Folder")
        self.uo_button = QPushButton("Select UO Folder")
        self.output_button = QPushButton("Choose Output Folder")

        self.preview_button.clicked.connect(self.generate_preview)
        self.world_button.clicked.connect(self.generate_world)
        self.cancel_button.clicked.connect(self.cancel_job)
        self.fit_button.clicked.connect(self.preview.fit_image)
        self.open_button.clicked.connect(self.open_output)
        self.uo_button.clicked.connect(self.choose_uo)
        self.output_button.clicked.connect(self.choose_output)

        self._build_menu()
        self._build_layout()
        self._refresh_uo_label()

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(100)
        self.poll_timer.timeout.connect(self.poll_process)
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self.update_elapsed)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        load_action = QAction("Load preset…", self)
        save_action = QAction("Save preset…", self)
        reset_action = QAction("Reset defaults", self)
        load_action.triggered.connect(self.load_preset)
        save_action.triggered.connect(self.save_preset)
        reset_action.triggered.connect(lambda: self.form.set_value(Config()))
        file_menu.addAction(load_action)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        file_menu.addAction(reset_action)

    def _build_layout(self) -> None:
        path_box = QGroupBox("Portable paths")
        path_layout = QFormLayout(path_box)
        uo_row = QWidget()
        uo_layout = QHBoxLayout(uo_row)
        uo_layout.setContentsMargins(0, 0, 0, 0)
        uo_layout.addWidget(self.uo_label, 1)
        uo_layout.addWidget(self.uo_button)
        out_row = QWidget()
        out_layout = QHBoxLayout(out_row)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.addWidget(self.output_label, 1)
        out_layout.addWidget(self.output_button)
        path_layout.addRow("UO installation", uo_row)
        path_layout.addRow("Output root", out_row)

        # the settings form carries its own group boxes, so it needs no outer frame
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(path_box)
        left_layout.addWidget(self.form, 1)

        preview_box = QGroupBox("World overview")
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.addWidget(self.preview, 1)
        preview_layout.addWidget(self.fit_button, 0, Qt.AlignmentFlag.AlignRight)

        upper = QSplitter()
        upper.addWidget(left)
        upper.addWidget(preview_box)
        upper.setStretchFactor(0, 0)
        upper.setStretchFactor(1, 1)
        upper.setSizes([680, 600])

        buttons = QHBoxLayout()
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.world_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        buttons.addWidget(self.open_button)

        status = QHBoxLayout()
        status.addWidget(self.progress, 1)
        status.addWidget(self.elapsed)

        # the log sits under a draggable split so it can give the settings page room
        log_box = QWidget()
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.addWidget(QLabel("Generation log"))
        log_layout.addWidget(self.log, 1)
        self.log.setMinimumHeight(60)
        vertical = QSplitter(Qt.Orientation.Vertical)
        vertical.addWidget(upper)
        vertical.addWidget(log_box)
        vertical.setStretchFactor(0, 1)
        vertical.setStretchFactor(1, 0)
        vertical.setSizes([640, 120])

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(vertical, 1)
        layout.addLayout(status)
        layout.addLayout(buttons)
        self.setCentralWidget(central)

    def config_or_error(self) -> Config | None:
        """The form's Config, or None after showing the validation message."""
        try:
            return self.form.value()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Invalid settings", str(exc))
            return None

    def start_process(self, kind: str, target, args: tuple) -> None:
        """Start `target(*args, queue)` in a child process and begin polling it."""
        if self.process is not None:
            return
        context = multiprocessing.get_context("spawn")
        self.queue = context.Queue()
        self.process = context.Process(target=target, args=(*args, self.queue))
        self.process.start()
        self.active_kind = kind
        self.started_at = time.monotonic()
        self.progress_value = 0
        self.progress.setValue(0)
        self.exit_wait_ticks = 0
        self.preview_button.setEnabled(False)
        self.world_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.log.clear()
        self.elapsed.setText("Starting…")
        self.poll_timer.start()
        self.elapsed_timer.start()

    def generate_preview(self) -> None:
        """Generate Preview: reuse the cached image for these exact settings, else
        render one in a child process."""
        config = self.config_or_error()
        if config is None:
            return
        data = config_dict(config)
        cache = self.output_root / ".preview"
        target = cache / f"preview_{config.seed}_{config_fingerprint(data)}.png"
        if target.exists() and self.preview.set_image(target):
            self.log.setPlainText(f"Loaded cached preview: {target}")
            return
        self.start_process("preview", preview_task, (data, str(target)))

    def generate_world(self) -> None:
        """Generate World: needs a valid UO folder; writes into a .partial folder that
        the child renames on success."""
        config = self.config_or_error()
        if config is None:
            return
        valid, message = validate_uo_directory(self.uo_directory)
        if not valid:
            QMessageBox.warning(
                self,
                "UO data required",
                message + "\n\nSelect your Ultima Online installation before generating.",
            )
            self.choose_uo()
            return
        self.output_root.mkdir(parents=True, exist_ok=True)
        final, partial = unique_world_paths(self.output_root, config.seed)
        self.active_final, self.active_partial = final, partial
        self.start_process(
            "world",
            world_task,
            (
                config_dict(config),
                self.uo_directory,
                str(partial),
                str(final),
            ),
        )

    def poll_process(self) -> None:
        """Timer tick: apply every event the child has queued, and notice a child that
        died without sending a terminal event."""
        if self.process is None or self.queue is None:
            return
        terminal_event = False
        for event in drain_queue(self.queue):
            kind = event[0]
            if kind == "log":
                line = str(event[1])
                self.log.append(line)
                self.progress_value, _phase = phase_progress(
                    line, self.progress_value
                )
                self.progress.setValue(self.progress_value)
            elif kind == "progress":
                self.progress_value = max(self.progress_value, int(event[1]))
                self.progress.setValue(self.progress_value)
            elif kind == "preview_done":
                terminal_event = True
                path = Path(event[1])
                if self.preview.set_image(path):
                    self.log.append(f"Preview ready: {path}")
                self.finish_job(True)
            elif kind == "world_done":
                terminal_event = True
                path = Path(event[1])
                self.preview.set_image(path / "overview.png")
                self.log.append(f"World ready: {path}")
                self.active_final = path
                self.finish_job(True)
            elif kind == "error":
                terminal_event = True
                self.log.append(str(event[1]))
                self.finish_job(False, "Generation failed. See the log for details.")
        if terminal_event or self.process is None:
            return
        if not self.process.is_alive():
            self.exit_wait_ticks += 1
            if self.exit_wait_ticks >= 10:
                self.finish_job(
                    False,
                    f"The {self.active_kind or 'generation'} process exited unexpectedly.",
                )

    def finish_job(self, success: bool, message: str = "") -> None:
        """Return the window to idle after the child finished; `message` is shown as an
        error dialog on failure."""
        if self.process is not None:
            self.process.join(timeout=1)
        self.process = None
        self.queue = None
        self.poll_timer.stop()
        self.elapsed_timer.stop()
        self.preview_button.setEnabled(True)
        self.world_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if success:
            self.progress.setValue(100)
            self.elapsed.setText(
                f"Completed in {time.monotonic() - self.started_at:.1f}s"
            )
        else:
            self.elapsed.setText("Failed")
            if message:
                QMessageBox.critical(self, "Map generation", message)
        self.save_portable_settings()

    def cancel_job(self) -> None:
        """Cancel: terminate the child and keep a cancelled world's partial output under
        a .cancelled name, so a completed-looking folder is always a complete world."""
        if self.process is None:
            return
        kind = self.active_kind
        self.process.terminate()
        self.process.join(timeout=5)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=2)
        if kind == "world" and self.active_partial and self.active_partial.exists():
            try:
                cancelled = retain_cancelled_output(
                    self.active_partial, self.active_final
                )
                self.log.append(f"Cancelled output retained for diagnostics: {cancelled}")
            except OSError as exc:
                self.log.append(f"Could not retain cancelled output: {exc}")
        self.process = None
        self.queue = None
        self.poll_timer.stop()
        self.elapsed_timer.stop()
        self.preview_button.setEnabled(True)
        self.world_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.elapsed.setText("Cancelled")

    def update_elapsed(self) -> None:
        elapsed = int(time.monotonic() - self.started_at)
        self.elapsed.setText(f"{elapsed // 60}:{elapsed % 60:02d} elapsed")

    def choose_uo(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Select Ultima Online installation", self.uo_directory
        )
        if not selected:
            return
        valid, message = validate_uo_directory(selected)
        if not valid:
            QMessageBox.warning(self, "Invalid UO installation", message)
            return
        self.uo_directory = selected
        self._refresh_uo_label()
        self.save_portable_settings()

    def choose_output(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Choose output folder", str(self.output_root)
        )
        if not selected:
            return
        self.output_root = Path(selected)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.output_label.setText(str(self.output_root))
        self.save_portable_settings()

    def _refresh_uo_label(self) -> None:
        valid, _message = validate_uo_directory(self.uo_directory)
        self.uo_label.setText(
            self.uo_directory if valid else "Not configured (tiledata.mul required)"
        )

    def save_preset(self) -> None:
        config = self.config_or_error()
        if config is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save MapGen preset", "mapgen-preset.json", "JSON (*.json)"
        )
        if path:
            try:
                save_preset(Path(path), config)
            except OSError as exc:
                QMessageBox.warning(self, "Save failed", str(exc))

    def load_preset(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load MapGen preset", "", "JSON (*.json)"
        )
        if path:
            try:
                self.form.set_value(load_preset(Path(path)))
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                QMessageBox.warning(self, "Invalid preset", str(exc))

    def open_output(self) -> None:
        path = self.active_final if self.active_final and self.active_final.exists() else self.output_root
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def save_portable_settings(self) -> None:
        """Write the UO folder, the output folder and the current settings to
        portable-settings.json."""
        config = self.config_or_error()
        if config is None:
            return
        save_settings(
            {
                "uo_directory": self.uo_directory,
                "output_root": str(self.output_root),
                "config": config_dict(config),
            }
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.process is not None:
            answer = QMessageBox.question(
                self,
                "Generation is running",
                "Cancel the active job and close MapGen?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.cancel_job()
        self.save_portable_settings()
        event.accept()


def run() -> int:
    """Create the application and the main window and run the event loop."""
    application = QApplication.instance() or QApplication([])
    application.setApplicationName("MapGen Portable")
    application.setWindowIcon(QIcon(str(resource_root() / "assets" / "mapgen.svg")))
    window = MainWindow()
    window.show()
    return application.exec()
