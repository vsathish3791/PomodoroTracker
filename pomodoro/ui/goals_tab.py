"""The Goals tab: control panel, goals, time split and the compounding chart."""

import json
from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
                               QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget)

from pomodoro import goals
from pomodoro.database import Database
from pomodoro.models import NATURE_ICONS, NATURES
from pomodoro.ui.charts import CumulativeChart

# Status colours with an icon + word, so colour is never the only signal.
PILL = {"good": ("#E6F6EC", "#18794E"), "warning": ("#FFF1E0", "#AD5700"),
        "critical": ("#FDECEC", "#CE2C31"), "done": ("#E6F0FF", "#0D63C9"),
        "none": ("#F0F0F3", "#60646C")}


def pill(status: str) -> QLabel:
    background, ink = PILL[status]
    label = QLabel(goals.STATUS_LABELS[status], objectName="pill")
    label.setStyleSheet(f"background: {background}; color: {ink}; border-radius: 9px; "
                        "padding: 2px 8px; font-size: 11px; font-weight: 600;")
    return label


def card(title: str, note: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(objectName="card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 12, 16, 14)
    head = QHBoxLayout()
    head.addWidget(QLabel(title, objectName="cardTitle"))
    head.addStretch()
    layout.addLayout(head)
    if note:
        layout.addWidget(QLabel(note, objectName="cardNote", wordWrap=True))
    frame.head = head
    return frame, layout


def scope_key(kind: str, value) -> str:
    """('project', 3) -> 'project:3'. Combo boxes store this text (Qt can't look up tuples)."""
    return kind if value is None else f"{kind}:{value}"


def parse_scope(key: str | None) -> tuple:
    if not key or key == "all":
        return ("all", None)
    kind, value = key.split(":", 1)
    return (kind, value)


def scope_choices(db: Database) -> list[tuple[str, str]]:
    choices = [("All work", "all")]
    choices += [(f"Project: {p['name']}", scope_key("project", p["id"]))
                for p in db.list_projects()]
    choices += [(f"Kind: {label}", scope_key("nature", key)) for key, label in NATURES.items()]
    choices += [(f"Category: {c['name']}", scope_key("category", c["id"]))
                for c in db.list_categories()]
    return choices


class GoalDialog(QDialog):
    def __init__(self, db: Database, goal_id: int | None = None, parent=None):
        super().__init__(parent)
        self.db, self.goal_id = db, goal_id
        goal = db.get_goal(goal_id) if goal_id else None
        self.setWindowTitle("Edit goal" if goal else "New goal")
        self.setMinimumWidth(420)

        self.title_input = QLineEdit(placeholderText="e.g. Learn AI every week")
        self.kind_input = QComboBox()
        self.kind_input.addItem("Weekly rhythm – at least N 🍅 every week", "weekly")
        self.kind_input.addItem("Target by a date – N 🍅 in total by a deadline", "by_date")
        self.scope_input = QComboBox()
        for label, scope in scope_choices(db):
            self.scope_input.addItem(label, scope)
        self.value_input = QSpinBox(minimum=1, maximum=2000, value=10, suffix=" 🍅")
        self.deadline_input = QDateEdit(calendarPopup=True, displayFormat="ddd dd MMM yyyy")
        self.deadline_input.setDate(QDate.currentDate().addMonths(1))
        self.note = QLabel(objectName="cardNote", wordWrap=True)

        form = QFormLayout()
        form.addRow("Goal", self.title_input)
        form.addRow("Kind", self.kind_input)
        form.addRow("For", self.scope_input)
        form.addRow("Target", self.value_input)
        form.addRow("Deadline", self.deadline_input)
        form.addRow("", self.note)
        self.form = form
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if goal:
            self.title_input.setText(goal["title"])
            self.kind_input.setCurrentIndex(self.kind_input.findData(goal["kind"]))
            self.scope_input.setCurrentIndex(max(self.scope_input.findData(
                scope_key(goal["scope_kind"], goal["scope_value"])), 0))
            self.value_input.setValue(goal["value"])
            if goal["deadline"]:
                self.deadline_input.setDate(QDate.fromString(goal["deadline"], "yyyy-MM-dd"))
        self.kind_input.currentIndexChanged.connect(self._update)
        self._update()

    def _update(self):
        by_date = self.kind_input.currentData() == "by_date"
        self.deadline_input.setVisible(by_date)
        self.form.labelForField(self.deadline_input).setVisible(by_date)
        self.note.setText(
            "Counts pomodoros from today until the deadline, and forecasts the finish date "
            "from your pace over the last two weeks." if by_date else
            "A rhythm (Atomic Habits: systems over goals). Checked against how far into the "
            "working week you are.")

    def _save(self):
        d = self.deadline_input.date()
        deadline = date(d.year(), d.month(), d.day()).isoformat()
        kind = self.kind_input.currentData()
        scope_kind, scope_value = parse_scope(self.scope_input.currentData())
        try:
            if self.goal_id:
                self.db.update_goal(self.goal_id, title=self.title_input.text(), kind=kind,
                                    scope_kind=scope_kind, scope_value=scope_value,
                                    value=self.value_input.value(),
                                    deadline=deadline if kind == "by_date" else None)
            else:
                self.goal_id = self.db.create_goal(
                    self.title_input.text(), kind, scope_kind, scope_value,
                    self.value_input.value(), deadline if kind == "by_date" else None)
        except ValueError as error:
            QMessageBox.warning(self, "Goal", str(error))
            return
        self.accept()


class SplitDialog(QDialog):
    """Target split of your time between Routine, Habit and Improvement (adds up to 100%)."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Target time split")
        targets = goals.split_targets(db)
        self.boxes = {}
        form = QFormLayout()
        for key, label in NATURES.items():
            box = QSpinBox(minimum=0, maximum=100, suffix=" %", value=targets[key])
            box.valueChanged.connect(self._update)
            self.boxes[key] = box
            form.addRow(f"{NATURE_ICONS[key]} {label}", box)
        self.total = QLabel(objectName="cardNote")
        form.addRow("", self.total)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Falconi: the more you lead, the more of your time should go "
                                "to improvement rather than routine.", objectName="cardNote",
                                wordWrap=True))
        layout.addLayout(form)
        layout.addWidget(self.buttons)
        self._update()

    def _update(self):
        total = sum(box.value() for box in self.boxes.values())
        self.total.setText(f"Total: {total}%" + ("" if total == 100 else " – must be 100%"))
        self.buttons.button(QDialogButtonBox.Save).setEnabled(total == 100)

    def _save(self):
        self.db.set_setting("nature_targets",
                            json.dumps({k: box.value() for k, box in self.boxes.items()}))
        self.accept()


class GoalsTab(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        content = QWidget(objectName="reportsContent")
        self.layout_ = QVBoxLayout(content)
        self.layout_.setContentsMargins(16, 12, 16, 16)
        self.layout_.setSpacing(12)

        # Control panel
        self.panel, panel_layout = card(
            "Control panel",
            "Your system (lead measures) drives your results (lag measures). "
            "Hover a tile for details.")
        self.lead_grid, self.lag_grid = QGridLayout(), QGridLayout()
        panel_layout.addWidget(QLabel("<b>Your system</b>", objectName="cardNote"))
        panel_layout.addLayout(self.lead_grid)
        panel_layout.addWidget(QLabel("<b>Results</b>", objectName="cardNote"))
        panel_layout.addLayout(self.lag_grid)
        self.layout_.addWidget(self.panel)

        # Goals
        self.goals_card, self.goals_layout = card("Goals")
        add = QPushButton("+ New goal")
        add.clicked.connect(self.new_goal)
        self.goals_card.head.addWidget(add)
        self.goal_rows = QVBoxLayout()
        self.goals_layout.addLayout(self.goal_rows)
        self.layout_.addWidget(self.goals_card)

        # Time split
        self.split_card, split_layout = card("Time split this week",
                                             "Routine / Habit / Improvement against your target.")
        change = QPushButton("Change targets…")
        change.clicked.connect(self.change_split)
        self.split_card.head.addWidget(change)
        self.split_rows = QVBoxLayout()
        split_layout.addLayout(self.split_rows)
        self.layout_.addWidget(self.split_card)

        # Compounding
        self.compound_card, compound_layout = card(
            "Compounding", "Your running total. Small daily effort adds up – keep the line rising.")
        self.compound_scope = QComboBox()
        self.compound_scope.currentIndexChanged.connect(lambda _: self._draw_compounding())
        self.compound_card.head.addWidget(self.compound_scope)
        self.compound_chart = CumulativeChart()
        compound_layout.addWidget(self.compound_chart)
        self.layout_.addWidget(self.compound_card)
        self.layout_.addStretch()

        scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ---------- drawing ----------

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout():
                GoalsTab._clear(item.layout())

    def refresh(self):
        today = date.today()
        items = goals.control_items(self.db, today)
        for grid, group in ((self.lead_grid, "lead"), (self.lag_grid, "lag")):
            self._clear(grid)
            for i, item in enumerate(x for x in items if x.group == group):
                grid.addWidget(self._tile(item), 0, i)
        self._draw_goals(today)
        self._draw_split(today)
        current = self.compound_scope.currentData()
        self.compound_scope.blockSignals(True)
        self.compound_scope.clear()
        for label, scope in scope_choices(self.db):
            self.compound_scope.addItem(label, scope)
        index = self.compound_scope.findData(current) if current else 0
        self.compound_scope.setCurrentIndex(max(index, 0))
        self.compound_scope.blockSignals(False)
        self._draw_compounding()

    def _tile(self, item: goals.ControlItem) -> QWidget:
        tile = QFrame(objectName="tile")
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        layout.addWidget(QLabel(item.name, objectName="tileCaption"))
        layout.addWidget(QLabel(item.value, objectName="tileValue"))
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel(item.target, objectName="tileDetail"))
        bottom.addStretch()
        bottom.addWidget(pill(item.status))
        layout.addLayout(bottom)
        tile.setToolTip(item.hint)
        return tile

    def _draw_goals(self, today: date):
        self._clear(self.goal_rows)
        all_goals = self.db.list_goals()
        if not all_goals:
            self.goal_rows.addWidget(QLabel(
                "No goals yet. Try a weekly rhythm such as “Learning AI: 10 🍅 a week”, "
                "or a target such as “Career: 20 🍅 by 30 Nov”.",
                objectName="cardNote", wordWrap=True))
            return
        for goal in all_goals:
            progress = goals.goal_progress(self.db, goal, today)
            row = QFrame(objectName="goalRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(4, 6, 4, 6)
            text = QVBoxLayout()
            text.setSpacing(2)
            scope = goals.scope_label(self.db, (goal["scope_kind"], goal["scope_value"]))
            text.addWidget(QLabel(f"<b>{goal['title']}</b> "
                                  f"<span style='color:#8B8D98'>· {scope}</span>"))
            bar = QProgressBar(textVisible=False, maximum=1000)
            bar.setValue(int(progress.fraction * 1000))
            bar.setFixedHeight(8)
            ink = PILL[progress.status][1]
            bar.setStyleSheet(f"QProgressBar::chunk {{ background: {ink}; border-radius: 3px; }}")
            text.addWidget(bar)
            text.addWidget(QLabel(f"{progress.text} · <span style='color:#8B8D98'>"
                                  f"{progress.detail}</span>", objectName="todoMeta"))
            layout.addLayout(text, 1)
            layout.addWidget(pill(progress.status), 0, Qt.AlignTop)
            row.setContextMenuPolicy(Qt.CustomContextMenu)
            row.customContextMenuRequested.connect(
                lambda pos, g=goal["id"], w=row: self._goal_menu(g, w.mapToGlobal(pos)))
            row.mouseDoubleClickEvent = lambda _e, g=goal["id"]: self.edit_goal(g)
            self.goal_rows.addWidget(row)

    def _draw_split(self, today: date):
        self._clear(self.split_rows)
        shares, unset = goals.nature_split(self.db, goals.week_start(today), today)
        targets = goals.split_targets(self.db)
        if not any(shares.values()):
            self.split_rows.addWidget(QLabel(
                "No pomodoros with a kind of work this week yet. Set “Kind of work” on tasks "
                "(recurring tasks default to Routine).", objectName="cardNote", wordWrap=True))
            return
        for key, label in NATURES.items():
            row = QHBoxLayout()
            name = QLabel(f"{NATURE_ICONS[key]} {label}")
            name.setFixedWidth(130)
            bar = QProgressBar(textVisible=False, maximum=100)
            bar.setValue(round(shares[key] * 100))
            bar.setFixedHeight(10)
            status = goals.split_status(shares[key], targets[key])
            bar.setStyleSheet(f"QProgressBar::chunk {{ background: {PILL[status][1]}; "
                              "border-radius: 4px; }")
            row.addWidget(name)
            row.addWidget(bar, 1)
            value = QLabel(f"{shares[key]:.0%}  (target {targets[key]}%)")
            value.setFixedWidth(150)
            row.addWidget(value)
            row.addWidget(pill(status))
            self.split_rows.addLayout(row)
        if unset:
            self.split_rows.addWidget(QLabel(f"{unset} pomodoro(s) on tasks without a kind of "
                                             "work aren't counted.", objectName="cardNote"))

    def _draw_compounding(self):
        scope = parse_scope(self.compound_scope.currentData())
        extra, params = goals._scope_sql(scope)
        first = self.db.conn.execute(
            "SELECT MIN(substr(s.start_time, 1, 10)) FROM sessions s "
            f"LEFT JOIN tasks t ON t.id = s.task_id WHERE s.kind = 'focus' AND s.completed = 1"
            f"{extra}", params).fetchone()[0]
        if not first:
            self.compound_chart.set_points([])
            return
        start = max(date.fromisoformat(first), date.today() - timedelta(days=180))
        rows = dict(self.db.conn.execute(
            "SELECT substr(s.start_time, 1, 10), SUM(s.completed) FROM sessions s "
            "LEFT JOIN tasks t ON t.id = s.task_id WHERE s.kind = 'focus' "
            f"AND s.start_time >= ?{extra} GROUP BY 1", [start.isoformat(), *params]).fetchall())
        before = goals.pomodoros(self.db, date(2000, 1, 1), start - timedelta(days=1), scope)
        points, total, day = [], before, start
        while day <= date.today():
            total += rows.get(day.isoformat(), 0) or 0
            points.append((day, total))
            day += timedelta(days=1)
        self.compound_chart.set_points(points)

    # ---------- actions ----------

    def new_goal(self):
        if GoalDialog(self.db, parent=self).exec():
            self.refresh()

    def edit_goal(self, goal_id: int):
        if GoalDialog(self.db, goal_id, parent=self).exec():
            self.refresh()

    def _goal_menu(self, goal_id: int, pos):
        menu = QMenu(self)
        menu.addAction("Edit…", lambda: self.edit_goal(goal_id))
        menu.addAction("Delete…", lambda: self._delete_goal(goal_id))
        menu.exec(pos)

    def _delete_goal(self, goal_id: int):
        goal = self.db.get_goal(goal_id)
        if QMessageBox.question(self, "Delete goal",
                                f'Delete the goal "{goal["title"]}"?') == QMessageBox.Yes:
            self.db.delete_goal(goal_id)
            self.refresh()

    def change_split(self):
        if SplitDialog(self.db, self).exec():
            self.refresh()
