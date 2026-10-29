"""Dialog for adding or editing a task, or a recurring series.

Modes:
  * new task          - can be one-off or repeating (Daily / Weekly / Monthly)
  * edit task         - a one-off task
  * edit occurrence   - one day of a series; on Save you choose "just this one" or
                        "this and all future ones"
  * edit series       - the series itself (from the Recurring list)
"""

from datetime import date

from PySide6.QtCore import QDate, QTime, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                               QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QTimeEdit,
                               QVBoxLayout, QWidget)

from pomodoro import goals
from pomodoro.database import Database
from pomodoro.models import (DEFAULT_PRIORITY, ENERGY_SLOTS, NATURE_HINTS, NATURES, PRIORITIES,
                             STATUSES)
from pomodoro.recurrence import DAY_NAMES, FREQUENCIES, Schedule, schedule_from_row
from pomodoro.ui.notion_ui import notion_enabled
from pomodoro.ui.project_picker import ProjectPicker

JUST_THIS, THIS_AND_FUTURE = "this", "future"


def to_qdate(day: date) -> QDate:
    return QDate(day.year, day.month, day.day)


def from_qdate(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


class TaskDialog(QDialog):
    def __init__(self, db: Database, task_id: int | None = None, parent=None,
                 project_id: int | None = None, recurrence_id: int | None = None):
        super().__init__(parent)
        self.db = db
        self.task_id = task_id
        self.default_project_id = project_id
        task = db.get_task(task_id) if task_id else None
        # The series this dialog edits (series mode), or the one the task belongs to
        self.recurrence_id = recurrence_id or (task["recurrence_id"] if task else None)
        self.series = db.get_recurrence(self.recurrence_id) if self.recurrence_id else None
        self.series_mode = recurrence_id is not None and task_id is None
        self.task = task

        if self.series_mode:
            title = "Edit recurring task"
        elif task and self.series:
            title = "Edit occurrence"
        else:
            title = "Edit task" if task else "New task"
        self.setWindowTitle(title)
        self.setMinimumWidth(460)

        # ----- fields -----
        self.title_input = QLineEdit(placeholderText="e.g. Fix login bug")
        self.project_input = ProjectPicker(db)

        self.nature_input = QComboBox()
        for key, label in NATURES.items():
            self.nature_input.addItem(label, key)
        self.nature_input.setToolTip("Routine: keeps things running · Habit: small repeated "
                                     "action that builds who you are · Improvement: moves "
                                     "things forward")
        self._nature_touched = False
        self.nature_input.activated.connect(lambda _: setattr(self, "_nature_touched", True))
        self.nature_hint = QLabel(objectName="cardNote", wordWrap=True)
        self.nature_input.currentIndexChanged.connect(
            lambda _: self.nature_hint.setText(NATURE_HINTS.get(self.nature_input.currentData(), "")))

        # Pick a category, or type a new name to create one.
        self.category_input = QComboBox(editable=True)
        self.category_input.addItem("")
        self.category_input.addItems([c["name"] for c in db.list_categories()])
        self.category_input.lineEdit().setPlaceholderText("Pick or type a new category")

        self.type_input = QComboBox()
        for task_type in db.list_types():
            self.type_input.addItem(task_type["name"], task_type["key"])

        self.priority_input = QComboBox()
        for key, label in PRIORITIES.items():
            self.priority_input.addItem(label, key)

        self.energy_input = QComboBox()
        self.energy_input.addItem("Any time", None)
        for key, label in ENERGY_SLOTS.items():
            self.energy_input.addItem(label, key)

        # ----- repeat -----
        self.repeat_input = QComboBox()
        self.repeat_input.addItem("Does not repeat", None)
        for key, label in FREQUENCIES.items():
            self.repeat_input.addItem(label, key)

        self.has_due = QCheckBox("Due")
        self.due_input = QDateEdit(calendarPopup=True, displayFormat="ddd dd MMM yyyy")
        self.due_input.setDate(QDate.currentDate())
        self.has_due.toggled.connect(self.due_input.setEnabled)
        self.due_widget = QWidget()
        due_row = QHBoxLayout(self.due_widget)
        due_row.setContentsMargins(0, 0, 0, 0)
        due_row.addWidget(self.has_due)
        due_row.addWidget(self.due_input, 1)

        self.start_input = QDateEdit(calendarPopup=True, displayFormat="ddd dd MMM yyyy")
        self.start_input.setDate(QDate.currentDate())
        self.end_input = QDateEdit(calendarPopup=True, displayFormat="ddd dd MMM yyyy")
        self.end_input.setDate(QDate.currentDate().addMonths(1))
        self.range_widget = QWidget()
        range_row = QHBoxLayout(self.range_widget)
        range_row.setContentsMargins(0, 0, 0, 0)
        range_row.addWidget(QLabel("from"))
        range_row.addWidget(self.start_input, 1)
        range_row.addWidget(QLabel("until"))
        range_row.addWidget(self.end_input, 1)

        self.workdays_input = QCheckBox("Working days only (as set in Settings)")
        self.workdays_input.setChecked(True)
        self.day_boxes = [QCheckBox(name) for name in DAY_NAMES]
        self.weekdays_widget = QWidget()
        days_row = QHBoxLayout(self.weekdays_widget)
        days_row.setContentsMargins(0, 0, 0, 0)
        for box in self.day_boxes:
            days_row.addWidget(box)
        self.month_day_input = QSpinBox(minimum=1, maximum=31, prefix="Day ")
        self.month_day_input.setToolTip("29-31 fall back to the last day in shorter months")
        self.summary_label = QLabel(objectName="cardNote", wordWrap=True)

        # Habit cue (Atomic Habits: "I will [do it] at [time] in [place]")
        self.has_cue = QCheckBox("at")
        self.cue_time_input = QTimeEdit(displayFormat="HH:mm")
        self.cue_time_input.setTime(QTime(8, 30))
        self.cue_place_input = QLineEdit(placeholderText="where, e.g. at my desk")
        self.cue_widget = QWidget()
        cue_row = QHBoxLayout(self.cue_widget)
        cue_row.setContentsMargins(0, 0, 0, 0)
        cue_row.addWidget(self.has_cue)
        cue_row.addWidget(self.cue_time_input)
        cue_row.addWidget(self.cue_place_input, 1)
        self.remind_input = QCheckBox("Remind me at the cue time")
        self.remind_input.setChecked(True)
        self.has_cue.toggled.connect(self.cue_time_input.setEnabled)
        self.has_cue.toggled.connect(self.remind_input.setEnabled)

        # Habit stacking: "After [current habit], I will [new habit]"
        self.stack_input = QComboBox()
        self.stack_input.addItem("Not linked to another task", None)
        for rec in db.list_recurrences(include_stopped=False):
            if rec["id"] != self.recurrence_id:
                self.stack_input.addItem(f"After: {rec['title']}", rec["id"])

        self.two_minute_input = QLineEdit(
            placeholderText="The smallest version, e.g. open the book and read one page")
        self.intention_label = QLabel(objectName="intention", wordWrap=True)

        self.estimate_input = QSpinBox(minimum=0, maximum=200, suffix=" 🍅",
                                       specialValueText="No estimate")
        # Learned estimate (Falconi's "standard time"): what similar tasks really took.
        self.estimate_hint = QLabel(objectName="cardNote", wordWrap=True)
        self.estimate_use = QPushButton("Use", objectName="small")
        self.estimate_use.clicked.connect(
            lambda: self.estimate_input.setValue(self._suggestion[0]))
        self.estimate_hint_widget = QWidget()
        hint_row = QHBoxLayout(self.estimate_hint_widget)
        hint_row.setContentsMargins(0, 0, 0, 0)
        hint_row.addWidget(self.estimate_hint, 1)
        hint_row.addWidget(self.estimate_use)
        self._suggestion = None

        self.status_input = QComboBox()
        for key, label in STATUSES.items():
            self.status_input.addItem(label, key)

        self.checklist_input = QPlainTextEdit(
            placeholderText="Optional: one step per line, e.g.\nCollect numbers\nUpdate chart\n"
                            "Send to team")
        self.checklist_input.setFixedHeight(64)
        self.notes_input = QPlainTextEdit(placeholderText="Optional notes")
        self.notes_input.setFixedHeight(56)

        # Optional link to a page with the background (e.g. Notion; notes stay there).
        use_notion = notion_enabled(db)
        self.notion_input = QLineEdit(placeholderText="Paste a Notion page link (optional)"
                                      if use_notion else
                                      "Paste a link to notes or a document (optional)")
        self.notion_open = QPushButton("Open")
        self.notion_open.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(self.notion_input.text().strip())))
        self.notion_input.textChanged.connect(
            lambda text: self.notion_open.setEnabled(text.strip().startswith("http")))
        self.notion_open.setEnabled(False)
        notion_row = QHBoxLayout()
        notion_row.addWidget(self.notion_input, 1)
        notion_row.addWidget(self.notion_open)

        form = QFormLayout()
        self.form = form
        form.addRow("Task", self.title_input)
        form.addRow("Project", self.project_input)
        form.addRow("Kind of work", self.nature_input)
        form.addRow("", self.nature_hint)
        form.addRow("Category", self.category_input)
        form.addRow("Type", self.type_input)
        form.addRow("Priority", self.priority_input)
        form.addRow("Energy slot", self.energy_input)
        form.addRow("Repeat", self.repeat_input)
        form.addRow("Due date", self.due_widget)
        form.addRow("Repeats", self.range_widget)
        form.addRow("", self.workdays_input)
        form.addRow("On", self.weekdays_widget)
        form.addRow("On", self.month_day_input)
        form.addRow("", self.summary_label)
        form.addRow("Cue", self.cue_widget)
        form.addRow("", self.remind_input)
        form.addRow("Stack", self.stack_input)
        form.addRow("2-minute version", self.two_minute_input)
        form.addRow("", self.intention_label)
        form.addRow("Estimate", self.estimate_input)
        form.addRow("", self.estimate_hint_widget)
        form.addRow("Status", self.status_input)
        form.addRow("Checklist", self.checklist_input)
        form.addRow("Notes", self.notes_input)
        form.addRow("Notion" if use_notion else "Link", notion_row)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 6, 0)
        body_layout.addLayout(form)
        if task:
            minutes = round(task["focus_minutes"])
            body_layout.addWidget(QLabel(f"Logged so far: 🍅 {task['pomodoros']}  ·  {minutes} min"))
        scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        scroll.setWidget(body)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addWidget(buttons)

        for signal in (self.repeat_input.currentIndexChanged, self.start_input.dateChanged,
                       self.end_input.dateChanged, self.workdays_input.toggled,
                       self.month_day_input.valueChanged):
            signal.connect(lambda *_: self._update_repeat())
        for box in self.day_boxes:
            box.toggled.connect(lambda *_: self._update_repeat())
        for signal in (self.has_cue.toggled, self.cue_time_input.timeChanged,
                       self.cue_place_input.textChanged, self.stack_input.currentIndexChanged,
                       self.title_input.textChanged, self.two_minute_input.textChanged):
            signal.connect(lambda *_: self._update_intention())

        self._load(task)
        self.nature_hint.setText(NATURE_HINTS.get(self.nature_input.currentData(), ""))
        self.category_input.currentTextChanged.connect(lambda _: self._update_estimate_hint())
        self.type_input.currentIndexChanged.connect(lambda _: self._update_estimate_hint())
        self._update_estimate_hint()
        self._update_repeat()
        self._update_intention()
        self._fit_to_screen(body)

    # ---------- layout helpers ----------

    def _fit_to_screen(self, body: QWidget):
        """Never taller than the screen: the form scrolls instead."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        available = screen.availableGeometry().height() - 60
        wanted = body.sizeHint().height() + 70
        self.resize(max(self.minimumWidth(), body.sizeHint().width() + 40),
                    min(wanted, available))

    def _set_row_visible(self, field: QWidget, visible: bool):
        label = self.form.labelForField(field)
        field.setVisible(visible)
        if label is not None:
            label.setVisible(visible)

    def _frequency(self) -> str | None:
        return self.repeat_input.currentData()

    def _schedule(self) -> Schedule | None:
        """The schedule from the form, or None if not repeating / not valid yet."""
        frequency = self._frequency()
        if frequency is None:
            return None
        try:
            return Schedule(frequency, from_qdate(self.start_input.date()),
                            from_qdate(self.end_input.date()), self.workdays_input.isChecked(),
                            [i for i, box in enumerate(self.day_boxes) if box.isChecked()],
                            self.month_day_input.value())
        except ValueError:
            return None

    def _update_repeat(self):
        frequency = self._frequency()
        repeating = frequency is not None
        self._set_row_visible(self.due_widget, not repeating)
        self._set_row_visible(self.range_widget, repeating)
        self._set_row_visible(self.workdays_input, frequency == "daily")
        self._set_row_visible(self.weekdays_widget, frequency == "weekly")
        self._set_row_visible(self.month_day_input, frequency == "monthly")
        self._set_row_visible(self.summary_label, repeating)
        for widget in (self.cue_widget, self.remind_input, self.stack_input,
                       self.two_minute_input, self.intention_label):
            self._set_row_visible(widget, repeating)
        # A series has no status of its own; each occurrence has one.
        self._set_row_visible(self.status_input, not self.series_mode and
                              not (repeating and self.task is None))
        self.form.labelForField(self.estimate_input).setText(
            "Estimate (each time)" if repeating else "Estimate")
        if repeating and not self._nature_touched and self.task is None and not self.series:
            self.nature_input.setCurrentIndex(self.nature_input.findData("routine"))
        if not repeating and not self._nature_touched and self.task is None:
            self.nature_input.setCurrentIndex(self.nature_input.findData("improvement"))
        if repeating:
            schedule = self._schedule()
            if schedule is None:
                end_before = from_qdate(self.end_input.date()) < from_qdate(self.start_input.date())
                self.summary_label.setText("⚠ 'Until' must be on or after the start date."
                                           if end_before else "⚠ Pick at least one day.")
            else:
                times = schedule.count(self.db.get_working_days())
                self.summary_label.setText(
                    f"{schedule.describe()} – {times} time{'s' if times != 1 else ''}."
                    if times else "⚠ No days match in this range.")

    def _update_estimate_hint(self):
        name = " ".join(self.category_input.currentText().split())
        row = self.db.conn.execute("SELECT id FROM categories WHERE name = ? COLLATE NOCASE",
                                   (name,)).fetchone() if name else None
        self._suggestion = goals.suggest_estimate(self.db, row[0] if row else None,
                                                  self.type_input.currentData())
        if self._suggestion:
            value, samples, label = self._suggestion
            self.estimate_hint.setText(f"Usually ~{value} 🍅 for {label} "
                                       f"(median of {samples} finished tasks).")
        self.estimate_hint_widget.setVisible(self._suggestion is not None)
        label = self.form.labelForField(self.estimate_hint_widget)
        if label is not None:
            label.setVisible(self._suggestion is not None)

    def _update_intention(self):
        """Spell the habit out as an implementation intention."""
        name = " ".join(self.title_input.text().split()) or "do it"
        parts = []
        stack = self.stack_input.currentData()
        if stack is not None:
            after = self.stack_input.currentText().removeprefix("After: ")
            parts.append(f"After {after}, I will {name}")
        else:
            parts.append(f"I will {name}")
        if self.has_cue.isChecked():
            parts[0] += " at " + self.cue_time_input.time().toString("HH:mm")
        place = self.cue_place_input.text().strip()
        if place:
            parts[0] += " " + place
        text = parts[0] + "."
        if self.two_minute_input.text().strip():
            text += f" On a hard day: {self.two_minute_input.text().strip()}."
        self.intention_label.setText("💡 " + text)

    # ---------- load ----------

    def _load(self, task: dict | None):
        source = self.series if self.series_mode else task
        if source is None:                       # new task
            self.priority_input.setCurrentIndex(self.priority_input.findData(DEFAULT_PRIORITY))
            self.project_input.set_project_id(self.default_project_id
                                              or self.db.last_project_id())
            self.nature_input.setCurrentIndex(self.nature_input.findData("improvement"))
            self.has_due.setChecked(False)
            self.due_input.setEnabled(False)
            self.day_boxes[date.today().weekday()].setChecked(True)
            self.month_day_input.setValue(date.today().day)
            self.has_cue.setChecked(False)
            self.cue_time_input.setEnabled(False)
            self.remind_input.setEnabled(False)
            return

        self.title_input.setText(source["title"])
        category = self.db.conn.execute("SELECT name FROM categories WHERE id = ?",
                                        (source["category_id"],)).fetchone()
        self.category_input.setCurrentText(category["name"] if category else "")
        self.project_input.set_project_id(source["project_id"])
        self.nature_input.setCurrentIndex(max(self.nature_input.findData(source["nature"]), 0)
                                          if source["nature"] else
                                          self.nature_input.findData("improvement"))
        self.type_input.setCurrentIndex(max(self.type_input.findData(source["type"]), 0))
        self.priority_input.setCurrentIndex(self.priority_input.findData(source["priority"]))
        self.energy_input.setCurrentIndex(max(self.energy_input.findData(source["energy_slot"]), 0))
        self.notion_input.setText(source["notion_url"] or "")
        self.estimate_input.setValue(source["estimate_pomodoros"] or 0)
        self.checklist_input.setPlainText(source["checklist"] or "")
        self.notes_input.setPlainText(source["notes"] or "")
        if task is not None:
            self.status_input.setCurrentIndex(self.status_input.findData(task["status"]))
            self.has_due.setChecked(bool(task["due_date"]))
            self.due_input.setEnabled(bool(task["due_date"]))
            if task["due_date"]:
                self.due_input.setDate(QDate.fromString(task["due_date"][:10], "yyyy-MM-dd"))

        if self.series:
            schedule = schedule_from_row(self.series)
            self.repeat_input.setCurrentIndex(self.repeat_input.findData(schedule.frequency))
            self.start_input.setDate(to_qdate(schedule.start))
            self.end_input.setDate(to_qdate(schedule.end))
            self.workdays_input.setChecked(schedule.workdays_only)
            for i, box in enumerate(self.day_boxes):
                box.setChecked(i in schedule.weekdays)
            self.month_day_input.setValue(schedule.month_day or schedule.start.day)
            cue = self.series.get("cue_time")
            self.has_cue.setChecked(bool(cue))
            if cue:
                hours, minutes = (int(x) for x in cue.split(":"))
                self.cue_time_input.setTime(QTime(hours, minutes))
            self.cue_place_input.setText(self.series.get("cue_place") or "")
            self.remind_input.setChecked(bool(self.series.get("remind", 1)))
            self.stack_input.setCurrentIndex(
                max(self.stack_input.findData(self.series.get("stack_after_id")), 0))
            self.two_minute_input.setText(self.series.get("two_minute") or "")
        else:
            # Turning an existing one-off task into a series isn't supported (yet).
            self.repeat_input.setEnabled(False)
            self.repeat_input.setToolTip("To make something repeat, add it as a new "
                                         "recurring task.")
        self._nature_touched = True

    # ---------- save ----------

    def _common_values(self) -> dict:
        return {
            "title": self.title_input.text(),
            "category_id": self.db.get_or_create_category(self.category_input.currentText()),
            "project_id": self.project_input.project_id(),
            "type": self.type_input.currentData(),
            "priority": self.priority_input.currentData(),
            "energy_slot": self.energy_input.currentData(),
            "nature": self.nature_input.currentData(),
            "notion_url": self.notion_input.text(),
            "estimate_pomodoros": self.estimate_input.value() or None,
            "checklist": self.checklist_input.toPlainText(),
            "notes": self.notes_input.toPlainText().strip() or None,
        }

    def _schedule_values(self, schedule: Schedule) -> dict:
        cue = self.cue_time_input.time().toString("HH:mm") if self.has_cue.isChecked() else None
        return {
            "cue_time": cue,
            "cue_place": self.cue_place_input.text(),
            "remind": int(self.remind_input.isChecked()),
            "stack_after_id": self.stack_input.currentData(),
            "two_minute": self.two_minute_input.text(),
            "frequency": schedule.frequency,
            "workdays_only": int(schedule.workdays_only),
            "weekdays": schedule.weekdays,
            "month_day": schedule.month_day,
            "start_date": schedule.start.isoformat(),
            "end_date": schedule.end.isoformat(),
        }

    def values(self) -> dict:
        """Values for a one-off task (kept for callers and tests)."""
        due = from_qdate(self.due_input.date()).isoformat() if self.has_due.isChecked() else None
        return {**self._common_values(), "due_date": due,
                "status": self.status_input.currentData()}

    def _ask_scope(self) -> str | None:
        box = QMessageBox(self)
        box.setWindowTitle("Recurring task")
        box.setText("Change only this occurrence, or this and all future ones?")
        box.setInformativeText("Changes to the schedule only apply to the whole series.")
        this_one = box.addButton("Just this one", QMessageBox.AcceptRole)
        future = box.addButton("This and future ones", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(future)
        box.exec()
        if box.clickedButton() is this_one:
            return JUST_THIS
        if box.clickedButton() is future:
            return THIS_AND_FUTURE
        return None

    def _save(self):
        title = " ".join(self.title_input.text().split())
        if not title:
            QMessageBox.warning(self, "Task name needed", "Please enter a task name.")
            self.title_input.setFocus()
            return
        same_name = self.db.find_open_task(title)
        if same_name is not None and same_name != self.task_id \
                and self.status_input.currentData() != "done" \
                and not (self.series_mode and self.db.get_task(same_name)["recurrence_id"]
                         == self.recurrence_id):
            QMessageBox.warning(self, "Task already exists",
                                f'There is already an open task called "{title}".')
            self.title_input.setFocus()
            return

        repeating = self._frequency() is not None
        schedule = self._schedule() if repeating else None
        if repeating and (schedule is None or schedule.count(self.db.get_working_days()) == 0):
            QMessageBox.warning(self, "Repeat", "Please fix the repeat settings: a recurring "
                                "task needs a valid start and 'until' date, and at least one "
                                "matching day.")
            return

        common = self._common_values()
        try:
            if self.series_mode:
                self.db.update_recurrence(self.recurrence_id, **common,
                                          **self._schedule_values(schedule))
            elif self.task_id is None and repeating:
                self.recurrence_id = self.db.create_recurrence(**common,
                                                               **self._schedule_values(schedule))
                self.db.set_last_project_id(common["project_id"])
            elif self.task_id is None:
                self.task_id = self.db.create_task(**self.values())
                self.db.set_last_project_id(common["project_id"])
            elif self.series:                     # an occurrence
                scope = self._ask_scope()
                if scope is None:
                    return
                task_values = {**common, "status": self.status_input.currentData()}
                if self.task["checklist"] != common["checklist"]:
                    self.db.set_checklist_done(self.task_id, [])
                self.db.update_task(self.task_id, **task_values)
                if scope == THIS_AND_FUTURE:
                    self.db.update_recurrence(self.recurrence_id, **common,
                                              **self._schedule_values(schedule))
            else:
                if self.task["checklist"] != common["checklist"]:
                    self.db.set_checklist_done(self.task_id, [])
                self.db.update_task(self.task_id, **self.values())
        except ValueError as error:
            QMessageBox.warning(self, "Can't save", str(error))
            return
        if self.recurrence_id:
            self.db.generate_occurrences()        # today's occurrence appears right away
        self.accept()
