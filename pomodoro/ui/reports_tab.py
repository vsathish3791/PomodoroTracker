"""The Reports tab: where your effort went, for a chosen period."""

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from pomodoro import reports
from pomodoro.database import Database
from pomodoro.models import CATEGORY_PALETTE, EXTRA_CATEGORY_COLOR
from pomodoro.ui.charts import Bar, ColumnChart, HBarChart

RANGES = ["Today", "This week", "Last 7 days", "This month", "Last 30 days", "Custom"]


def range_dates(name: str, today: date) -> tuple[date, date]:
    if name == "Today":
        return today, today
    if name == "This week":                       # Monday .. today
        return today - timedelta(days=today.weekday()), today
    if name == "Last 7 days":
        return today - timedelta(days=6), today
    if name == "This month":
        return today.replace(day=1), today
    return today - timedelta(days=29), today      # Last 30 days


def format_minutes(minutes: float) -> str:
    hours, mins = divmod(round(minutes), 60)
    return f"{hours} h {mins} min" if hours else f"{mins} min"


def to_qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def from_qdate(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


class StatTile(QFrame):
    def __init__(self, caption: str):
        super().__init__(objectName="tile")
        self.value = QLabel("0", objectName="tileValue")
        self.caption = QLabel(caption, objectName="tileCaption")
        self.detail = QLabel(objectName="tileDetail")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(0)
        layout.addWidget(self.caption)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set(self, value: str, detail: str = ""):
        self.value.setText(value)
        self.detail.setText(detail)


class Card(QFrame):
    """A white panel with a title, holding one chart or table."""

    def __init__(self, title: str, body: QWidget, note: str = ""):
        super().__init__(objectName="card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.addWidget(QLabel(title, objectName="cardTitle"))
        if note:
            layout.addWidget(QLabel(note, objectName="cardNote", wordWrap=True))
        layout.addWidget(body)
        layout.addStretch()   # keep the title at the top when the card is taller


class ReportsTab(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        # ----- filters, all in one row -----
        self.range_input = QComboBox()
        self.range_input.addItems(RANGES)
        self.range_input.setCurrentText("This week")
        self.from_input = QDateEdit(calendarPopup=True, displayFormat="dd MMM yyyy")
        self.to_input = QDateEdit(calendarPopup=True, displayFormat="dd MMM yyyy")
        self.measure_input = QComboBox()
        self.measure_input.addItem("Show pomodoros", "pomodoros")
        self.measure_input.addItem("Show hours", "hours")
        export_sessions = QPushButton("Export sessions CSV…")
        export_tasks = QPushButton("Export tasks CSV…")

        filters = QHBoxLayout()
        filters.addWidget(self.range_input)
        filters.addWidget(self.from_input)
        filters.addWidget(QLabel("to", objectName="cardNote"))
        filters.addWidget(self.to_input)
        filters.addWidget(self.measure_input)
        filters.addStretch()
        filters.addWidget(export_sessions)
        filters.addWidget(export_tasks)

        # ----- headline numbers -----
        self.tile_pomodoros = StatTile("Pomodoros")
        self.tile_time = StatTile("Focus time")
        self.tile_done = StatTile("Tasks done")
        self.tile_overrides = StatTile("Suggestions skipped")
        tiles = QHBoxLayout()
        for tile in (self.tile_pomodoros, self.tile_time, self.tile_done, self.tile_overrides):
            tiles.addWidget(tile)

        # ----- charts -----
        self.category_chart = HBarChart()
        self.project_chart = HBarChart()
        self.type_chart = HBarChart()
        self.priority_chart = HBarChart()
        self.trend_chart = ColumnChart()
        self.estimate_table = QTableWidget(0, 4)
        self.estimate_table.setHorizontalHeaderLabels(["Finished task", "Estimate 🍅",
                                                       "Actual 🍅", "Difference"])
        self.estimate_table.verticalHeader().setVisible(False)
        self.estimate_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.estimate_table.setShowGrid(False)
        header = self.estimate_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.Stretch)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(Card("Effort by category", self.category_chart), 0, 0)
        grid.addWidget(Card("Effort by type", self.type_chart), 0, 1)
        grid.addWidget(Card("Effort by priority", self.priority_chart,
                            "Are your pomodoros going to the important work?"), 1, 0)
        self.trend_card = Card("Daily trend", self.trend_chart)
        grid.addWidget(self.trend_card, 1, 1)
        grid.addWidget(Card("Effort by project", self.project_chart), 2, 0)
        grid.addWidget(Card("Estimate vs actual", self.estimate_table,
                            "Finished tasks that had an estimate."), 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        content = QWidget(objectName="reportsContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 12, 16, 16)
        content_layout.setSpacing(12)
        content_layout.addLayout(filters)
        content_layout.addLayout(tiles)
        content_layout.addLayout(grid)
        content_layout.addStretch()

        scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        self.range_input.currentTextChanged.connect(self._on_range_changed)
        self.from_input.dateChanged.connect(self.refresh)
        self.to_input.dateChanged.connect(self.refresh)
        self.measure_input.currentIndexChanged.connect(self.refresh)
        export_sessions.clicked.connect(self._export_sessions)
        export_tasks.clicked.connect(self._export_tasks)
        self._on_range_changed(self.range_input.currentText())

    # ---------- period ----------

    def _on_range_changed(self, name: str):
        custom = name == "Custom"
        self.from_input.setEnabled(custom)
        self.to_input.setEnabled(custom)
        if not custom:
            start, end = range_dates(name, date.today())
            for widget, value in ((self.from_input, start), (self.to_input, end)):
                widget.blockSignals(True)
                widget.setDate(to_qdate(value))
                widget.blockSignals(False)
        self.refresh()

    def period(self) -> tuple[date, date]:
        if self.range_input.currentText() != "Custom":
            return range_dates(self.range_input.currentText(), date.today())
        start, end = from_qdate(self.from_input.date()), from_qdate(self.to_input.date())
        return (start, end) if start <= end else (end, start)

    # ---------- drawing ----------

    def _value(self, pomodoros: int, minutes: float) -> float:
        return pomodoros if self.measure_input.currentData() == "pomodoros" else minutes / 60

    def _value_text(self, pomodoros: int, minutes: float, share: float) -> str:
        main = (f"{pomodoros} 🍅" if self.measure_input.currentData() == "pomodoros"
                else f"{minutes / 60:.1f} h")
        return f"{main}  ({share:.0%})"

    def _bars(self, rows: list[reports.EffortRow], color_for) -> list[Bar]:
        """Chart bars; color_for(row) picks each bar's colour."""
        total = sum(self._value(r.pomodoros, r.minutes) for r in rows) or 1
        bars = []
        for r in rows:
            value = self._value(r.pomodoros, r.minutes)
            bars.append(Bar(r.label, value, color_for(r),
                            f"{r.label}\n{r.pomodoros} pomodoros · {format_minutes(r.minutes)}",
                            self._value_text(r.pomodoros, r.minutes, value / total)))
        return bars

    def refresh(self):
        start, end = self.period()
        stats = reports.summary(self.db, start, end)
        days = (end - start).days + 1
        self.tile_pomodoros.set(str(stats["pomodoros"]),
                                f"{stats['daily_average']} a day" if days > 1 else "")
        self.tile_time.set(format_minutes(stats["minutes"]))
        dated = stats["on_time"] + stats["late"]
        self.tile_done.set(str(stats["tasks_done"]),
                           f"{stats['on_time']} on time · {stats['late']} late" if dated else "")
        self.tile_overrides.set(str(stats["overrides"]), "chose a lower-priority task")

        grey = EXTRA_CATEGORY_COLOR
        # Each category keeps its own colour everywhere in the app.
        self.category_chart.set_bars(self._bars(
            reports.effort_by(self.db, start, end, "category"), lambda r: r.color or grey))
        self.project_chart.set_bars(self._bars(
            reports.effort_by(self.db, start, end, "project"), lambda r: r.color or grey))
        self.type_chart.set_bars(self._bars(
            reports.effort_by(self.db, start, end, "type"),
            lambda r: r.color or grey))
        # Priority: one series, so one colour; the row labels say which is which.
        self.priority_chart.set_bars(self._bars(
            reports.effort_by(self.db, start, end, "priority"),
            lambda r: grey if r.label == reports.UNASSIGNED else CATEGORY_PALETTE[0]))

        trend = reports.daily_trend(self.db, start, end)
        pomodoros = self.measure_input.currentData() == "pomodoros"
        bars = [Bar(day.strftime("%d %b") if len(trend) > 7 else day.strftime("%a %d"),
                    self._value(p, m), CATEGORY_PALETTE[0],
                    f"{day.strftime('%a %d %b')}\n{p} pomodoros · {format_minutes(m)}")
                for day, p, m in trend]
        goal = self.db.get_int("daily_goal")
        self.trend_chart.set_bars(bars, goal if pomodoros else goal * 25 / 60,
                                  f"Goal {goal} 🍅" if pomodoros else f"Goal {goal * 25 / 60:.1f} h")

        rows = reports.estimate_accuracy(self.db, start, end)
        self.estimate_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            diff = row["actual"] - row["estimate"]
            cells = [row["title"], str(row["estimate"]), str(row["actual"]),
                     "on estimate" if diff == 0 else f"{diff:+d} 🍅"]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(Qt.AlignCenter)
                self.estimate_table.setItem(i, column, item)
        self.estimate_table.setFixedHeight(36 + 30 * max(len(rows), 1))

    # ---------- export ----------

    def _export(self, default_name: str, write) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", default_name, "CSV files (*.csv)")
        if not path:
            return
        try:
            count = write(path)
        except OSError as error:
            QMessageBox.warning(self, "Export failed", f"Couldn't write the file:\n{error}")
            return
        QMessageBox.information(self, "Exported", f"Saved {count} rows to\n{path}")

    def _export_sessions(self):
        start, end = self.period()
        self._export(f"pomodoro-sessions-{start}-to-{end}.csv",
                     lambda path: reports.export_sessions_csv(self.db, start, end, path))

    def _export_tasks(self):
        self._export(f"pomodoro-tasks-{date.today()}.csv",
                     lambda path: reports.export_tasks_csv(self.db, path))
