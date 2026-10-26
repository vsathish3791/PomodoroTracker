"""A small always-on-top timer you can drag anywhere on screen."""

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from pomodoro.timer import Phase
from pomodoro.ui.main_window import format_mmss
from pomodoro.ui.theme import PHASE_COLORS


class MiniWindow(QWidget):
    toggle_requested = Signal()     # Start / Pause / Resume
    open_main = Signal()
    hidden_by_user = Signal()
    moved = Signal(QPoint)

    WIDTH, HEIGHT = 270, 64

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setWindowTitle("Pomodoro mini timer")
        self._color = QColor(PHASE_COLORS[Phase.IDLE])
        self._drag_offset: QPoint | None = None

        self.time_label = QLabel("25:00")
        self.time_label.setStyleSheet("font-size: 22px; font-weight: 600; color: #1C2024;")
        self.task_label = QLabel()
        self.task_label.setStyleSheet("font-size: 11px; color: #60646C;")
        self.task_label.setFixedWidth(150)

        self.toggle_button = self._button("▶", "Start / Pause", self.toggle_requested.emit)
        open_button = self._button("⤢", "Open the main window", self.open_main.emit)
        close_button = self._button("✕", "Hide the mini timer", self._hide_by_user)

        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(self.time_label)
        text.addWidget(self.task_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 6, 8, 6)
        layout.setSpacing(4)
        layout.addLayout(text, 1)
        layout.addWidget(self.toggle_button)
        layout.addWidget(open_button)
        layout.addWidget(close_button)

    def _button(self, text: str, tooltip: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.setFixedSize(28, 28)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            "QPushButton { border: none; border-radius: 14px; background: #F0F0F3;"
            " color: #1C2024; font-size: 13px; }"
            "QPushButton:hover { background: #E0E1E6; }")
        button.clicked.connect(slot)
        return button

    def show_state(self, phase: Phase, running: bool, started: bool, remaining: float,
                   task_name: str):
        self._color = QColor(PHASE_COLORS[phase])
        self.time_label.setText(format_mmss(remaining))
        label = task_name if phase in (Phase.FOCUS, Phase.IDLE) else phase.label
        if started and not running:
            label = "Paused · " + label
        metrics = self.task_label.fontMetrics()
        self.task_label.setText(metrics.elidedText(label, Qt.ElideRight, 150))
        self.task_label.setToolTip(label)
        self.toggle_button.setText("❚❚" if running else "▶")
        self.update()

    def _hide_by_user(self):
        self.hide()
        self.hidden_by_user.emit()

    # ---------- drawing: rounded card with a phase-coloured stripe ----------

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        painter.fillPath(path, QColor("white"))
        painter.setPen(QPen(QColor("#D9D9E0"), 1))
        painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        painter.drawRoundedRect(QRectF(8, 12, 6, rect.height() - 22), 3, 3)

    # ---------- drag to move ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _event):
        if self._drag_offset is not None:
            self._drag_offset = None
            self.moved.emit(self.pos())

    def mouseDoubleClickEvent(self, _event):
        self.open_main.emit()
