"""The Deadlines tab: open tasks grouped by due date, and a 7-day workload check."""

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from pomodoro import reports
from pomodoro.models import PRIORITIES, due_label
from pomodoro.priority import ScoredTask

OVERDUE_RED = "#CE2C31"
AT_RISK_ORANGE = "#DC6B19"
OK_GREEN = "#18794E"


class DeadlinesTab(QWidget):
    start_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Set by the app: returns (ranked tasks, daily goal, pomodoros done today,
        # working days, upcoming recurring occurrences).
        self.plan_provider = lambda: ([], 8, 0, {0, 1, 2, 3, 4}, [])

        self.board = QHBoxLayout()
        self.board.setSpacing(10)
        self.columns: dict[str, QVBoxLayout] = {}
        self.headers: dict[str, QLabel] = {}
        for name in reports.BOARD_COLUMNS:
            frame = QFrame(objectName="boardColumn")
            column = QVBoxLayout(frame)
            column.setContentsMargins(8, 8, 8, 8)
            column.setSpacing(6)
            header = QLabel(objectName="boardHeader")
            column.addWidget(header)
            cards = QVBoxLayout()
            cards.setSpacing(6)
            column.addLayout(cards)
            column.addStretch()
            self.board.addWidget(frame, 1)
            self.columns[name], self.headers[name] = cards, header

        self.workload_table = QTableWidget(0, 5)
        self.workload_table.setHorizontalHeaderLabels(
            ["Day", "Due that day", "You can do", "Running total (needed / can do)", "Status"])
        self.workload_table.verticalHeader().setVisible(False)
        self.workload_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.workload_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.workload_table.setShowGrid(False)
        header = self.workload_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)

        workload_card = QFrame(objectName="card")
        workload_layout = QVBoxLayout(workload_card)
        workload_layout.setContentsMargins(16, 12, 16, 14)
        workload_layout.addWidget(QLabel("Workload - next 7 days", objectName="cardTitle"))
        workload_layout.addWidget(QLabel(
            "Pomodoros still needed for tasks due each day vs. what your daily goal allows. "
            "Overdue work counts on today; upcoming recurring tasks count on their day. "
            "Tasks without an estimate aren't counted.",
            objectName="cardNote", wordWrap=True))
        workload_layout.addWidget(self.workload_table)

        content = QWidget(objectName="reportsContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)
        layout.addLayout(self.board)
        layout.addWidget(workload_card)
        layout.addStretch()

        scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def refresh(self):
        ranked, goal, done_today, working_days, reserved = self.plan_provider()
        today = date.today()

        board = reports.deadline_board(ranked, today)
        for name, cards in self.columns.items():
            while cards.count():
                item = cards.takeAt(0)
                if item.widget():
                    item.widget().hide()          # hide now; delete once any click on it has finished
                    item.widget().deleteLater()
            tasks = board[name]
            self.headers[name].setText(f"{name.upper()}  ·  {len(tasks)}")
            self.headers[name].setStyleSheet(
                f"color: {OVERDUE_RED};" if name == "Overdue" and tasks else "")
            for scored in tasks:
                cards.addWidget(self._card(scored, name, today))
            if not tasks:
                cards.addWidget(QLabel("Nothing here", objectName="cardNote"))

        days = reports.workload(ranked, today, goal, done_today, working_days,
                                reserved=reserved)
        self.workload_table.setRowCount(len(days))
        for row, day in enumerate(days):
            label = "Today" if row == 0 else day.day.strftime("%a %d %b")
            over = day.cumulative_needed - day.cumulative_available
            status = f"⚠ Overloaded by {over} 🍅" if day.overloaded else "✓ OK"
            cells = [label, str(day.needed), str(day.available),
                     f"{day.cumulative_needed} / {day.cumulative_available}", status]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column in (1, 2, 3):
                    item.setTextAlignment(Qt.AlignCenter)
                if column == 4:
                    item.setForeground(QColor(OVERDUE_RED if day.overloaded else OK_GREEN))
                self.workload_table.setItem(row, column, item)
        self.workload_table.setFixedHeight(36 + 30 * len(days))

    def _card(self, scored: ScoredTask, column: str, today: date) -> QWidget:
        card = QFrame(objectName="taskCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(2)

        top = QHBoxLayout()
        title = QLabel(scored.title, objectName="taskName", wordWrap=True)
        play = QPushButton("▶", objectName="play")
        play.setFixedSize(26, 26)
        play.setToolTip(f'Start a pomodoro on "{scored.title}"')
        play.setCursor(Qt.PointingHandCursor)
        play.setStyleSheet("QPushButton { background: #E5484D; }")
        play.clicked.connect(lambda: self.start_requested.emit(scored.id))
        top.addWidget(title, 1)
        top.addWidget(play, 0, Qt.AlignTop)
        layout.addLayout(top)

        details = [PRIORITIES[scored.task["priority"]]]
        if scored.due and column not in ("Today",):
            details.append(due_label(scored.task["due_date"], today))
        if scored.remaining is not None:
            details.append(f"{scored.remaining} 🍅 left")
        layout.addWidget(QLabel(" · ".join(details), objectName="reason", wordWrap=True))
        if scored.at_risk:
            risk = QLabel("⚠ At risk", objectName="reason")
            risk.setStyleSheet(f"color: {AT_RISK_ORANGE}; font-weight: 600;")
            risk.setToolTip("The pomodoros left won't fit before the due date at your daily goal.")
            layout.addWidget(risk)
        return card
