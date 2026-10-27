"""A row of small squares, one per scheduled day of a recurring task ("don't break the chain").

  ✓ green       done
  ½ light green showed up (did the two-minute version)
  ✗ red         missed
  ○ outlined    today, still open
  · grey        coming days
Hover a square for the date and the pomodoros spent.
"""

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

CELL, GAP = 18, 4
STYLE = {   # fill, text colour, symbol
    "done": ("#30A46C", "white", "✓"),
    "showed_up": ("#A7DDBB", "#18794E", "½"),
    "missed": ("#FBE3E3", "#CE2C31", "✗"),
    "open": (None, "#12A594", ""),
    "future": ("#F0F0F3", "#B9BBC6", ""),
}
LABELS = {"done": "Done", "showed_up": "Showed up (two-minute version)", "missed": "Missed",
          "open": "Today – still open", "future": "Coming up"}


class HistoryStrip(QWidget):
    def __init__(self, days: list[dict], parent=None):
        super().__init__(parent)
        self.days = days
        self.setMouseTracking(True)
        self.setFixedHeight(CELL + 2)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedWidth(max(len(days), 1) * (CELL + GAP))

    def sizeHint(self) -> QSize:
        return QSize(self.width(), CELL + 2)

    @staticmethod
    def kind(day: dict) -> str:
        return "showed_up" if day["status"] == "done" and day["showed_up"] else day["status"]

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        for i, day in enumerate(self.days):
            fill, ink, symbol = STYLE[self.kind(day)]
            rect = QRectF(i * (CELL + GAP) + 1, 1, CELL, CELL)
            if fill:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(fill))
            else:
                painter.setPen(QPen(QColor(ink), 1.6))
                painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 4, 4)
            if symbol:
                painter.setPen(QColor(ink))
                painter.drawText(rect, Qt.AlignCenter, symbol)

    def mouseMoveEvent(self, event):
        index = int(event.position().x() // (CELL + GAP))
        if 0 <= index < len(self.days):
            day = self.days[index]
            text = f"{day['date'].strftime('%a %d %b')} – {LABELS[self.kind(day)]}"
            if day["pomodoros"]:
                text += f" · {day['pomodoros']} 🍅"
            QToolTip.showText(event.globalPosition().toPoint(), text, self)
        else:
            QToolTip.hideText()
