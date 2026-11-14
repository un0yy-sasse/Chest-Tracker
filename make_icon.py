"""Draws the app icon (a simple treasure chest) into assets/. Run once, or to change it."""

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

ASSETS = Path(__file__).resolve().parent / "assets"


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 64, size / 64)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#000000"))
    p.drawRoundedRect(QRectF(0, 0, 64, 64), 14, 14)
    p.setPen(QPen(QColor("#5A5A5A"), 1.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(1.5, 1.5, 61, 61), 12.5, 12.5)

    outline = QPen(QColor("#050505"), 2.2)
    p.setPen(outline)
    p.setBrush(QColor("#2E2E2E"))
    p.drawRoundedRect(QRectF(10, 13, 44, 20), 9, 9)
    p.setBrush(QColor("#161616"))
    p.drawRoundedRect(QRectF(10, 29, 44, 23), 2, 2)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#FFFFFF"))
    p.drawRect(QRectF(16, 14, 5, 37))
    p.drawRect(QRectF(43, 14, 5, 37))
    p.drawRect(QRectF(11, 28, 42, 3.2))
    p.setBrush(QColor("#E6E6E6"))
    p.setPen(QPen(QColor("#050505"), 1.8))
    p.drawRoundedRect(QRectF(27, 24, 10, 13), 2.5, 2.5)
    p.end()
    return image


def main() -> None:
    app = QGuiApplication([])
    ASSETS.mkdir(exist_ok=True)
    draw(256).save(str(ASSETS / "icon.png"))
    draw(256).save(str(ASSETS / "icon.ico"))
    del app


if __name__ == "__main__":
    main()
