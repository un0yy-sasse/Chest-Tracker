"""The app's hand-drawn pieces: the chest stage, tally marks, match meter and leaderboard rows."""

import ctypes
import math
import random
from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QKeyEvent, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

# Graphite: near-black surfaces, quiet greys, off-white for primary actions and a single
# champagne gold kept for the loot itself. MINT and EMBER are only for "working" and "problem".
NIGHT = "#0B0C0E"  # page background
SIDEBAR = "#0E0F12"  # navigation column
DUSK = "#131519"  # cards and panels
RAISED = "#1B1E23"  # hovered buttons and menu items
LINE = "#23262D"  # borders
LINE_STRONG = "#30343C"  # input and button borders
ACCENT = "#ECEDEF"  # primary buttons
ACCENT_LIGHT = "#FFFFFF"
ACCENT_DEEP = "#C4C7CD"
CYAN = "#9AA0AA"  # secondary figures
GOLD = "#D8B46E"  # chests and chest counts
GOLD_LIGHT = "#ECD3A1"  # highlights
GOLD_DEEP = "#8A6A2F"  # pressed states and coin edges
BONE = "#ECEDEF"  # main text
ASH = "#8B919B"  # secondary text
FAINT = "#5B606A"  # captions and axis labels
MINT = "#45B98E"
EMBER = "#EF6A62"
INK = "#08090B"  # outlines and the chest's dark body

FONT_UI = '"Segoe UI Variable Text", "Segoe UI"'
FONT_DISPLAY = "Segoe UI Variable Display"


def display_font(size: float, weight: str = "SemiBold") -> QFont:
    """Segoe UI Variable ships with Windows 11; Windows 10 falls back to Segoe UI."""
    font = QFont([FONT_DISPLAY, "Segoe UI"])
    font.setWeight(QFont.Weight.Bold if weight == "Bold" else QFont.Weight.DemiBold)
    font.setPixelSize(max(1, int(size)))
    return font


def animations_enabled() -> bool:
    """False when the player turned off animation effects in Windows."""
    enabled = ctypes.c_int(1)
    ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
    return bool(enabled.value)


@dataclass
class Coin:
    x: float
    y: float
    vx: float
    vy: float
    spin: float
    size: float
    life: float = 1.0


class ChestStage(QWidget):
    """A compact live view: a chest that reacts to what the tracker sees."""

    HOVER_LID = 0.14
    PENDING_LID = 0.3

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(240, 210)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setAccessibleName("Chests opened: 0")
        self.count = 0
        self.lid = 0.0
        self.lid_speed = 0.0
        self.lid_target = 0.0
        self.resting_lid = 0.0
        self.searching = False
        self.flash = 0.0
        self.shake = 0.0
        self.pop = 0.0
        self.wobble = 0.0
        self.coins: list[Coin] = []
        self.animate = animations_enabled()
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.close_timer = QTimer(self)
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self._settle)

    def set_count(self, count: int) -> None:
        self.count = count
        self.setAccessibleName(f"Chests opened: {count:,}")
        self.update()

    def show_pending(self) -> None:
        """A search looks real so far: the lid lifts while the app confirms it."""
        self.searching = True
        self.close_timer.stop()
        self._move_lid(self.PENDING_LID)

    def show_opened(self, count: int) -> None:
        self.searching = False
        self.set_count(count)
        self._move_lid(1.0)
        if self.animate:
            self.flash = 1.0
            self.pop = 1.0
            self._burst()
            self.timer.start()
        self.close_timer.start(1500)

    def show_cancelled(self) -> None:
        self.searching = False
        self.close_timer.stop()
        self._move_lid(self.resting_lid)
        if self.animate:
            self.shake = 1.0
            self.timer.start()

    def _settle(self) -> None:
        self._move_lid(self.resting_lid)

    def _move_lid(self, target: float) -> None:
        self.lid_target = target
        if self.animate:
            self.timer.start()
        else:
            self.lid = target
            self.update()

    def enterEvent(self, event) -> None:
        self.resting_lid = self.HOVER_LID
        if not self.searching and not self.close_timer.isActive():
            self._move_lid(self.resting_lid)

    def leaveEvent(self, event) -> None:
        self.resting_lid = 0.0
        if not self.searching and not self.close_timer.isActive():
            self._move_lid(0.0)

    def _burst(self) -> None:
        center, _, width = self._chest_box()
        for _ in range(34):
            angle = random.uniform(-2.65, -0.5)
            speed = random.uniform(0.34, 0.95) * width * 0.052
            self.coins.append(Coin(
                center + random.uniform(-0.2, 0.2) * width,
                self._body_top(),
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                random.uniform(0, 6.28),
                random.uniform(0.018, 0.034) * width,
            ))

    def _tick(self) -> None:
        # A lightly damped spring, so the lid overshoots and slams like something with weight.
        self.lid_speed += (self.lid_target - self.lid) * 0.075
        self.lid_speed *= 0.76
        self.lid += self.lid_speed
        self.flash = max(0.0, self.flash - 0.024)
        self.shake = max(0.0, self.shake - 0.05)
        self.pop = max(0.0, self.pop - 0.035)
        if self.searching:
            self.wobble += 0.3

        gravity = self._chest_box()[2] * 0.0024
        for coin in self.coins:
            coin.vy += gravity
            coin.x += coin.vx
            coin.y += coin.vy
            coin.spin += 0.3
            coin.life -= 0.016
        self.coins = [coin for coin in self.coins if coin.life > 0]

        at_rest = abs(self.lid_target - self.lid) < 0.002 and abs(self.lid_speed) < 0.002
        if at_rest and not self.searching and not (self.coins or self.flash or self.shake or self.pop):
            self.lid = self.lid_target
            self.timer.stop()
        self.update()

    def _chest_box(self) -> tuple[float, float, float]:
        width = min(self.width() * 0.6, self.height() * 0.6)
        return self.width() * 0.5, self.height() * 0.8, width

    def _body_top(self) -> float:
        _, bottom, width = self._chest_box()
        return bottom - width * 0.42

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_backdrop(p)

        center, bottom, width = self._chest_box()
        if self.shake:
            center += math.sin(self.shake * 26) * self.shake * width * 0.03
        if self.searching:
            center += math.sin(self.wobble) * width * 0.006

        openness = max(0.0, self.lid)
        self._paint_light(p, center, width, openness)
        self._paint_chest(p, center, bottom, width, openness)
        self._paint_coins(p)
        self._paint_count(p)
        p.end()

    def _paint_backdrop(self, p: QPainter) -> None:
        center, bottom, width = self._chest_box()
        glow = QRadialGradient(QPointF(center, bottom - width * 0.25), width * 1.1)
        color = QColor(GOLD)
        color.setAlphaF(0.05 + 0.22 * self.flash)
        glow.setColorAt(0, color)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), QBrush(glow))

        floor = QRadialGradient(QPointF(center, bottom + width * 0.015), width * 0.68)
        floor.setColorAt(0, QColor(0, 0, 0, 150))
        floor.setColorAt(1, QColor(0, 0, 0, 0))
        p.save()
        p.translate(center, bottom + width * 0.015)
        p.scale(1, 0.13)
        p.translate(-center, -(bottom + width * 0.015))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(floor))
        p.drawEllipse(QPointF(center, bottom + width * 0.015), width * 0.68, width * 0.68)
        p.restore()

    def _paint_light(self, p: QPainter, center: float, width: float, openness: float) -> None:
        if openness < 0.03:
            return
        top = self._body_top()
        strength = min(1.0, openness * 1.15) * (0.5 + 0.5 * self.flash)
        p.setPen(Qt.PenStyle.NoPen)
        for offset, reach, spread in ((-0.27, 0.5, 0.15), (0.0, 0.6, 0.2), (0.27, 0.5, 0.15)):
            beam = QPainterPath(QPointF(center + (offset - 0.09) * width, top))
            beam.lineTo(center + (offset * 1.9 - spread) * width, top - reach * width * openness)
            beam.lineTo(center + (offset * 1.9 + spread) * width, top - reach * width * openness)
            beam.lineTo(center + (offset + 0.09) * width, top)
            beam.closeSubpath()
            gradient = QLinearGradient(0, top, 0, top - reach * width * openness)
            near = QColor(GOLD)
            near.setAlphaF(0.72 * strength)
            far = QColor(GOLD)
            far.setAlphaF(0.0)
            gradient.setColorAt(0, near)
            gradient.setColorAt(1, far)
            p.setBrush(QBrush(gradient))
            p.drawPath(beam)

    def _paint_chest(self, p: QPainter, center: float, bottom: float, width: float, openness: float) -> None:
        half = width / 2
        body_top = self._body_top()
        lid_height = width * 0.33
        angle = min(openness, 1.2) * math.radians(112)
        lid_gap = lid_height * 0.72 * math.sin(min(angle, math.pi / 2))
        lid_bottom = body_top - lid_gap
        face = lid_height * math.cos(angle)
        outline = QPen(QColor(INK), width * 0.016)
        outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        # The inside of the chest shows behind the lifting lid.
        if openness > 0.02:
            p.setPen(outline)
            mouth = QLinearGradient(0, lid_bottom, 0, body_top)
            mouth.setColorAt(0, QColor("#0F1013"))
            mouth.setColorAt(1, QColor(GOLD))
            p.setBrush(QBrush(mouth))
            p.drawRect(QRectF(center - half * 0.96, lid_bottom, width * 0.96, body_top - lid_bottom + width * 0.02))

        # Lid.
        p.setPen(outline)
        if face >= 0:
            lid = QPainterPath()
            lid.moveTo(center - half, lid_bottom)
            lid.lineTo(center - half, lid_bottom - face * 0.55)
            lid.cubicTo(
                center - half, lid_bottom - face * 1.05,
                center + half, lid_bottom - face * 1.05,
                center + half, lid_bottom - face * 0.55,
            )
            lid.lineTo(center + half, lid_bottom)
            lid.closeSubpath()
            shade = QLinearGradient(0, lid_bottom - face, 0, lid_bottom)
            shade.setColorAt(0, QColor("#2E323A"))
            shade.setColorAt(1, QColor("#181A1F"))
            p.setBrush(QBrush(shade))
            p.drawPath(lid)
            self._paint_bands(p, center, width, lid_bottom - face * 0.82, lid_bottom)
        else:
            back = QRectF(center - half, lid_bottom + face, width, -face)
            p.setBrush(QColor("#121418"))
            p.drawRoundedRect(back, width * 0.03, width * 0.03)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(GOLD))
            p.drawRect(QRectF(center - half, lid_bottom - width * 0.012, width, width * 0.024))

        # Body with plank lines and metal corners.
        p.setPen(outline)
        planks = QLinearGradient(0, body_top, 0, bottom)
        planks.setColorAt(0, QColor("#24272D"))
        planks.setColorAt(1, QColor("#111316"))
        p.setBrush(QBrush(planks))
        p.drawRoundedRect(QRectF(center - half, body_top, width, bottom - body_top), width * 0.02, width * 0.02)
        p.setPen(QPen(QColor(255, 255, 255, 18), width * 0.008))
        for step in (0.34, 0.67):
            y = body_top + (bottom - body_top) * step
            p.drawLine(QPointF(center - half * 0.96, y), QPointF(center + half * 0.96, y))
        self._paint_bands(p, center, width, body_top, bottom)

        # Rim and clasp ride with the body, so the clasp stays put as the lid lifts.
        p.setPen(outline)
        p.setBrush(QColor(GOLD))
        p.drawRect(QRectF(center - half, body_top - width * 0.012, width, width * 0.042))
        clasp = QRectF(center - width * 0.075, body_top - width * 0.05, width * 0.15, width * 0.17)
        p.setBrush(QColor(GOLD_LIGHT))
        p.drawRoundedRect(clasp, width * 0.024, width * 0.024)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(INK))
        p.drawEllipse(clasp.center(), width * 0.021, width * 0.021)
        p.drawRect(QRectF(clasp.center().x() - width * 0.008, clasp.center().y(), width * 0.016, width * 0.05))

    def _paint_bands(self, p: QPainter, center: float, width: float, top: float, bottom: float) -> None:
        if bottom - top < 1:
            return
        p.setPen(QPen(QColor(INK), width * 0.008))
        p.setBrush(QColor(GOLD))
        for x in (-0.36, 0.36):
            p.drawRect(QRectF(center + (x - 0.04) * width, top, width * 0.08, bottom - top))

    def _paint_coins(self, p: QPainter) -> None:
        for coin in self.coins:
            p.save()
            p.setOpacity(min(1.0, coin.life * 2.2))
            p.translate(coin.x, coin.y)
            flat = abs(math.cos(coin.spin))
            p.setPen(QPen(QColor(GOLD_DEEP), max(1.0, coin.size * 0.16)))
            p.setBrush(QColor(GOLD_LIGHT))
            p.drawEllipse(QPointF(0, 0), max(1.5, coin.size * flat), coin.size)
            p.restore()

    def _paint_count(self, p: QPainter) -> None:
        if self.searching:
            text, color = "Checking this chest…", GOLD
        elif self.close_timer.isActive():
            text, color = "Chest counted", GOLD
        else:
            text, color = "Ready for the next chest", FAINT
        caption = QFont(["Segoe UI Variable Text", "Segoe UI"])
        caption.setPixelSize(12)
        caption.setWeight(QFont.Weight.DemiBold)
        p.setFont(caption)
        p.setPen(QColor(color))
        p.drawText(
            QRectF(0, self.height() - 30, self.width(), 22),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, text,
        )


class TallyMarks(QWidget):
    """Today's chests as groups of five hand-scratched marks."""

    GROUP_WIDTH = 46
    ROW_HEIGHT = 30

    def __init__(self):
        super().__init__()
        self.count = 0
        self.setMinimumHeight(self.ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self.ROW_HEIGHT * 2)

    def set_count(self, count: int) -> None:
        self.count = count
        self.setAccessibleName(f"{count} chests today")
        self.setVisible(count > 0)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        per_row = max(1, self.width() // self.GROUP_WIDTH)
        capacity = per_row * 2 * 5
        shown = min(self.count, capacity)
        rng = random.Random(11)  # the same marks every paint, so they don't jitter
        p.setPen(QPen(QColor(GOLD), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for index in range(shown):
            group, mark = divmod(index, 5)
            row, column = divmod(group, per_row)
            x, top = column * self.GROUP_WIDTH + 3, row * self.ROW_HEIGHT + 4
            if mark < 4:
                lean = rng.uniform(-1.4, 1.4)
                px = x + mark * 8
                p.drawLine(QPointF(px + lean, top), QPointF(px - lean, top + 21))
            else:
                p.drawLine(QPointF(x - 4, top + 17), QPointF(x + 28, top + 4))


class MatchMeter(QWidget):
    """Shows the live prompt match. Drag the marker, or use arrow keys, to set the required match."""

    threshold_changed = Signal(float)
    MIN_THRESHOLD = 0.5
    MAX_THRESHOLD = 0.99

    def __init__(self, threshold: float):
        super().__init__()
        self.score = 0.0
        self.threshold = min(self.MAX_THRESHOLD, max(self.MIN_THRESHOLD, threshold))
        self.setFixedHeight(48)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setToolTip(
            "Required match: 0.50 is more permissive and may cause false matches; "
            "0.99 is stricter and may miss prompts. Drag to change it."
        )
        self.setAccessibleName("Required prompt match")
        self.setAccessibleDescription(
            "The range goes from 0.50, more permissive, to 0.99, stricter."
        )

    def set_score(self, score: float) -> None:
        self.score = max(0.0, min(1.0, score))
        self.update()

    def _track(self) -> QRectF:
        return QRectF(8, 8, self.width() - 16, 9)

    @classmethod
    def _threshold_at_fraction(cls, fraction: float) -> float:
        fraction = min(1.0, max(0.0, fraction))
        value = cls.MIN_THRESHOLD + fraction * (cls.MAX_THRESHOLD - cls.MIN_THRESHOLD)
        return round(value, 2)

    @classmethod
    def _fraction_at_threshold(cls, threshold: float) -> float:
        return (threshold - cls.MIN_THRESHOLD) / (cls.MAX_THRESHOLD - cls.MIN_THRESHOLD)

    def _set_threshold_at(self, x: float) -> None:
        track = self._track()
        fraction = (x - track.left()) / track.width()
        self.threshold = self._threshold_at_fraction(fraction)
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._set_threshold_at(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._set_threshold_at(event.position().x())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.threshold_changed.emit(self.threshold)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        step = {Qt.Key.Key_Left: -0.01, Qt.Key.Key_Right: 0.01}.get(event.key())
        if step is None:
            super().keyPressEvent(event)
            return
        self.threshold = round(
            min(self.MAX_THRESHOLD, max(self.MIN_THRESHOLD, self.threshold + step)), 2
        )
        self.threshold_changed.emit(self.threshold)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = self._track()
        gradient = QLinearGradient(track.topLeft(), track.topRight())
        gradient.setColorAt(0.0, QColor(EMBER))
        gradient.setColorAt(0.5, QColor(GOLD))
        gradient.setColorAt(1.0, QColor(MINT))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(gradient))
        p.drawRoundedRect(track, 4, 4)
        if self.score > 0:
            score_fraction = self._fraction_at_threshold(self.score)
            score_fraction = min(1.0, max(0.0, score_fraction))
            fill = QRectF(track.left(), track.top(), track.width() * score_fraction, track.height())
            score_color = QColor(MINT if self.score >= self.threshold else ASH)
            score_color.setAlpha(110)
            p.setBrush(score_color)
            p.drawRoundedRect(fill, 4, 4)
        x = track.left() + track.width() * self._fraction_at_threshold(self.threshold)
        p.setPen(QPen(QColor(BONE if not self.hasFocus() else GOLD), 2))
        p.setBrush(QColor(GOLD))
        marker = QPainterPath(QPointF(x, 24))
        marker.lineTo(x - 6, 31)
        marker.lineTo(x + 6, 31)
        marker.closeSubpath()
        p.drawLine(QPointF(x, 3), QPointF(x, 26))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(marker)

        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor(EMBER))
        p.drawText(
            QRectF(track.left(), 32, track.width() / 2, 15),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{self.MIN_THRESHOLD:.2f}  More permissive",
        )
        p.setPen(QColor(MINT))
        p.drawText(
            QRectF(track.left() + track.width() / 2, 32, track.width() / 2, 15),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"Stricter  {self.MAX_THRESHOLD:.2f}",
        )


class LeaderRow(QWidget):
    """One leaderboard line: a bar showing the player's share of the top score."""

    def __init__(self, rank: int, name: str, count: int, top: int, is_you: bool):
        super().__init__()
        self.rank, self.name, self.count, self.top, self.is_you = rank, name, count, top, is_you
        self.setFixedHeight(46)
        self.setAccessibleName(f"{rank}. {name}: {count} chests")

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(0, 3, 0, -3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(DUSK))
        p.drawRoundedRect(area, 6, 6)
        share = max(0.0, self.count / self.top) if self.top > 0 else 0.0
        bar_rect = QRectF(area.left(), area.top(), area.width() * share, area.height())
        bar = QLinearGradient(bar_rect.topLeft(), bar_rect.topRight())
        start, end = QColor(GOLD if self.rank == 1 else ASH), QColor(GOLD if self.rank == 1 else ASH)
        start.setAlphaF(0.38 if self.rank == 1 else 0.14)
        end.setAlphaF(0.22 if self.rank == 1 else 0.08)
        bar.setColorAt(0, start)
        bar.setColorAt(1, end)
        p.setBrush(QBrush(bar))
        p.drawRoundedRect(bar_rect, 6, 6)

        p.setFont(display_font(21))
        p.setPen(QColor(BONE if self.rank == 1 else ASH))
        p.drawText(area.adjusted(14, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, str(self.rank))
        name = QFont("Segoe UI")
        name.setPixelSize(15)
        name.setWeight(QFont.Weight.DemiBold if self.is_you else QFont.Weight.Normal)
        p.setFont(name)
        p.setPen(QColor(BONE))
        label = f"{self.name} (you)" if self.is_you else self.name
        p.drawText(area.adjusted(44, 0, -90, 0), Qt.AlignmentFlag.AlignVCenter, label)
        p.setFont(display_font(22))
        p.setPen(QColor(BONE))
        p.drawText(
            area.adjusted(0, 0, -14, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, f"{self.count:,}",
        )


class StepBadge(QWidget):
    """A setup step's number, which becomes a check mark when the step is done."""

    def __init__(self, number: int):
        super().__init__()
        self.number = number
        self.done = False
        self.active = False
        self.setFixedSize(30, 30)

    def set_status(self, done: bool, active: bool) -> None:
        self.done, self.active = done, active
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        circle = QRectF(2, 2, 26, 26)
        if self.done:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(MINT))
            p.drawEllipse(circle)
            pen = QPen(QColor(NIGHT), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPolyline([QPointF(9, 15), QPointF(13.5, 19.5), QPointF(21, 11)])
            return
        p.setPen(QPen(QColor(GOLD if self.active else LINE_STRONG), 1.6))
        p.setBrush(QColor(NIGHT))
        p.drawEllipse(circle)
        p.setPen(QColor(GOLD if self.active else ASH))
        p.setFont(display_font(17))
        p.drawText(circle, Qt.AlignmentFlag.AlignCenter, str(self.number))


class DailyBars(QWidget):
    """Chests per day as quiet bars, today highlighted in gold."""

    def __init__(self):
        super().__init__()
        self.days: list[tuple[date, int]] = []
        self.hovered = -1
        self.setMouseTracking(True)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_days(self, days: list[tuple[date, int]]) -> None:
        self.days = days
        total = sum(count for _, count in days)
        self.setAccessibleName(f"{total} chests in the last {len(days)} days")
        self.update()

    def _plot(self) -> QRectF:
        return QRectF(self.rect()).adjusted(34, 10, -4, -26)

    def _bar_index(self, x: float) -> int:
        plot = self._plot()
        if not self.days or not plot.left() <= x <= plot.right():
            return -1
        return min(len(self.days) - 1, int((x - plot.left()) / (plot.width() / len(self.days))))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = self._bar_index(event.position().x())
        if index != self.hovered:
            self.hovered = index
            self.update()

    def leaveEvent(self, event) -> None:
        self.hovered = -1
        self.update()

    @staticmethod
    def _nice_top(value: int) -> int:
        if value <= 4:
            return 4
        magnitude = 10 ** (len(str(value)) - 1)
        for step in (1, 1.2, 1.6, 2, 2.4, 3, 4, 5, 6, 8, 10):
            top = int(step * magnitude)
            if top >= value and top % 4 == 0:
                return top
        return value + (4 - value % 4) % 4

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = self._plot()
        top = self._nice_top(max((count for _, count in self.days), default=0))
        small = QFont(["Segoe UI Variable Text", "Segoe UI"])
        small.setPixelSize(11)
        p.setFont(small)

        for step in range(5):
            y = plot.bottom() - plot.height() * step / 4
            p.setPen(QPen(QColor(LINE), 1, Qt.PenStyle.SolidLine if step == 0 else Qt.PenStyle.DotLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(FAINT))
            p.drawText(QRectF(0, y - 8, plot.left() - 8, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{round(top * step / 4):,}")
        if not self.days:
            return

        slot = plot.width() / len(self.days)
        bar_width = min(28.0, slot * 0.56)
        for index, (day, count) in enumerate(self.days):
            x = plot.left() + slot * index + (slot - bar_width) / 2
            height = plot.height() * count / top if top else 0
            is_today = index == len(self.days) - 1
            color = QColor(GOLD if is_today else "#3A3F48")
            if index == self.hovered and not is_today:
                color = QColor("#5A606B")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            if height > 0:
                bar = QPainterPath()
                bar.addRoundedRect(QRectF(x, plot.bottom() - height, bar_width, height), 3, 3)
                p.drawPath(bar)
            p.setPen(QColor(BONE if is_today else FAINT))
            label = "Today" if is_today else day.strftime("%a")[:2]
            p.drawText(QRectF(plot.left() + slot * index - 6, plot.bottom() + 6, slot + 12, 16),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)

        if 0 <= self.hovered < len(self.days):
            day, count = self.days[self.hovered]
            text = f"{day.strftime('%d %b')}  ·  {count:,} chest{'s' if count != 1 else ''}"
            metrics = QFontMetricsF(small)
            box = QRectF(0, 0, metrics.horizontalAdvance(text) + 18, 24)
            center = plot.left() + slot * (self.hovered + 0.5)
            box.moveCenter(QPointF(min(max(center, plot.left() + box.width() / 2), plot.right() - box.width() / 2),
                                   plot.top() + 12))
            p.setPen(QPen(QColor(LINE_STRONG), 1))
            p.setBrush(QColor(RAISED))
            p.drawRoundedRect(box, 5, 5)
            p.setPen(QColor(BONE))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)


class NavButton(QAbstractButton):
    """A sidebar entry: a Segoe Fluent icon and a label, with a gold marker when selected."""

    def __init__(self, glyph: str, text: str):
        super().__init__()
        self.glyph = glyph
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedHeight(38)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(text)

    def sizeHint(self) -> QSize:
        return QSize(200, 38)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        hovered = self.underMouse()
        if self.isChecked() or hovered:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(RAISED if self.isChecked() else "#15171B"))
            p.drawRoundedRect(area, 7, 7)
        if self.isChecked():
            p.setBrush(QColor(GOLD))
            p.drawRoundedRect(QRectF(area.left(), area.top() + 10, 3, area.height() - 20), 1.5, 1.5)
        if self.hasFocus():
            p.setPen(QPen(QColor(LINE_STRONG), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(area.adjusted(0.5, 0.5, -0.5, -0.5), 7, 7)

        color = QColor(BONE if self.isChecked() else (BONE if hovered else ASH))
        icon = QFont(["Segoe Fluent Icons", "Segoe MDL2 Assets"])
        icon.setPixelSize(16)
        p.setFont(icon)
        p.setPen(QColor(GOLD) if self.isChecked() else color)
        p.drawText(QRectF(area.left() + 14, area.top(), 20, area.height()), Qt.AlignmentFlag.AlignCenter, self.glyph)
        text = QFont(["Segoe UI Variable Text", "Segoe UI"])
        text.setPixelSize(14)
        text.setWeight(QFont.Weight.DemiBold if self.isChecked() else QFont.Weight.Medium)
        p.setFont(text)
        p.setPen(color)
        p.drawText(area.adjusted(46, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
