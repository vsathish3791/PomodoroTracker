"""Dialog for adding or editing a task."""

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QSpinBox, QVBoxLayout)

from pomodoro.database import Database
from pomodoro.models import DEFAULT_PRIORITY, PRIORITIES, STATUSES, TASK_TYPES


class TaskDialog(QDialog):
    def __init__(self, db: Database, task_id: int | None = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.task_id = task_id
        task = db.get_task(task_id) if task_id else None
        self.setWindowTitle("Edit task" if task else "New task")
        self.setMinimumWidth(420)

        self.title_input = QLineEdit(placeholderText="e.g. Fix login bug")

        # Pick a category, or type a new name to create one.
        self.category_input = QComboBox(editable=True)
        self.category_input.addItem("")
        self.category_input.addItems([c["name"] for c in db.list_categories()])
        self.category_input.lineEdit().setPlaceholderText("Pick or type a new category")

        self.type_input = QComboBox()
        for key, label in TASK_TYPES.items():
            self.type_input.addItem(label, key)

        self.priority_input = QComboBox()
        for key, label in PRIORITIES.items():
            self.priority_input.addItem(label, key)

        self.has_due = QCheckBox("Due")
        self.due_input = QDateEdit(calendarPopup=True, displayFormat="ddd dd MMM yyyy")
        self.due_input.setDate(QDate.currentDate())
        self.has_due.toggled.connect(self.due_input.setEnabled)
        due_row = QHBoxLayout()
        due_row.addWidget(self.has_due)
        due_row.addWidget(self.due_input, 1)

        self.estimate_input = QSpinBox(minimum=0, maximum=200, suffix=" 🍅",
                                       specialValueText="No estimate")

        self.status_input = QComboBox()
        for key, label in STATUSES.items():
            self.status_input.addItem(label, key)

        self.notes_input = QPlainTextEdit(placeholderText="Optional notes")
        self.notes_input.setFixedHeight(70)

        form = QFormLayout()
        form.addRow("Task", self.title_input)
        form.addRow("Category", self.category_input)
        form.addRow("Type", self.type_input)
        form.addRow("Priority", self.priority_input)
        form.addRow("Due date", due_row)
        form.addRow("Estimate", self.estimate_input)
        form.addRow("Status", self.status_input)
        form.addRow("Notes", self.notes_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        if task:
            minutes = round(task["focus_minutes"])
            layout.addWidget(QLabel(f"Logged so far: 🍅 {task['pomodoros']}  ·  {minutes} min"))
        layout.addWidget(buttons)

        self._load(task)

    def _load(self, task: dict | None):
        if not task:
            self.priority_input.setCurrentIndex(self.priority_input.findData(DEFAULT_PRIORITY))
            self.has_due.setChecked(False)
            self.due_input.setEnabled(False)
            return
        self.title_input.setText(task["title"])
        self.category_input.setCurrentText(task["category"] or "")
        self.type_input.setCurrentIndex(self.type_input.findData(task["type"]))
        self.priority_input.setCurrentIndex(self.priority_input.findData(task["priority"]))
        self.has_due.setChecked(bool(task["due_date"]))
        self.due_input.setEnabled(bool(task["due_date"]))
        if task["due_date"]:
            self.due_input.setDate(QDate.fromString(task["due_date"][:10], "yyyy-MM-dd"))
        self.estimate_input.setValue(task["estimate_pomodoros"] or 0)
        self.status_input.setCurrentIndex(self.status_input.findData(task["status"]))
        self.notes_input.setPlainText(task["notes"] or "")

    def values(self) -> dict:
        due = None
        if self.has_due.isChecked():
            d = self.due_input.date()
            due = date(d.year(), d.month(), d.day()).isoformat()
        return {
            "title": self.title_input.text(),
            "category_id": self.db.get_or_create_category(self.category_input.currentText()),
            "type": self.type_input.currentData(),
            "priority": self.priority_input.currentData(),
            "due_date": due,
            "estimate_pomodoros": self.estimate_input.value() or None,
            "status": self.status_input.currentData(),
            "notes": self.notes_input.toPlainText().strip() or None,
        }

    def _save(self):
        title = " ".join(self.title_input.text().split())
        if not title:
            QMessageBox.warning(self, "Task name needed", "Please enter a task name.")
            self.title_input.setFocus()
            return
        same_name = self.db.find_open_task(title)
        if same_name is not None and same_name != self.task_id \
                and self.status_input.currentData() != "done":
            QMessageBox.warning(self, "Task already exists",
                                f'There is already an open task called "{title}".')
            self.title_input.setFocus()
            return

        values = self.values()
        if self.task_id:
            self.db.update_task(self.task_id, **values)
        else:
            self.task_id = self.db.create_task(**values)
        self.accept()
