"""The Today tab: your day on one page, with Plan my day and Close the day.

Morning: routines and habits appear by themselves; "Plan my day" picks a few focus
tasks and checks them against what your daily goal allows.
Evening: "Close the day" shows today's numbers, moves unfinished planned tasks,
lets you plan tomorrow, and sends (or copies) a short summary to your Notion Journal.
"""

from datetime import date, timedelta

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QListWidget, QListWidgetItem, QMenu,
                               QProgressBar, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from pomodoro import goals, planning
from pomodoro.database import Database
from pomodoro.lists import remaining_estimate
from pomodoro.models import PRIORITIES, due_label
from pomodoro.ui.clipboard import copy_text
from pomodoro.ui.goals_tab import PILL, card, pill
from pomodoro.ui.notion_ui import (is_connected, notion_client, notion_enabled,
                                   run_in_background)
from pomodoro.notion import NotionError, parse_id
from pomodoro.ui.reports_tab import LabelDialog
from pomodoro.ui.task_dialog import TaskDialog
from pomodoro.ui.todo_tab import TaskRow, add_repeat_text


def day_name(day: date) -> str:
    today = date.today()
    return "Today" if day == today else "Tomorrow" if day == today + timedelta(days=1) \
        else day.strftime("%a %d %b")


class PlanDialog(QDialog):
    """Pick the focus tasks for a day, checked against what your daily goal allows."""

    def __init__(self, db: Database, day: date, score_order: dict, parent=None):
        super().__init__(parent)
        self.db, self.day = db, day
        name = day_name(day)
        self.setWindowTitle(f"Plan {name.lower() if name in ('Today', 'Tomorrow') else name}")
        self.setMinimumSize(520, 460)

        if day == date.today():
            cap = planning.capacity(db, day)
            self.available, self.routine = cap.available, cap.routine
        else:   # a future day: full goal, minus the routines/habits coming that day
            upcoming = db.upcoming_occurrences(day, day)
            self.available = db.get_int("daily_goal")
            self.routine = sum(u["estimate_pomodoros"] or 0 for u in upcoming)

        self.list = QListWidget()
        tasks = [t for t in db.list_tasks("open") if not t["recurrence_id"]]
        tasks.sort(key=lambda t: (score_order.get(t["id"], len(score_order)), t["id"]))
        for task in tasks:
            est = remaining_estimate(task)
            details = [PRIORITIES[task["priority"]]]
            if est:
                details.append(f"{est} 🍅 left")
            if task["due_date"]:
                details.append("due " + due_label(task["due_date"]).lower())
            if task["project"]:
                details.append(task["project"])
            item = QListWidgetItem(f"{task['title']}   ·   " + " · ".join(details))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if task["planned_date"] == day.isoformat()
                               else Qt.Unchecked)
            item.setData(Qt.UserRole, (task["id"], est))
            self.list.addItem(item)
        self.list.itemChanged.connect(lambda _: self._update())

        self.summary = QLabel(objectName="cardNote", wordWrap=True)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Tick the few tasks you'll focus on (best first, by Focus Score). Routines and "
            "habits are already on the plan.", objectName="cardNote", wordWrap=True))
        layout.addWidget(self.list, 1)
        layout.addWidget(self.summary)
        layout.addWidget(buttons)
        self._update()

    def _checked(self) -> list[tuple[int, int]]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]

    def _update(self):
        chosen = self._checked()
        planned = sum(est for _, est in chosen)
        room = max(self.available - self.routine, 0)
        text = (f"{len(chosen)} task(s), {planned} 🍅 planned · routines & habits need "
                f"{self.routine} 🍅 · room left in your goal: {room} 🍅")
        if planned > room:
            text += f"  –  ⚠ {planned - room} 🍅 too many; consider fewer tasks."
        self.summary.setText(text)

    def _save(self):
        chosen = {task_id for task_id, _ in self._checked()}
        for i in range(self.list.count()):
            task_id, _ = self.list.item(i).data(Qt.UserRole)
            was = self.db.get_task(task_id)["planned_date"] == self.day.isoformat()
            if task_id in chosen and not was:
                self.db.plan_task(task_id, self.day)
            elif task_id not in chosen and was:
                self.db.plan_task(task_id, None)
        self.accept()


class CloseDayDialog(QDialog):
    """Evening check: numbers, unfinished tasks, plan tomorrow, Notion Journal summary."""

    def __init__(self, db: Database, score_order: dict, parent=None):
        super().__init__(parent)
        self.db, self.score_order = db, score_order
        self.setWindowTitle("Close the day")
        self.setMinimumWidth(520)
        today = date.today()
        self.summary = planning.day_summary(db, today)
        s = self.summary

        layout = QVBoxLayout(self)
        hours, mins = divmod(s.focus_minutes, 60)
        lines = [f"<b>{s.pomodoros} 🍅</b> · {hours} h {mins} min of focus",
                 f"<b>{len(s.finished)}</b> task(s) done"
                 + (": " + "; ".join(s.finished) if s.finished else "")]
        if s.habits[1]:
            lines.append(f"Habits <b>{s.habits[0]}/{s.habits[1]}</b>")
        if s.routines[1]:
            lines.append(f"Routines <b>{s.routines[0]}/{s.routines[1]}</b>")
        if s.stopped or s.distractions:
            lines.append(f"Interruptions: {s.stopped} stopped early ({s.minutes_lost} min lost), "
                         f"{s.distractions} distraction(s)"
                         + (f" – top cause <b>{s.top_cause}</b>" if s.top_cause else ""))
        numbers = QLabel("<br>".join(lines), wordWrap=True)
        numbers.setTextFormat(Qt.RichText)
        layout.addWidget(numbers)

        waiting = len(db.unlabelled_anomalies())
        if waiting:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{waiting} event(s) still need a reason.",
                                 objectName="cardNote"))
            label = QPushButton("Label…")
            label.clicked.connect(lambda: LabelDialog(db, self).exec())
            row.addWidget(label)
            row.addStretch()
            layout.addLayout(row)

        self.move_boxes = []
        if s.unfinished_planned:
            layout.addWidget(QLabel("<b>Not finished from today's plan</b> – move to tomorrow?"))
            for task in s.unfinished_planned:
                box = QCheckBox(task["title"].replace("&", "&&"))   # "&" isn't a shortcut
                box.setChecked(True)
                box.task_id = task["id"]
                layout.addWidget(box)
                self.move_boxes.append(box)

        actions = QHBoxLayout()
        plan = QPushButton("Plan tomorrow…")
        plan.clicked.connect(self._plan_tomorrow)
        use_notion = notion_enabled(db)
        if use_notion:
            copy = QPushButton("Copy for Notion Journal")
            copy.setToolTip("Copies today's numbers for your Journal's “What happened?”. "
                            "Write the reflection itself in Notion.")
        else:
            copy = QPushButton("Copy day summary")
            copy.setToolTip("Copies today's numbers – paste them into your journal or notes.")
        copy.clicked.connect(self._copy)
        self.send = QPushButton("Send to Notion Journal")
        self.send.setToolTip("Adds today's numbers to today's Journal entry (creates it if "
                             "needed). Your own text there is never changed.")
        self.send.clicked.connect(self._send)
        self.send.setVisible(is_connected(db) and bool(db.get_setting("notion_journal_url")))
        copy.setVisible(not self.send.isVisible())
        journal = QPushButton("Open Notion Journal ↗")
        journal.clicked.connect(self._open_journal)
        journal.setVisible(use_notion)
        for button in (plan, self.send, copy, journal):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.copied = QLabel(objectName="cardNote", wordWrap=True)
        layout.addWidget(self.copied)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Done")
        buttons.accepted.connect(self._done)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _plan_tomorrow(self):
        self._apply_moves()
        PlanDialog(self.db, date.today() + timedelta(days=1), self.score_order, self).exec()

    def _copy(self):
        if copy_text(self, self.summary.journal_text()):
            self.copied.setText("Copied. Paste it into today's Journal entry (What happened?)."
                                if notion_enabled(self.db) else
                                "Copied. Paste it into your journal or notes.")

    def _send(self):
        try:                                     # read settings here, not in the worker
            client = notion_client(self.db)
            journal = parse_id(self.db.get_setting("notion_journal_url"))
        except NotionError as error:
            self.copied.setText(f"✗ {error}")
            return
        day, text = date.today(), self.summary.journal_text()

        def work():
            return client.send_journal(journal, day, text)

        def done(url, error):
            self.send.setEnabled(True)
            if error:
                self.copied.setText(f"✗ {error}")
                return
            self.journal_entry = url
            self.copied.setText("Sent to today's Journal entry – add your reflection there.")

        self.send.setEnabled(False)
        self.copied.setText("Sending…")
        run_in_background(self, work, done)

    def _open_journal(self):
        if getattr(self, "journal_entry", None):
            QDesktopServices.openUrl(QUrl(self.journal_entry))
            return
        url = self.db.get_setting("notion_journal_url")
        if not url:
            url, ok = QInputDialog.getText(
                self, "Notion Journal", "Paste the link to your Notion Journal (once):")
            if not ok or not url.strip().startswith("http"):
                return
            url = url.strip()
            self.db.set_setting("notion_journal_url", url)
        QDesktopServices.openUrl(QUrl(url))

    def _apply_moves(self):
        tomorrow = date.today() + timedelta(days=1)
        planning.move_to(self.db, [b.task_id for b in self.move_boxes if b.isChecked()], tomorrow)
        for box in self.move_boxes:
            box.setEnabled(False)
        self.move_boxes = []

    def _done(self):
        self._apply_moves()
        self.accept()


class TodayTab(QWidget):
    start_requested = Signal(int)
    tasks_changed = Signal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        # Set by the app: {task id: position in the Focus Score ranking}.
        self.score_order = lambda: {}

        content = QWidget(objectName="todoMain")
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(24, 16, 24, 16)
        self.body.setSpacing(12)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        self.date_label = QLabel(objectName="todoHeading")
        titles.addWidget(self.date_label)
        titles.addWidget(QLabel("Plan in the morning · focus · close the day in the evening",
                                objectName="cardNote"))
        head.addLayout(titles, 1)
        plan = QPushButton("☀ Plan my day…")
        plan.clicked.connect(self.plan_day)
        close = QPushButton("☾ Close the day…")
        close.clicked.connect(self.close_day)
        head.addWidget(plan)
        head.addWidget(close)
        self.body.addLayout(head)

        self.capacity_card, cap_layout = card("Capacity")
        self.capacity_bar = QProgressBar(textVisible=False, maximum=1000)
        self.capacity_bar.setFixedHeight(10)
        self.capacity_text = QLabel(wordWrap=True)
        cap_layout.addWidget(self.capacity_bar)
        cap_layout.addWidget(self.capacity_text)
        self.body.addWidget(self.capacity_card)

        self.routine_card, self.routine_rows = card("Routines & habits")
        self.body.addWidget(self.routine_card)
        self.focus_card, self.focus_rows = card("Today's focus")
        self.body.addWidget(self.focus_card)
        self.goals_card, self.goal_rows = card("Goals at a glance")
        self.body.addWidget(self.goals_card)
        self.body.addStretch()

        scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ---------- drawing ----------

    @staticmethod
    def _clear(layout: QVBoxLayout, keep: int):
        """Remove everything after the first `keep` items (the card's header/note)."""
        while layout.count() > keep:
            item = layout.takeAt(keep)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def refresh(self):
        today = date.today()
        self.date_label.setText(today.strftime("%A %d %B"))
        routine, planned = planning.day_tasks(self.db, today)
        add_repeat_text(self.db, routine)

        cap = planning.capacity(self.db, today)
        fraction = cap.needed / cap.available if cap.available else (1 if cap.needed else 0)
        status = "good" if cap.over == 0 else "warning" if cap.over <= 2 else "critical"
        self.capacity_bar.setValue(int(min(fraction, 1) * 1000))
        self.capacity_bar.setStyleSheet(
            f"QProgressBar::chunk {{ background: {PILL[status][1]}; border-radius: 4px; }}")
        text = (f"Still to do: <b>{cap.needed} 🍅</b> (routines & habits {cap.routine}, "
                f"focus tasks {cap.planned}) · your goal leaves <b>{cap.available} 🍅</b> today "
                f"({cap.done} done of {cap.goal}).")
        if cap.over:
            text += f" <span style='color:{PILL[status][1]}'>⚠ {cap.over} 🍅 more than fits.</span>"
        self.capacity_text.setText(text)

        self._clear(self.routine_rows, 1)
        for task in routine:
            self.routine_rows.addWidget(self._row(task))
        if not routine:
            self.routine_rows.addWidget(QLabel(
                "No routines or habits today. Add one in To-Do → Recurring.", objectName="cardNote"))

        self._clear(self.focus_rows, 1)
        for task in planned:
            self.focus_rows.addWidget(self._row(task))
        if not planned:
            self.focus_rows.addWidget(QLabel(
                "Nothing planned yet. Click ☀ Plan my day… to pick a few focus tasks.",
                objectName="cardNote", wordWrap=True))
        overdue = self.db.conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status NOT IN ('done', 'missed') "
            "AND recurrence_id IS NULL AND due_date < ? "
            "AND (planned_date IS NULL OR planned_date != ?)",
            (today.isoformat(), today.isoformat())).fetchone()[0]
        if overdue:
            self.focus_rows.addWidget(QLabel(
                f"{overdue} overdue task(s) aren't on today's plan – see To-Do → Today.",
                objectName="cardNote"))

        self._clear(self.goal_rows, 1)
        for goal in self.db.list_goals():
            progress = goals.goal_progress(self.db, goal, today)
            row = QHBoxLayout()
            row.addWidget(QLabel(f"<b>{goal['title']}</b> · {progress.text}"), 1)
            row.addWidget(pill(progress.status))
            holder = QWidget()
            holder.setLayout(row)
            self.goal_rows.addWidget(holder)
        if not self.db.list_goals():
            self.goal_rows.addWidget(QLabel("No goals yet – add some in the Goals tab.",
                                            objectName="cardNote"))

    def _row(self, task: dict) -> TaskRow:
        row = TaskRow(task, show_project=True, today=date.today())
        row.toggled.connect(self._toggle)
        row.start.connect(self.start_requested.emit)
        row.edit.connect(self._edit)
        row.menu_requested.connect(self._menu)
        return row

    # ---------- actions ----------

    def _changed(self):
        self.refresh()
        self.tasks_changed.emit()

    def _toggle(self, task_id: int):
        task = self.db.get_task(task_id)
        self.db.set_task_status(task_id, "todo" if task["status"] == "done" else "done")
        self._changed()

    def _edit(self, task_id: int):
        if TaskDialog(self.db, task_id, parent=self).exec():
            self._changed()

    def _menu(self, task_id: int, pos):
        task = self.db.get_task(task_id)
        menu = QMenu(self)
        if task["status"] not in ("done", "missed"):
            menu.addAction("▶  Start pomodoro", lambda: self.start_requested.emit(task_id))
        menu.addAction("Edit…", lambda: self._edit(task_id))
        menu.addAction("Reopen" if task["status"] == "done" else "✓  Mark done",
                       lambda: self._toggle(task_id))
        if not task["recurrence_id"]:
            menu.addAction("Move to tomorrow", lambda: (
                self.db.plan_task(task_id, date.today() + timedelta(days=1)), self._changed()))
            menu.addAction("Remove from today's plan",
                           lambda: (self.db.plan_task(task_id, None), self._changed()))
        menu.exec(pos)

    def plan_day(self):
        if PlanDialog(self.db, date.today(), self.score_order(), self).exec():
            self._changed()

    def close_day(self):
        dialog = CloseDayDialog(self.db, self.score_order(), self)
        dialog.exec()
        self._changed()
