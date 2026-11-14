"""The mini window: a small always-on-top chest counter, like a scoreboard in the corner of the screen."""

import ctypes
import random

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction, QColor, QFont, QFontMetricsF, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QMenu, QWidget

from widgets import ASH, BONE, EMBER, GOLD, GOLD_LIGHT, MINT


BASE_WIDTH, BASE_HEIGHT = 236, 118
MIN_SCALE, MAX_SCALE = 0.7, 2.0
MIN_OPACITY, MAX_OPACITY = 0.3, 1.0

PANEL = QColor(38, 42, 52, 228)
PANEL_EDGE = QColor(255, 255, 255, 22)
LABEL_GOLD = "#F6C445"
OUTLINE = QColor(10, 11, 14, 235)
LOCK_AREA = QRectF(6, 40, 34, 40)


def clamp(value, low: float, high: float, default: float) -> float:
    """A setting from a file that may have been edited by hand: always lands in range."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return min(high, max(low, number))


def score_font(size: float) -> QFont:
    """Bold, condensed and slanted, like a game scoreboard. Bahnschrift ships with Windows 10 and 11."""
    font = QFont(["Bahnschrift Bold Condensed", "Bahnschrift", "Segoe UI"])
    font.setWeight(QFont.Weight.Bold)
    font.setItalic(True)
    font.setPixelSize(max(1, int(size)))
    return font


class ChestOverlay(QWidget):
    """The mini window. Unlock it with the lock to drag it; while Fortnite is in front, clicks pass through."""

    position_saved = Signal(object)
    lock_toggled = Signal(bool)
    open_requested = Signal()
    hide_requested = Signal()

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setWindowTitle("Chest Tracker mini window")
        self.scale = 1.0
        self.opacity = 1.0
        self.setFixedSize(BASE_WIDTH, BASE_HEIGHT)
        self.count = 0
        self.today = 0
        self.session = 0
        self.paused = False
        self.positioning = False
        self.locked = True
        self.click_through = False
        self._hover_lock = False
        self._drag_offset: QPoint | None = None
        self._particles: list[list[float | QColor]] = []
        self._flash = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    # Settings ------------------------------------------------------------------------------

    def set_scale(self, scale: float) -> None:
        self.scale = clamp(scale, MIN_SCALE, MAX_SCALE, 1.0)
        self.setFixedSize(round(BASE_WIDTH * self.scale), round(BASE_HEIGHT * self.scale))
        self.update()

    def set_opacity(self, opacity: float) -> None:
        self.opacity = clamp(opacity, MIN_OPACITY, MAX_OPACITY, 1.0)
        self.update()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self.update()

    def set_locked(self, locked: bool) -> None:
        self.locked = bool(locked)
        self._update_cursor()
        self.update()

    def set_details(self, today: int, session: int) -> None:
        self.today, self.session = today, session
        self.update()

    def set_count(self, count: int, celebrate: bool = False) -> None:
        self.count = count
        if celebrate:
            colors = [QColor(GOLD), QColor(GOLD_LIGHT), QColor(LABEL_GOLD), QColor(BONE)]
            for _ in range(26):
                self._particles.append([
                    random.uniform(90, BASE_WIDTH - 20),
                    random.uniform(20, 50),
                    random.uniform(-2.8, 2.8),
                    random.uniform(-5.4, -1.0),
                    1.0,
                    random.choice(colors),
                ])
            self._flash = 1.0
            self._timer.start()
        self.update()

    # Windows ---------------------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._hide_from_screen_capture()

    def _hide_from_screen_capture(self) -> None:
        """Keep the mini window out of screenshots, so the tracker never mistakes it for part of the game.

        The tracker reads the screen to find the SEARCH prompt. Without this, a window dragged
        over the middle of the screen would be part of every frame it checks. Needs Windows 10
        version 2004 or newer; on older versions the call fails and nothing changes.
        """
        try:
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            display_affinity = ctypes.windll.user32.SetWindowDisplayAffinity
            display_affinity.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            display_affinity(int(self.winId()), WDA_EXCLUDEFROMCAPTURE)
        except (AttributeError, OSError):
            pass

    def set_click_through(self, enabled: bool) -> None:
        """Use Windows extended styles so mouse input passes through the mini window."""
        if enabled == self.click_through:
            return
        self.click_through = enabled
        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        get_style = user32.GetWindowLongW
        set_style = user32.SetWindowLongW
        get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
        get_style.restype = ctypes.c_long
        set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
        user32.SetWindowPos.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_uint,
        ]
        style = get_style(hwnd, -20)  # GWL_EXSTYLE
        transparent = 0x00000020  # WS_EX_TRANSPARENT
        style = style | transparent if enabled else style & ~transparent
        set_style(hwnd, -20, style)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0037)  # refresh style, without moving or activating

    # Mouse ----------------------------------------------------------------------------------

    def _can_drag(self) -> bool:
        return self.positioning or not self.locked

    def _on_lock(self, position: QPointF) -> bool:
        return LOCK_AREA.contains(QPointF(position.x() / self.scale, position.y() / self.scale))

    def _update_cursor(self) -> None:
        if self._hover_lock:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif self._can_drag():
            self.setCursor(Qt.CursorShape.ClosedHandCursor if self._drag_offset else Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        if self._on_lock(event.position()):
            self.set_locked(not self.locked)
            self.lock_toggled.emit(self.locked)
            event.accept()
            return
        if self._can_drag():
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._update_cursor()
            event.accept()
            return
        event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        hovering = self._on_lock(event.position())
        if hovering != self._hover_lock:
            self._hover_lock = hovering
            self._update_cursor()
            self.update()
        event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self._update_cursor()
            self.position_saved.emit(self.pos())
            event.accept()
            return
        event.ignore()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if not self._on_lock(event.position()):
            self.open_requested.emit()
        event.accept()

    def leaveEvent(self, event) -> None:
        if self._hover_lock:
            self._hover_lock = False
            self._update_cursor()
            self.update()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1B1E23; border: 1px solid #30343C; border-radius: 8px; padding: 4px; color: #ECEDEF; }"
            "QMenu::item { padding: 7px 22px; border-radius: 5px; }"
            "QMenu::item:selected { background: #2A2E36; }"
        )
        open_app = QAction("Open Chest Tracker", menu)
        open_app.triggered.connect(self.open_requested.emit)
        lock = QAction("Unlock to move" if self.locked else "Lock in place", menu)
        lock.triggered.connect(lambda: (self.set_locked(not self.locked), self.lock_toggled.emit(self.locked)))
        hide = QAction("Hide mini window", menu)
        hide.triggered.connect(self.hide_requested.emit)
        for action in (open_app, lock, hide):
            menu.addAction(action)
        menu.exec(event.globalPos())

    # Painting -------------------------------------------------------------------------------

    def _outlined_text(self, painter: QPainter, font: QFont, right: float, baseline: float, parts) -> float:
        """Right-aligned text with a dark outline, so it reads over any background. `parts` is [(text, color)]."""
        metrics = QFontMetricsF(font)
        x = right - sum(metrics.horizontalAdvance(text) for text, _ in parts)
        for text, color in parts:
            path = QPainterPath()
            path.addText(QPointF(x, baseline), font, text)
            painter.strokePath(path, QPen(OUTLINE, max(2.0, font.pixelSize() * 0.11), Qt.PenStyle.SolidLine,
                                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.fillPath(path, QColor(color))
            x += metrics.horizontalAdvance(text)
        return x

    def _paint_chest_icon(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.setPen(QPen(OUTLINE, 1.6))
        lid = QPainterPath()
        lid.moveTo(rect.left(), rect.top() + rect.height() * 0.45)
        lid.lineTo(rect.left(), rect.top() + rect.height() * 0.3)
        lid.cubicTo(rect.left(), rect.top() - rect.height() * 0.05, rect.right(), rect.top() - rect.height() * 0.05,
                    rect.right(), rect.top() + rect.height() * 0.3)
        lid.lineTo(rect.right(), rect.top() + rect.height() * 0.45)
        lid.closeSubpath()
        shade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        shade.setColorAt(0, QColor("#FFD866"))
        shade.setColorAt(1, QColor("#E39B17"))
        painter.setBrush(shade)
        painter.drawPath(lid)
        body = QRectF(rect.left(), rect.top() + rect.height() * 0.5, rect.width(), rect.height() * 0.5)
        painter.drawRoundedRect(body, 2.5, 2.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(OUTLINE)
        clasp = QRectF(rect.center().x() - rect.width() * 0.09, rect.top() + rect.height() * 0.36,
                       rect.width() * 0.18, rect.height() * 0.26)
        painter.drawRoundedRect(clasp, 1.5, 1.5)
        painter.restore()

    def _paint_lock(self, painter: QPainter) -> None:
        center = LOCK_AREA.center()
        color = QColor(GOLD_LIGHT if not self.locked else (BONE if self._hover_lock else ASH))
        if self._hover_lock:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 20))
            painter.drawRoundedRect(LOCK_AREA.adjusted(4, 4, -4, -4), 6, 6)
        painter.setPen(QPen(color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        body = QRectF(center.x() - 7, center.y() - 1, 14, 11)
        painter.drawRoundedRect(body, 2.5, 2.5)
        shackle = QPainterPath()
        lift = 0 if self.locked else 4
        shackle.moveTo(center.x() - 4.5, center.y() - 1)
        shackle.lineTo(center.x() - 4.5, center.y() - 5 - lift)
        shackle.arcTo(QRectF(center.x() - 4.5, center.y() - 10 - lift, 9, 9), 180, -180)
        if self.locked:
            shackle.lineTo(center.x() + 4.5, center.y() - 1)
        painter.drawPath(shackle)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self.opacity)
        painter.scale(self.scale, self.scale)  # everything below is drawn at the base size

        panel = QRectF(1, 1, BASE_WIDTH - 2, BASE_HEIGHT - 2)
        painter.setPen(QPen(QColor(MINT) if self._can_drag() else PANEL_EDGE, 1.4 if self._can_drag() else 1))
        painter.setBrush(PANEL)
        painter.drawRoundedRect(panel, 12, 12)
        if self._flash > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(246, 196, 69, int(self._flash * 60)))
            painter.drawRoundedRect(panel, 12, 12)

        right = BASE_WIDTH - 16
        big = score_font(46)
        number = f"{self.count:,}"
        number_left = right - QFontMetricsF(big).horizontalAdvance(number)
        self._paint_chest_icon(painter, QRectF(number_left - 40, 20, 30, 24))
        self._outlined_text(painter, big, right, 50, [(number, "#FFFFFF")])

        rows = score_font(21)
        if self.positioning or self._drag_offset is not None:
            self._outlined_text(painter, rows, right, 80, [("Drag to place", MINT)])
            self._outlined_text(painter, rows, right, 104, [("Lock when done", ASH)])
        elif self.paused:
            self._outlined_text(painter, rows, right, 80, [("Paused", EMBER)])
            self._outlined_text(painter, rows, right, 104, [("Session · ", LABEL_GOLD), (f"{self.session:,}", BONE)])
        else:
            self._outlined_text(painter, rows, right, 80, [("Today · ", LABEL_GOLD), (f"{self.today:,}", BONE)])
            self._outlined_text(painter, rows, right, 104, [("Session · ", LABEL_GOLD), (f"{self.session:,}", BONE)])

        self._paint_lock(painter)

        for x, y, _vx, _vy, life, color in self._particles:
            painter.setPen(Qt.PenStyle.NoPen)
            particle = QColor(color)
            particle.setAlphaF(max(0.0, float(life)))
            painter.setBrush(particle)
            painter.drawEllipse(QRectF(float(x), float(y), 5, 5))
        painter.end()

    def _tick(self) -> None:
        for particle in self._particles:
            particle[0] = float(particle[0]) + float(particle[2])
            particle[1] = float(particle[1]) + float(particle[3])
            particle[3] = float(particle[3]) + 0.22
            particle[4] = float(particle[4]) - 0.025
        self._particles = [p for p in self._particles if float(p[4]) > 0]
        self._flash = max(0.0, self._flash - 0.045)
        if not self._particles and self._flash == 0:
            self._timer.stop()
        self.update()
