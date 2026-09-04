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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QCloseEvent,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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
from gen.macro import BIOME_BANDS, BIOME_MATERIAL, OVERVIEW_PALETTE, OVERVIEW_SCALE, PROFILE_HANDLES
from gui.config_io import (
    BIOMES,
    COAST,
    CONTINENT,
    ELEVATION,
    FIXED_FIELDS,
    GROUPS,
    MAP_HEIGHT,
    MAP_WIDTH,
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


# the settings the overview pane's overlays follow: the bands, the zone settings
# of every profile, and the profile itself
BAND_FIELDS = tuple(f"{name}_band" for name in BIOME_BANDS)
ZONE_FIELDS = tuple(dict.fromkeys(
    setting for handles in PROFILE_HANDLES.values() for setting, _index in handles
))
OVERLAY_FIELDS = BAND_FIELDS + ZONE_FIELDS + ("temperature_profile",)

# the overlay's geometry, in viewport pixels: a temperature bar and one bar per
# biome stand along the left edge of the map region, their names above them
BAR_WIDTH = 18       # the temperature bar and each biome bar
BAR_GAP = 8          # between biome bars
BAR_MARGIN = 3       # inside the map border
BAR_GROUP_GAP = 8    # between the temperature bar and the first biome bar
HANDLE_RADIUS = 6    # the round handle at every boundary
HANDLE_REACH = 7     # how far from a boundary a press still takes its handle
BAND_STEP = 0.01     # a dragged boundary snaps to the form's step
COLD, MILD, WARM = QColor(30, 90, 255), QColor(255, 235, 40), QColor(235, 25, 25)


@dataclass(frozen=True)
class Track:
    """One bar of the overlay: its rect, its colour and label, and its chain of
    boundaries from top to bottom as (setting, index) pairs whose values come from
    the form. A biome bar's chain is its band's two edges; the temperature bar's is
    the active profile's zone boundaries."""

    key: str
    rect: QRectF
    chain: tuple[tuple[str, int], ...]
    colour: QColor
    label: str


@dataclass
class Drag:
    """What the pointer has hold of on a track: one handle, by its index in the
    chain (several indices when handles coincide, until the first movement picks
    one), or the stretch between two consecutive handles. `start_y` and `start`
    remember the press position and the chain's values at that moment."""

    track: Track
    handles: list[int] | None = None
    stretch: tuple[int, int] | None = None
    start_y: float = 0.0
    start: tuple[float, ...] = ()


class PreviewView(QGraphicsView):
    """The overview image pane: fits the image on load, drags to pan, wheel zooms.

    Until an image arrives it shows the map's outline at the overview's scale, and
    two overlays can be drawn along the left edge of the outline or of the image:
    the temperature bar (blue cold, yellow mild, red warm, laid out by the profile
    and its zones) and one narrow bar per biome, in the order the biomes are placed,
    filled where its band allows it. Every boundary on a bar is a handle: dragging
    one emits `handle_dragged`, which the window feeds back into the settings form,
    and the form's changes come back through `set_overlay`. Dragging the stretch
    between two boundaries moves both, so a thin band can still be moved. Hovering
    a bar shows its values and rules its boundaries across the whole map.
    """

    handle_dragged = Signal(str, int, float)   # setting, index within it, new value

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.item = QGraphicsPixmapItem()
        self.scene().addItem(self.item)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self.setMouseTracking(True)
        self._has_image = False
        self.scene().setSceneRect(
            QRectF(0, 0, MAP_WIDTH / OVERVIEW_SCALE, MAP_HEIGHT / OVERVIEW_SCALE)
        )
        self.values: dict[str, tuple[float, ...]] = {}   # every overlay setting, by name
        self.profile = "north"
        self.show_bands = True
        self.show_temperature = True
        self.hover: str | None = None      # the key of the track under the pointer
        self.drag: Drag | None = None

    def set_image(self, path: Path) -> bool:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return False
        self.item.setPixmap(pixmap)
        self.scene().setSceneRect(self.item.boundingRect())
        self._has_image = True
        self.fit_image()
        return True

    def map_rect(self) -> QRectF:
        """The map's extent in scene coordinates: the image, or the outline."""
        return self.item.boundingRect() if self._has_image else self.sceneRect()

    def fit_image(self) -> None:
        self.fitInView(self.map_rect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._has_image:
            self.fit_image()   # the outline always fills the pane; an image keeps its zoom

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.fit_image()

    def wheelEvent(self, event) -> None:
        if not self._has_image:
            return super().wheelEvent(event)
        factor = 1.18 if event.angleDelta().y() > 0 else 1 / 1.18
        self.scale(factor, factor)

    def set_overlay(self, values: dict[str, tuple[float, ...]], profile: str) -> None:
        """The overlay settings (bands and zones, by setting name) and the profile."""
        self.values = {name: tuple(float(v) for v in value) for name, value in values.items()}
        self.profile = profile
        self.viewport().update()

    def set_overlay_visible(self, bands: bool | None = None, temperature: bool | None = None) -> None:
        if bands is not None:
            self.show_bands = bands
        if temperature is not None:
            self.show_temperature = temperature
        self.viewport().update()

    # geometry, all in viewport pixels

    def _area(self) -> QRectF:
        return QRectF(self.mapFromScene(self.map_rect()).boundingRect())

    def _tracks(self, area: QRectF) -> list[Track]:
        """The visible bars, left to right: the temperature bar, then the biomes in
        placement order."""
        tracks = []
        x = area.left() + BAR_MARGIN
        if self.show_temperature:
            chain = tuple(handle for handle in PROFILE_HANDLES[self.profile] if handle[0] in self.values)
            tracks.append(Track("temperature", QRectF(x, area.top(), BAR_WIDTH, area.height()), chain, WARM, "Temp"))
            x += BAR_WIDTH + BAR_GROUP_GAP
        if self.show_bands:
            for name in BIOME_BANDS:
                setting = f"{name}_band"
                if setting in self.values:
                    colour = QColor(*OVERVIEW_PALETTE[BIOME_MATERIAL[name]])
                    rect = QRectF(x, area.top(), BAR_WIDTH, area.height())
                    tracks.append(Track(name, rect, ((setting, 0), (setting, 1)), colour, name.capitalize()))
                    x += BAR_WIDTH + BAR_GAP
        return tracks

    def _value(self, handle) -> float:
        setting, index = handle
        return min(1.0, max(0.0, self.values[setting][index]))

    @staticmethod
    def _edge_y(area: QRectF, value: float) -> float:
        return area.top() + value * area.height()

    def _track_at(self, pos) -> Track | None:
        for track in self._tracks(self._area()):
            if track.rect.adjusted(-2, 0, 2, 0).contains(pos):
                return track
        return None

    def _grab_at(self, pos) -> Drag | None:
        """What a press at `pos` would take hold of: the nearest handle within reach
        (all of them when several coincide there), else the stretch the pointer is
        on, else None."""
        track = self._track_at(pos)
        if track is None or not track.chain:
            return None
        area = self._area()
        start = tuple(self._value(handle) for handle in track.chain)
        ys = [self._edge_y(area, value) for value in start]
        near = [i for i, y in enumerate(ys) if abs(pos.y() - y) <= HANDLE_REACH]
        if near:
            best = min(abs(pos.y() - ys[i]) for i in near)
            handles = [i for i in near if abs(pos.y() - ys[i]) - best < 0.5]
            return Drag(track, handles=handles, start_y=pos.y(), start=start)
        for i in range(len(ys) - 1):
            if ys[i] < pos.y() < ys[i + 1]:
                return Drag(track, stretch=(i, i + 1), start_y=pos.y(), start=start)
        return None

    # the mouse: handles and stretches first, then the pane's own pan

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            grab = self._grab_at(event.position())
            if grab is not None:
                self.drag = grab
                self.viewport().update()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.drag is not None:
            self._drag_to(event.position())
            event.accept()
            return
        track = self._track_at(event.position())
        hover = track.key if track else None
        if hover != self.hover:
            self.hover = hover
            self.viewport().update()
        if event.buttons() == Qt.MouseButton.NoButton:   # never during a pan
            grab = self._grab_at(event.position())
            cursor = Qt.CursorShape.OpenHandCursor
            if grab is not None:
                cursor = Qt.CursorShape.SizeVerCursor if grab.handles else Qt.CursorShape.SizeAllCursor
            self.viewport().setCursor(cursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.drag is not None:
            self.drag = None
            self.viewport().update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        if self.hover is not None:
            self.hover = None
            self.viewport().update()
        super().leaveEvent(event)

    def _drag_to(self, pos) -> None:
        """Move what is being dragged to the pointer, snapped to the form's step: a
        handle stays between its neighbours (coincident handles part in the direction
        of the first movement), a stretch keeps its length and stays between the
        boundaries around it or the map edges."""
        drag = self.drag
        chain = drag.track.chain
        start = drag.start
        area = self._area()
        height = area.height() or 1.0
        lat = min(1.0, max(0.0, (pos.y() - area.top()) / height))
        if drag.handles is not None:
            if len(drag.handles) > 1:
                dy = pos.y() - drag.start_y
                if abs(dy) < 1:
                    return
                drag.handles = [min(drag.handles) if dy < 0 else max(drag.handles)]
            i = drag.handles[0]
            low = self._value(chain[i - 1]) if i > 0 else 0.0
            high = self._value(chain[i + 1]) if i + 1 < len(chain) else 1.0
            value = min(max(self._snap(lat), low), high)
            self.handle_dragged.emit(chain[i][0], chain[i][1], value)
            return
        a, b = drag.stretch
        delta = lat - min(1.0, max(0.0, (drag.start_y - area.top()) / height))
        low = self._value(chain[a - 1]) if a > 0 else 0.0
        high = self._value(chain[b + 1]) if b + 1 < len(chain) else 1.0
        delta = min(max(delta, low - start[a]), high - start[b])
        new_a, new_b = self._snap(start[a] + delta), self._snap(start[b] + delta)
        order = ((b, new_b), (a, new_a)) if delta > 0 else ((a, new_a), (b, new_b))
        for i, value in order:                  # the leading edge first, so they never cross
            self.handle_dragged.emit(chain[i][0], chain[i][1], value)

    @staticmethod
    def _snap(value: float) -> float:
        return round(min(1.0, max(0.0, round(value / BAND_STEP) * BAND_STEP)), 2)

    # painting

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if not (self.show_bands or self.show_temperature):
            return
        # drawn in viewport pixels, so bars and captions keep their size at any zoom
        area = self._area()
        tracks = self._tracks(area)
        painter.save()
        painter.setWorldMatrixEnabled(False)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = painter.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
        painter.setFont(font)
        active = self.drag.track.key if self.drag is not None else self.hover
        self._draw_rules(painter, area, tracks, active)
        for track in tracks:
            if track.key == "temperature":
                self._draw_temperature(painter, track)
            else:
                self._draw_band(painter, area, track, track.key == active)
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(area)
        # the handles sit over the border, so one at 0 or 1 stays visible
        for track in tracks:
            self._draw_grips(painter, area, track, track.key == active)
        self._draw_captions(painter, area, tracks, active)
        self._draw_labels(painter, area, tracks, active)
        painter.restore()

    def _draw_temperature(self, painter: QPainter, track: Track) -> None:
        """The temperature bar: the profile's gradient between its zone boundaries."""
        bar = track.rect
        bounds = sorted(self._value(handle) for handle in track.chain)
        gradient = QLinearGradient(bar.topLeft(), bar.bottomLeft())
        if self.profile == "poles" and len(bounds) == 4:
            cold_to, hot_from, hot_to, cold_from = bounds
            stops = ((0.0, COLD), (cold_to, COLD), ((cold_to + hot_from) / 2, MILD), (hot_from, WARM),
                     (hot_to, WARM), ((hot_to + cold_from) / 2, MILD), (cold_from, COLD), (1.0, COLD))
        else:
            cold_to, hot_from = (bounds + [0.0, 1.0])[:2]
            stops = ((0.0, COLD), (cold_to, COLD), ((cold_to + hot_from) / 2, MILD), (hot_from, WARM), (1.0, WARM))
        for at, colour in stops:
            gradient.setColorAt(at, colour)
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.setBrush(QBrush(gradient))
        painter.drawRect(bar)

    def _draw_band(self, painter: QPainter, area: QRectF, track: Track, active: bool) -> None:
        """A biome bar: the whole bar faintly, the band solid."""
        bar = track.rect
        top, bottom = sorted(self._value(handle) for handle in track.chain)
        track_fill = QColor(track.colour)
        track_fill.setAlpha(70)
        painter.setPen(QPen(QColor(0, 0, 0, 170), 1))
        painter.setBrush(track_fill)
        painter.drawRect(bar)
        band = QRectF(bar.left(), self._edge_y(area, top), bar.width(), (bottom - top) * area.height())
        fill = QColor(track.colour)
        fill.setAlpha(255 if active else 215)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRect(band)

    def _draw_grips(self, painter: QPainter, area: QRectF, track: Track, active: bool) -> None:
        """A round handle at every boundary of the track's chain."""
        painter.setPen(QPen(QColor(0, 0, 0), 1.5))
        painter.setBrush(QColor(255, 255, 255) if active else QColor(225, 225, 225))
        radius = HANDLE_RADIUS + (1 if active else 0)
        for handle in track.chain:
            centre = QPointF(track.rect.center().x(), self._edge_y(area, self._value(handle)))
            painter.drawEllipse(centre, radius, radius)

    def _draw_rules(self, painter: QPainter, area: QRectF, tracks: list[Track], active: str | None) -> None:
        """The active track's boundaries ruled across the whole map, a biome's band
        also tinted."""
        track = next((t for t in tracks if t.key == active), None)
        if track is None or not track.chain:
            return
        ys = [self._edge_y(area, self._value(handle)) for handle in track.chain]
        if track.key != "temperature":
            tint = QColor(track.colour)
            tint.setAlpha(45)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tint)
            painter.drawRect(QRectF(area.left(), min(ys), area.width(), max(ys) - min(ys)))
        painter.setPen(QPen(QColor(255, 255, 255), 1.5, Qt.PenStyle.DashLine))
        for y in ys:
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))

    def _draw_captions(self, painter: QPainter, area: QRectF, tracks: list[Track], active: str | None) -> None:
        """The active track's values, right of every bar so they cover no bar, kept
        inside the map region."""
        track = next((t for t in tracks if t.key == active), None)
        if track is None or not track.chain:
            return
        x = max(t.rect.right() for t in tracks) + 8
        half = (painter.fontMetrics().height() + 4) / 2
        for handle in track.chain:
            value = self._value(handle)
            y = min(max(self._edge_y(area, value), area.top() + half), area.bottom() - half)
            self._caption(painter, x, y, f"{value:.2f}")

    def _draw_labels(self, painter: QPainter, area: QRectF, tracks: list[Track], active: str | None) -> None:
        """Each bar's name centred above it, in two staggered rows so neighbours never
        collide, kept inside the map region; the active bar's name bold on a lit pill,
        drawn last so it stands over its neighbours."""
        plain = painter.font()
        bold = QFont(plain)
        bold.setBold(True)
        metrics = painter.fontMetrics()
        height = metrics.height() + 4
        order = sorted(enumerate(tracks), key=lambda item: item[1].key == active)
        for index, track in order:
            lit = track.key == active
            painter.setFont(bold if lit else plain)
            width = painter.fontMetrics().horizontalAdvance(track.label) + 8
            x = track.rect.center().x() - width / 2
            x = min(max(x, area.left() + 2), area.right() - width - 2)
            y = area.top() + 3 + (index % 2) * (height + 2)
            box = QRectF(x, y, width, height)
            painter.setPen(QPen(QColor(255, 255, 255), 1) if lit else Qt.PenStyle.NoPen)
            painter.setBrush(QColor(track.colour).lighter(115) if lit else QColor(0, 0, 0, 170))
            painter.drawRoundedRect(box, 3, 3)
            painter.setPen(QColor(0, 0, 0) if lit else QColor(255, 255, 255))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, track.label)
        painter.setFont(plain)

    @staticmethod
    def _caption(painter: QPainter, x: float, y: float, text: str) -> None:
        """White text on a dark pill, centred vertically on `y`, starting at `x`."""
        metrics = painter.fontMetrics()
        box = QRectF(x, y - (metrics.height() + 4) / 2, metrics.horizontalAdvance(text) + 8, metrics.height() + 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 170))
        painter.drawRoundedRect(box, 3, 3)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)


# the setting groups, in reading order down the left column and then the right
COLUMNS = ((WORLD, CONTINENT, COAST, WATER), (ELEVATION, BIOMES, TOWNS))


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

    biome_changed = Signal()   # a band, a zone or the temperature profile was edited

    def __init__(self):
        super().__init__()
        # a scalar setting maps to its box; a pair setting to a tuple of boxes
        self.widgets: dict[str, QWidget | tuple[QWidget, ...]] = {}
        self._rows: dict[str, tuple[QFormLayout, QWidget]] = {}   # a setting's form and row field
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
                settings = settings_in(group)
                fields = {s.name: self._field(s, defaults[s.name]) for s in settings}
                for setting in settings:
                    if setting.beside:
                        continue
                    field = fields[setting.name]
                    joined = [s for s in settings if s.beside == setting.name]
                    if joined:
                        # one row for a setting and the settings drawn beside it
                        row = QWidget()
                        layout = QHBoxLayout(row)
                        layout.setContentsMargins(0, 0, 0, 0)
                        layout.addWidget(field, 1)
                        for extra in joined:
                            tag = QLabel(extra.short)
                            tag.setToolTip(tooltip_html(extra))
                            layout.addSpacing(6)
                            layout.addWidget(tag)
                            layout.addWidget(fields[extra.name], 2)
                        field = row
                    form.addRow(self._label(setting), field)
                    self._rows[setting.name] = (form, field)
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
        profile = self.widgets["temperature_profile"]
        assert isinstance(profile, QComboBox)
        profile.currentIndexChanged.connect(self._sync_profile_rows)
        self._sync_profile_rows()

    def _sync_profile_rows(self) -> None:
        """Show only the zone rows of the selected temperature profile."""
        profile = self.widgets["temperature_profile"]
        assert isinstance(profile, QComboBox)
        current = profile.currentData()
        for setting in SETTINGS:
            if setting.profile and setting.name in self._rows:
                form, field = self._rows[setting.name]
                row, _role = form.getWidgetPosition(field)
                form.setRowVisible(row, setting.profile == current)

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
        if setting.choices:
            combo = QComboBox()
            for value, label in setting.choices:
                combo.addItem(label, value)
            combo.setCurrentIndex(combo.findData(default))
            combo.setToolTip(tooltip_html(setting))
            combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            combo.installEventFilter(self._wheel_guard)
            if setting.name in OVERLAY_FIELDS:
                combo.currentIndexChanged.connect(self.biome_changed)
            self.widgets[setting.name] = combo
            return combo
        if setting.parts:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            boxes = []
            for part, value in zip(setting.parts, default):
                layout.addWidget(QLabel(part))
                spin = self._spin(setting, value)
                if setting.name in OVERLAY_FIELDS:
                    spin.valueChanged.connect(self.biome_changed)
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
            if setting.choices:
                assert isinstance(widget, QComboBox)
                result[setting.name] = widget.currentData()
            elif setting.parts:
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
            if setting.choices:
                assert isinstance(widget, QComboBox)
                widget.setCurrentIndex(widget.findData(value))
            elif setting.parts:
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

    def set_part(self, name: str, index: int, value: float) -> None:
        """A handle was dragged in the overview pane: put its value in the box."""
        spins = self.widgets[name]
        spins[index].setValue(value)

    def overlay_state(self) -> tuple[dict[str, tuple[float, ...]], str]:
        """The bands, the zones and the temperature profile as the boxes show them
        right now, unvalidated, for the overview pane's overlays."""
        values = {
            name: tuple(spin.value() for spin in self.widgets[name])
            for name in BAND_FIELDS + ZONE_FIELDS
        }
        combo = self.widgets["temperature_profile"]
        assert isinstance(combo, QComboBox)
        return values, combo.currentData()


class MainWindow(QMainWindow):
    """The main window. `process`/`queue` are the running child process and its event
    queue (None when idle); `active_*` describe the job it is running."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ultima Online Procedural Map Generator")
        self.resize(1280, 960)
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
        self.bands_toggle = QCheckBox("Show biome bands")
        self.bands_toggle.setChecked(True)
        self.bands_toggle.setToolTip(
            "Stand one bar per biome along the left edge of the map in the overview pane, "
            "in the order the biomes are placed, filled where its band allows it. Drag the "
            "handle at either end of a band to move that edge, or drag the band itself to "
            "move the whole of it; hover a bar to read its values and see the band ruled "
            "across the map. Generating a preview or a world switches this off so the new "
            "map shows unobstructed; tick it again to draw the bars over the map."
        )
        self.temperature_toggle = QCheckBox("Show temperature profile")
        self.temperature_toggle.setChecked(True)
        self.temperature_toggle.setToolTip(
            "Stand the temperature bar along the left edge of the map in the overview pane: "
            "blue is cold, yellow mild and red warm, laid out as the selected temperature "
            "profile and its zones have it. Drag a handle to move where the full cold or the "
            "full heat ends, or drag the stretch between two handles to move both. "
            "Generating a preview or a world switches it off; tick it again to draw it over "
            "the map."
        )
        self.open_button = QPushButton("Open Output Folder")
        self.uo_button = QPushButton("Select UO Folder")
        self.output_button = QPushButton("Choose Output Folder")

        self.preview_button.clicked.connect(self.generate_preview)
        self.world_button.clicked.connect(self.generate_world)
        self.cancel_button.clicked.connect(self.cancel_job)
        self.fit_button.clicked.connect(self.preview.fit_image)
        self.bands_toggle.toggled.connect(
            lambda on: self.preview.set_overlay_visible(bands=on)
        )
        self.temperature_toggle.toggled.connect(
            lambda on: self.preview.set_overlay_visible(temperature=on)
        )
        self.form.biome_changed.connect(self.refresh_overlay)
        self.preview.handle_dragged.connect(self.form.set_part)
        self.refresh_overlay()
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
        preview_tools = QHBoxLayout()
        preview_tools.addWidget(self.bands_toggle)
        preview_tools.addWidget(self.temperature_toggle)
        preview_tools.addStretch(1)
        preview_tools.addWidget(self.fit_button)
        preview_layout.addLayout(preview_tools)

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

    def refresh_overlay(self) -> None:
        """A band, a zone or the profile changed: redraw the overlays from the form."""
        values, profile = self.form.overlay_state()
        self.preview.set_overlay(values, profile)

    def hide_overlays(self) -> None:
        """Generating: the new map must show unobstructed. The check boxes under the
        pane bring the overlays back, over the map."""
        self.bands_toggle.setChecked(False)
        self.temperature_toggle.setChecked(False)

    def generate_preview(self) -> None:
        """Generate Preview: reuse the cached image for these exact settings, else
        render one in a child process."""
        self.hide_overlays()
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
        self.hide_overlays()
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
