"""Two small hand-drawn charts for the Reports and Deadlines tabs.

  * HBarChart  - one labelled row per item (category, type, priority)
  * ColumnChart - one column per day, with an optional dashed goal line

Every bar is labelled directly (name + value), and hovering shows the details,
so colour is never the only way to tell bars apart.
"""

from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

TEXT = QColor("#1C2024")
TEXT_SECONDARY = QColor("#60646C")
TEXT_MUTED = QColor("#8B8D98")
GRID = QColor("#E8E8EC")
DEFAULT_BAR = "#2a78d6"


@dataclass
class Bar:
    label: str
    value: float
    color: str = DEFAULT_BAR
    tooltip: str = ""
    value_text: str = ""     # what to print at the end of the bar


def _bar_path(rect: QRectF, radius: float, horizontal: bool) -> QPainterPath:
    """Bar with rounded corners on the data end only (the end away from the baseline)."""
    path = QPainterPath()
    r = min(radius, rect.width() / 2, rect.height() / 2)
    if horizontal:          # rounded on the right
        path.moveTo(rect.left(), rect.top())
        path.lineTo(rect.right() - r, rect.top())
        path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + r)
        path.lineTo(rect.right(), rect.bottom() - r)
        path.quadTo(rect.right(), rect.bottom(), rect.right() - r, rect.bottom())
        path.lineTo(rect.left(), rect.bottom())
    else:                   # rounded on the top
        path.moveTo(rect.left(), rect.bottom())
        path.lineTo(rect.left(), rect.top() + r)
        path.quadTo(rect.left(), rect.top(), rect.left() + r, rect.top())
        path.lineTo(rect.right() - r, rect.top())
        path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + r)
        path.lineTo(rect.right(), rect.bottom())
    path.closeSubpath()
    return path


class HBarChart(QWidget):
    ROW_HEIGHT = 30
    BAR_HEIGHT = 14
    LABEL_WIDTH = 120
    VALUE_WIDTH = 90

    def __init__(self, empty_text: str = "No focus time in this period.", parent=None):
        super().__init__(parent)
        self.bars: list[Bar] = []
        self.empty_text = empty_text
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_bars(self, bars: list[Bar]):
        self.bars = bars
        self.setFixedHeight(max(len(bars), 1) * self.ROW_HEIGHT + 4)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(320, self.height())

    def _bar_rect(self, index: int, value: float, top_value: float) -> QRectF:
        plot_width = max(self.width() - self.LABEL_WIDTH - self.VALUE_WIDTH, 10)
        width = 0 if top_value <= 0 else max(plot_width * value / top_value, 2 if value else 0)
        y = index * self.ROW_HEIGHT + (self.ROW_HEIGHT - self.BAR_HEIGHT) / 2
        return QRectF(self.LABEL_WIDTH, y, width, self.BAR_HEIGHT)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont(self.font())
        font.setPixelSize(12)
        painter.setFont(font)

        if not self.bars:
            painter.setPen(TEXT_MUTED)
            painter.drawText(self.rect(), Qt.AlignVCenter | Qt.AlignLeft, self.empty_text)
            return

        top = max(bar.value for bar in self.bars)
        # Baseline
        painter.setPen(QPen(GRID, 1))
        painter.drawLine(self.LABEL_WIDTH, 0, self.LABEL_WIDTH, self.height())

        for i, bar in enumerate(self.bars):
            row = QRectF(0, i * self.ROW_HEIGHT, self.width(), self.ROW_HEIGHT)
            painter.setPen(TEXT_SECONDARY)
            label_rect = QRectF(0, row.top(), self.LABEL_WIDTH - 10, row.height())
            label = painter.fontMetrics().elidedText(bar.label, Qt.ElideRight,
                                                     int(label_rect.width()))
            painter.drawText(label_rect, Qt.AlignVCenter | Qt.AlignRight, label)

            rect = self._bar_rect(i, bar.value, top)
            if rect.width() > 0:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(bar.color))
                painter.drawPath(_bar_path(rect, 4, horizontal=True))

            painter.setPen(TEXT)
            value_rect = QRectF(rect.right() + 8, row.top(), self.VALUE_WIDTH + 40, row.height())
            painter.drawText(value_rect, Qt.AlignVCenter | Qt.AlignLeft, bar.value_text)

    def mouseMoveEvent(self, event):
        index = int(event.position().y() // self.ROW_HEIGHT)
        if 0 <= index < len(self.bars) and self.bars[index].tooltip:
            QToolTip.showText(event.globalPosition().toPoint(), self.bars[index].tooltip, self)
        else:
            QToolTip.hideText()


class ColumnChart(QWidget):
    """Vertical bars, one per day. Hover a column for its details."""
    LEFT, RIGHT, TOP, BOTTOM = 34, 8, 14, 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bars: list[Bar] = []
        self.goal: float | None = None
        self.goal_label = ""
        self.setMouseTracking(True)
        self.setFixedHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_bars(self, bars: list[Bar], goal: float | None = None, goal_label: str = ""):
        self.bars, self.goal, self.goal_label = bars, goal, goal_label
        self.update()

    def _scale_top(self) -> float:
        values = [b.value for b in self.bars] + ([self.goal] if self.goal else [])
        top = max(values, default=0)
        if top <= 0:
            return 1
        # Round up to a "nice" number so gridlines land on whole values.
        for step in (1, 2, 4, 5, 10, 20, 25, 50, 100):
            if top / step <= 4:
                return step * -(-top // step)
        return top

    def _plot(self) -> QRectF:
        return QRectF(self.LEFT, self.TOP, self.width() - self.LEFT - self.RIGHT,
                      self.height() - self.TOP - self.BOTTOM)

    def _column_rect(self, index: int, top: float) -> QRectF:
        plot = self._plot()
        slot = plot.width() / len(self.bars)
        gap = max(2.0, slot * 0.25)
        width = min(max(slot - gap, 2), 40)     # thin bars, even when there are few days
        height = plot.height() * self.bars[index].value / top
        return QRectF(plot.left() + index * slot + (slot - width) / 2, plot.bottom() - height,
                      width, height)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont(self.font())
        font.setPixelSize(11)
        painter.setFont(font)
        plot = self._plot()
        top = self._scale_top()

        # Recessive gridlines with value labels on the left
        for i in range(5):
            value = top * i / 4
            y = plot.bottom() - plot.height() * i / 4
            painter.setPen(QPen(GRID, 1))
            painter.drawLine(plot.left(), y, plot.right(), y)
            painter.setPen(TEXT_MUTED)
            text = f"{value:g}" if value == int(value) else f"{value:.1f}"
            painter.drawText(QRectF(0, y - 8, self.LEFT - 6, 16),
                             Qt.AlignRight | Qt.AlignVCenter, text)

        if not self.bars:
            return

        for i, bar in enumerate(self.bars):
            rect = self._column_rect(i, top)
            if rect.height() > 0:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(bar.color))
                painter.drawPath(_bar_path(rect, 3, horizontal=False))

        # Day labels - thinned out so they never overlap
        metrics = painter.fontMetrics()
        slot = plot.width() / len(self.bars)
        widest = max(metrics.horizontalAdvance(b.label) for b in self.bars) + 6
        every = max(1, int(-(-widest // slot)))
        painter.setPen(TEXT_SECONDARY)
        for i, bar in enumerate(self.bars):
            if i % every == 0:
                x = plot.left() + i * slot
                painter.drawText(QRectF(x - 20, plot.bottom() + 4, slot + 40, 16),
                                 Qt.AlignHCenter | Qt.AlignTop, bar.label)

        if self.goal:
            y = plot.bottom() - plot.height() * self.goal / top
            pen = QPen(TEXT_SECONDARY, 1, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(plot.left(), y, plot.right(), y)
            painter.drawText(QRectF(plot.left() + 4, y - 16, 200, 14),
                             Qt.AlignLeft | Qt.AlignVCenter, self.goal_label)

    def mouseMoveEvent(self, event):
        if not self.bars:
            return
        plot = self._plot()
        index = int((event.position().x() - plot.left()) // (plot.width() / len(self.bars)))
        if 0 <= index < len(self.bars):
            QToolTip.showText(event.globalPosition().toPoint(), self.bars[index].tooltip, self)
        else:
            QToolTip.hideText()
