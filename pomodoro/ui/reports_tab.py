"""The Reports tab: where your effort went, for a chosen period."""

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QDialog,
                               QDialogButtonBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QMessageBox,
                               QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from pomodoro import reports
from pomodoro.database import Database
from pomodoro.models import ANOMALY_KINDS, ANOMALY_REASONS, CATEGORY_PALETTE, EXTRA_CATEGORY_COLOR
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


class LabelDialog(QDialog):
    """Give reasons to off-plan events that don't have one yet."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("What got in the way?")
        self.setMinimumWidth(620)
        self.events = db.unlabelled_anomalies()
        self.table = QTableWidget(len(self.events), 4)
        self.table.setHorizontalHeaderLabels(["When", "What happened", "Task", "Reason"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.pickers = []
        for row, event in enumerate(self.events):
            when = event["happened_at"][:16].replace("T", " ")
            for column, text in enumerate([when, ANOMALY_KINDS[event["kind"]],
                                           event["title"] or "–"]):
                self.table.setItem(row, column, QTableWidgetItem(text))
            picker = QComboBox()
            picker.addItem("Not now", None)
            for key, label in ANOMALY_REASONS.items():
                picker.addItem(label, key)
            self.table.setCellWidget(row, 3, picker)
            self.pickers.append(picker)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("One reason each is enough. Leave 'Not now' to decide later.",
                                objectName="cardNote"))
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def _save(self):
        for event, picker in zip(self.events, self.pickers):
            if picker.currentData():
                self.db.set_anomaly_reason(event["id"], picker.currentData())
        self.accept()


class ReportsTab(QWidget):
    tasks_changed = Signal()       # a countermeasure task was added

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
        # Interruptions & misses (Pareto)
        self.pareto_chart = HBarChart(empty_text="Nothing off-plan in this period. 👍",
                                      value_width=200)
        self.anomaly_summary = QLabel(objectName="cardNote", wordWrap=True)
        self.label_button = QPushButton("Label…")
        self.label_button.clicked.connect(self._label_events)
        self.counter_button = QPushButton("Plan a countermeasure…")
        self.counter_button.clicked.connect(self._plan_countermeasure)
        anomaly_box = QWidget()
        anomaly_layout = QVBoxLayout(anomaly_box)
        anomaly_layout.setContentsMargins(0, 0, 0, 0)
        anomaly_layout.addWidget(self.anomaly_summary)
        anomaly_layout.addWidget(self.pareto_chart)
        anomaly_buttons = QHBoxLayout()
        anomaly_buttons.addWidget(self.label_button)
        anomaly_buttons.addWidget(self.counter_button)
        anomaly_buttons.addStretch()
        anomaly_layout.addLayout(anomaly_buttons)
        self._top_cause = None
        self.nature_chart = HBarChart()
        self.recurring_table = QTableWidget(0, 5)
        self.recurring_table.setHorizontalHeaderLabels(["Recurring task", "Done", "Missed",
                                                        "Open", "Done %"])
        self.recurring_table.verticalHeader().setVisible(False)
        self.recurring_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.recurring_table.setShowGrid(False)
        rec_header = self.recurring_table.horizontalHeader()
        rec_header.setSectionResizeMode(QHeaderView.ResizeToContents)
        rec_header.setSectionResizeMode(0, QHeaderView.Stretch)
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
        grid.addWidget(Card("Kind of work", self.nature_chart,
                            "Routine keeps things running; improvement moves them forward."),
                       2, 1)
        grid.addWidget(Card("Recurring tasks", self.recurring_table,
                            "Occurrences in this period."), 3, 0)
        grid.addWidget(Card("Estimate vs actual", self.estimate_table,
                            "Finished tasks that had an estimate."), 3, 1)
        grid.addWidget(Card("Interruptions & misses", anomaly_box,
                            "Why focus time was lost, biggest causes first. Red bars are "
                            "the 'vital few' behind ~80% of it: fix those first."), 4, 0, 1, 2)
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
        self._show_anomalies(start, end)
        self.nature_chart.set_bars(self._bars(
            reports.effort_by(self.db, start, end, "nature"), lambda r: r.color or grey))
        recurring = reports.recurring_summary(self.db, start, end)
        self.recurring_table.setRowCount(len(recurring))
        for i, row in enumerate(recurring):
            rate = f"{row['rate']:.0%}" if row["rate"] is not None else "–"
            for column, text in enumerate([row["title"], str(row["done"]), str(row["missed"]),
                                           str(row["open"]), rate]):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(Qt.AlignCenter)
                self.recurring_table.setItem(i, column, item)
        self.recurring_table.setFixedHeight(36 + 30 * max(len(recurring), 1))
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

    # ---------- interruptions & misses ----------

    def _show_anomalies(self, start, end):
        rows, summary = reports.anomaly_pareto(self.db, start, end)
        bars, vital = [], True
        for row in rows:
            bars.append(Bar(row.reason, row.count,
                            CATEGORY_PALETTE[7] if vital else EXTRA_CATEGORY_COLOR,
                            f"{row.reason}\n{row.count} times · {row.minutes_lost:.0f} min lost",
                            f"{row.count}  ({row.share:.0%} · total {row.cumulative:.0%})"))
            vital = vital and row.cumulative < 0.8
        self.pareto_chart.set_bars(bars)
        parts = []
        if summary["stopped"]:
            parts.append(f"{summary['stopped']} pomodoro(s) stopped early "
                         f"({summary['minutes_lost']} min lost)")
        if summary["distraction"]:
            parts.append(f"{summary['distraction']} distraction(s)")
        if summary["missed"]:
            parts.append(f"{summary['missed']} missed recurring")
        if summary["late"]:
            parts.append(f"{summary['late']} finished late")
        self.anomaly_summary.setText(" · ".join(parts) if parts else "")
        waiting = len(self.db.unlabelled_anomalies())
        self.label_button.setText(f"Label {waiting} event{'s' if waiting != 1 else ''}…")
        self.label_button.setEnabled(waiting > 0)
        self._top_cause = rows[0].reason if rows else None
        self.counter_button.setEnabled(self._top_cause is not None)
        if self._top_cause:
            self.counter_button.setText(f"Plan a countermeasure for “{self._top_cause}”…")

    def _label_events(self):
        if LabelDialog(self.db, self).exec():
            self.refresh()

    def _plan_countermeasure(self):
        """Falconi: every top cause gets a countermeasure. Often it's a new habit or routine."""
        from pomodoro.ui.task_dialog import TaskDialog
        dialog = TaskDialog(self.db, parent=self)
        dialog.title_input.setText(f"Countermeasure: reduce “{self._top_cause}”")
        dialog.notes_input.setPlainText(
            "Ideas: block focus time in the calendar · Teams on Do Not Disturb during "
            "pomodoros · split big tasks · clarify requirements before starting.")
        if dialog.exec():
            self.tasks_changed.emit()

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
