"""'Focus Next' panel: the top 3 tasks to work on, each with a Start button."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from pomodoro.priority import ScoredTask
from pomodoro.ui.theme import PHASE_COLORS
from pomodoro.timer import Phase

AT_RISK_COLOR = "#DC6B19"


class FocusNextPanel(QFrame):
    start_requested = Signal(int)   # task id

    def __init__(self, parent=None):
        super().__init__(parent, objectName="focusNext")
        self._buttons: list[QPushButton] = []
        self._start_enabled = True

        title = QLabel("FOCUS NEXT", objectName="panelTitle")
        self.summary_label = QLabel(objectName="summary", wordWrap=True)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)
        layout.addWidget(title)
        layout.addWidget(self.summary_label)
        layout.addLayout(self.rows)

    def show_tasks(self, ranked: list[ScoredTask], summary: str):
        self.summary_label.setText(summary)
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().hide()          # hide now; delete once any click on it has finished
                item.widget().deleteLater()
        self._buttons = []

        if not ranked:
            self.rows.addWidget(QLabel("No open tasks. Add some in the Tasks tab.",
                                       objectName="reason"))
            return
        for number, scored in enumerate(ranked[:3], start=1):
            self.rows.addWidget(self._make_row(number, scored))
        self.set_start_enabled(self._start_enabled)

    def _make_row(self, number: int, scored: ScoredTask) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 2)

        rank = QLabel(str(number), objectName="rank", alignment=Qt.AlignCenter)
        rank.setFixedWidth(18)
        name = QLabel(scored.title, objectName="taskName")
        reason = QLabel(scored.short_reason(), objectName="reason")
        if scored.at_risk or (scored.due and "overdue" in scored.short_reason()):
            reason.setStyleSheet(f"color: {AT_RISK_COLOR};")
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(name)
        text.addWidget(reason)

        button = QPushButton("▶", objectName="play")
        button.setToolTip(f'Start a pomodoro on "{scored.title}"')
        button.setCursor(Qt.PointingHandCursor)
        button.setFixedSize(30, 30)
        button.setStyleSheet(f"QPushButton {{ background: {PHASE_COLORS[Phase.FOCUS]}; }}"
                             "QPushButton:disabled { background: #E8E8EC; }")
        button.clicked.connect(lambda: self.start_requested.emit(scored.id))
        self._buttons.append(button)

        layout.addWidget(rank)
        layout.addLayout(text, 1)
        layout.addWidget(button)
        return row

    def set_start_enabled(self, enabled: bool):
        """Start buttons are disabled while a focus block is running."""
        self._start_enabled = enabled
        for button in self._buttons:
            button.setEnabled(enabled)
