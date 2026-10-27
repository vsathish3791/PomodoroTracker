"""Reports -> Growth: evidence that you're improving, from your own pomodoros."""

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHeaderView, QLabel, QScrollArea,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from pomodoro import growth
from pomodoro.database import Database
from pomodoro.models import STRETCH
from pomodoro.ui.charts import Bar, ColumnChart, HBarChart
from pomodoro.ui.goals_tab import card

GOOD, BAD, PEAK, LOW, NORMAL = "#18794E", "#CE2C31", "#30A46C", "#DC6B19", "#2a78d6"
STRETCH_COLORS = {"comfort": "#8B8D98", "stretch": "#30A46C", "panic": "#DC6B19"}


def table(headers: list[str]) -> QTableWidget:
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().setVisible(False)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.setSelectionMode(QAbstractItemView.NoSelection)
    widget.setShowGrid(False)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    return widget


class GrowthTab(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        content = QWidget(objectName="reportsContent")
        body = QVBoxLayout(content)
        body.setContentsMargins(16, 12, 16, 16)
        body.setSpacing(12)

        frame, layout = card("Then vs Now", "The last 30 days against the 30 days before. "
                                            "Small gains add up – here's your evidence.")
        self.compare = table(["", "30–60 days ago", "Last 30 days", ""])
        layout.addWidget(self.compare)
        body.addWidget(frame)

        frame, layout = card("Best hours", "Completed pomodoros by hour of day (last 60 days). "
                                           "Green = your peak, orange = your weakest hour.")
        self.hours_text = QLabel(wordWrap=True)
        self.hours_chart = ColumnChart()
        layout.addWidget(self.hours_text)
        layout.addWidget(self.hours_chart)
        body.addWidget(frame)

        frame, layout = card("Stretch zone (last 30 days)",
                             "How finished tasks felt. Growth happens in the stretch zone – "
                             "aim for about 30%.")
        self.stretch_chart = HBarChart(empty_text="No rated tasks yet – rate tasks when you "
                                                  "finish them (bottom bar).")
        self.stretch_text = QLabel(objectName="cardNote", wordWrap=True)
        layout.addWidget(self.stretch_chart)
        layout.addWidget(self.stretch_text)
        body.addWidget(frame)

        frame, layout = card("Practice (last 30 days)",
                             "Pomodoros in 🎯 Practice mode per skill. Falling difficulty for "
                             "the same kind of target means you're getting better.")
        self.practice = table(["Skill", "Sessions", "Time", "Difficulty (earlier → recent)",
                               "Last target"])
        self.practice_empty = QLabel("No practice pomodoros yet – tick 🎯 Practice on the "
                                     "Timer.", objectName="cardNote")
        layout.addWidget(self.practice)
        layout.addWidget(self.practice_empty)
        body.addWidget(frame)
        body.addStretch()

        scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def refresh(self):
        today = date.today()
        self._then_vs_now(today)
        self._best_hours(today)
        self._stretch(today)
        self._practice(today)

    def _then_vs_now(self, today: date):
        rows = growth.then_vs_now(self.db, today)
        self.compare.setRowCount(len(rows))
        for i, row in enumerate(rows):
            arrow = {True: "▲ better", False: "▼ worse", None: ""}[row.better]
            for column, text in enumerate([row.name, row.then, row.now, arrow]):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(Qt.AlignCenter)
                if column == 3 and row.better is not None:
                    item.setForeground(QColor(GOOD if row.better else BAD))
                self.compare.setItem(i, column, item)
        self.compare.setFixedHeight(36 + 30 * len(rows))

    def _best_hours(self, today: date):
        hours = growth.best_hours(self.db, today)
        if not hours.hours:
            self.hours_text.setText("No pomodoros yet.")
            self.hours_chart.set_bars([])
            return
        span = range(min(h.hour for h in hours.hours), max(h.hour for h in hours.hours) + 1)
        by_hour = {h.hour: h for h in hours.hours}
        bars = []
        for hour in span:
            stats = by_hour.get(hour)
            color = PEAK if hour in hours.peak else LOW if hour in hours.low else NORMAL
            tip = (f"{hour}:00–{hour + 1}:00\n{stats.completed} completed of {stats.started} · "
                   f"{stats.distractions} distraction(s)" if stats else f"{hour}:00 – nothing")
            bars.append(Bar(f"{hour}", stats.completed if stats else 0,
                            color if hours.enough_data else NORMAL, tip))
        self.hours_chart.set_bars(bars)
        if hours.enough_data:
            self.hours_text.setText(
                f"Your focus peaks <b>{growth.hour_label(hours.peak)}</b>"
                + (f" · weakest hour <b>{growth.hour_label(hours.low)}</b>" if hours.low else "")
                + ". Focus Next lifts ⚡ Deep-work tasks in your peak hours and ☐ Plan/Close "
                  "tasks in your weakest hour – plan your hardest work there.")
        else:
            self.hours_text.setText(
                f"{hours.total} of {growth.MIN_FOR_BEST_HOURS} pomodoros needed before your "
                "best hours are reliable – keep going.")

    def _stretch(self, today: date):
        counts, unrated, advice = growth.stretch_mix(self.db, today - timedelta(days=29), today)
        total = sum(counts.values())
        bars = [Bar(STRETCH[key], counts[key], STRETCH_COLORS[key],
                    f"{STRETCH[key]}: {counts[key]} task(s)",
                    f"{counts[key]}  ({counts[key] / total:.0%})" if total else "0")
                for key in STRETCH] if total else []
        self.stretch_chart.set_bars(bars)
        self.stretch_text.setText(advice + (f" ({unrated} finished task(s) not rated.)"
                                            if unrated else ""))

    def _practice(self, today: date):
        rows = growth.practice_summary(self.db, today - timedelta(days=29), today)
        self.practice.setRowCount(len(rows))
        for i, row in enumerate(rows):
            if row.first_difficulty is not None and row.recent_difficulty is not None:
                trend = f"{row.first_difficulty:.1f} → {row.recent_difficulty:.1f}"
            elif row.recent_difficulty is not None:
                trend = f"{row.recent_difficulty:.1f}"
            else:
                trend = "not rated"
            hours, minutes = divmod(round(row.minutes), 60)
            cells = [row.skill, str(row.sessions), f"{hours} h {minutes} min" if hours
                     else f"{minutes} min", trend, row.last_target or "–"]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column in (1, 2, 3):
                    item.setTextAlignment(Qt.AlignCenter)
                if column == 3 and row.first_difficulty and row.recent_difficulty:
                    item.setForeground(QColor(GOOD if row.recent_difficulty < row.first_difficulty
                                              else BAD if row.recent_difficulty > row.first_difficulty
                                              else "#60646C"))
                self.practice.setItem(i, column, item)
        self.practice.setVisible(bool(rows))
        self.practice_empty.setVisible(not rows)
        self.practice.setFixedHeight(36 + 30 * max(len(rows), 1))
