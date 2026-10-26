"""The Tasks tab: list, filter, add, edit, complete and delete tasks."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from pomodoro.database import Database
from pomodoro.models import (PRIORITIES, PRIORITY_COLORS, STATUSES, due_label,
                             is_overdue, pomodoro_progress)
from pomodoro.ui.task_dialog import TaskDialog

COLUMNS = ["Task", "Category", "Type", "Priority", "Due", "🍅 Done / Est", "Score", "Status",
           "Project"]
PROJECT_COLUMN = 8
SCORE_COLUMN = 6
AT_RISK_COLOR = "#DC6B19"
DONE_GREY = "#8B8D98"


class TasksTab(QWidget):
    start_requested = Signal(int)   # task id: "start a pomodoro on this task"
    tasks_changed = Signal()        # something was added/edited/completed/deleted

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        # Set by the app: returns {task id: ScoredTask} for open tasks (Focus Score etc.).
        self.rank_lookup = lambda: {}

        self.new_button = QPushButton("+ New task", objectName="primary")
        self.new_button.setStyleSheet("background: #E5484D;")
        self.show_filter = QComboBox()
        self.show_filter.addItem("Open tasks", "open")
        self.show_filter.addItem("Done", "done")
        self.show_filter.addItem("All", "all")
        self.category_filter = QComboBox()
        self.project_filter = QComboBox()
        self.search_input = QLineEdit(placeholderText="Search…", clearButtonEnabled=True)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.new_button)
        toolbar.addSpacing(8)
        toolbar.addWidget(self.show_filter)
        toolbar.addWidget(self.category_filter)
        toolbar.addWidget(self.project_filter)
        toolbar.addWidget(self.search_input, 1)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.Stretch)

        self.start_button = QPushButton("▶ Start pomodoro")
        self.edit_button = QPushButton("Edit")
        self.done_button = QPushButton("✓ Mark done")
        self.delete_button = QPushButton("Delete")
        self.summary_label = QLabel(objectName="stats")

        actions = QHBoxLayout()
        actions.addWidget(self.start_button)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.done_button)
        actions.addWidget(self.delete_button)
        actions.addStretch()
        actions.addWidget(self.summary_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.addLayout(toolbar)
        layout.addWidget(self.table, 1)
        layout.addLayout(actions)

        self.new_button.clicked.connect(self.add_task)
        self.edit_button.clicked.connect(self.edit_selected)
        self.done_button.clicked.connect(self.toggle_done_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.start_button.clicked.connect(self._start_selected)
        self.table.doubleClicked.connect(lambda _: self.edit_selected())
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.show_filter.currentIndexChanged.connect(self.refresh)
        self.category_filter.currentIndexChanged.connect(self.refresh)
        self.project_filter.currentIndexChanged.connect(self.refresh)
        self.search_input.textChanged.connect(self.refresh)

        self._reload_categories()
        self.refresh()

    # ---------- loading ----------

    def _reload_categories(self):
        current = self.category_filter.currentData()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All categories", None)
        for category in self.db.list_categories():
            self.category_filter.addItem(category["name"], category["id"])
        index = self.category_filter.findData(current)
        self.category_filter.setCurrentIndex(max(index, 0))
        self.category_filter.blockSignals(False)

        current = self.project_filter.currentData()
        self.project_filter.blockSignals(True)
        self.project_filter.clear()
        self.project_filter.addItem("All projects", None)
        for project in self.db.list_projects():
            self.project_filter.addItem(project["name"], project["id"])
        index = self.project_filter.findData(current)
        self.project_filter.setCurrentIndex(max(index, 0))
        self.project_filter.blockSignals(False)

    def refresh(self):
        selected = self.selected_task_id()
        tasks = self.db.list_tasks(show=self.show_filter.currentData(),
                                   category_id=self.category_filter.currentData(),
                                   search=self.search_input.text(),
                                   project_id=self.project_filter.currentData())
        self.type_names = self.db.type_names()
        ranking = self.rank_lookup()
        if self.show_filter.currentData() == "open":
            # Same order as "Focus Next": highest Focus Score first; On Hold tasks last.
            order = {task_id: n for n, task_id in enumerate(ranking)}
            tasks.sort(key=lambda t: order.get(t["id"], len(order)))
        self.table.clearSelection()
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self._fill_row(row, task, ranking.get(task["id"]))
            if task["id"] == selected:
                self.table.selectRow(row)

        total = sum(t["pomodoros"] for t in tasks)
        self.summary_label.setText(f"{len(tasks)} tasks  ·  🍅 {total}")
        self._update_buttons()

    def _fill_row(self, row: int, task: dict, scored=None):
        done = task["status"] == "done"
        due_text = due_label(task["due_date"])
        if scored and scored.at_risk:
            due_text += "  ⚠ at risk"
        cells = [
            task["title"],
            task["category"] or "",
            self.type_names.get(task["type"], task["type"]),
            PRIORITIES[task["priority"]],
            due_text,
            pomodoro_progress(task["pomodoros"], task["estimate_pomodoros"]),
            str(scored.score) if scored else "",
            STATUSES[task["status"]],
            task["project"] or "",
        ]
        for column, text in enumerate(cells):
            item = QTableWidgetItem(text)
            if column == 0:
                item.setData(Qt.UserRole, task["id"])
                tooltip = task["title"]
                if task["notes"]:
                    tooltip += "\n\n" + task["notes"]
                item.setToolTip(tooltip)
            if done:
                item.setForeground(QColor(DONE_GREY))
                if column == 0:
                    font = item.font()
                    font.setStrikeOut(True)
                    item.setFont(font)
            elif column == 1 and task["category_color"]:
                item.setForeground(QColor(task["category_color"]))
            elif column == 3:
                item.setForeground(QColor(PRIORITY_COLORS[task["priority"]]))
                if task["priority"] <= 2:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
            elif column == 4 and is_overdue(task["due_date"]):
                item.setForeground(QColor("#CE2C31"))
            elif column == 4 and scored and scored.at_risk:
                item.setForeground(QColor(AT_RISK_COLOR))
                item.setToolTip("Not enough pomodoros left before the due date "
                                "at your daily goal.")
            elif column == PROJECT_COLUMN and task["project_color"]:
                item.setForeground(QColor(task["project_color"]))
            elif column == SCORE_COLUMN and scored:
                item.setTextAlignment(Qt.AlignCenter)
                item.setToolTip("Focus Score: " + scored.short_reason())
            elif column == 5 and task["estimate_pomodoros"] \
                    and task["pomodoros"] > task["estimate_pomodoros"]:
                item.setForeground(QColor("#DC6B19"))   # over estimate
            self.table.setItem(row, column, item)

    # ---------- selection ----------

    def selected_task_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole)

    def _update_buttons(self):
        task_id = self.selected_task_id()
        task = self.db.get_task(task_id) if task_id else None
        for button in (self.edit_button, self.done_button, self.delete_button):
            button.setEnabled(task is not None)
        is_done = bool(task) and task["status"] == "done"
        self.start_button.setEnabled(task is not None and not is_done)
        self.done_button.setText("↺ Reopen" if is_done else "✓ Mark done")

    # ---------- actions ----------

    def add_task(self):
        dialog = TaskDialog(self.db, parent=self)
        if dialog.exec():
            self._after_change()
            self._select(dialog.task_id)

    def edit_selected(self):
        task_id = self.selected_task_id()
        if task_id and TaskDialog(self.db, task_id, parent=self).exec():
            self._after_change()

    def toggle_done_selected(self):
        task_id = self.selected_task_id()
        if not task_id:
            return
        task = self.db.get_task(task_id)
        if task["status"] == "done":
            if self.db.find_open_task(task["title"]) is not None:
                QMessageBox.warning(self, "Can't reopen",
                                    f'There is already an open task called "{task["title"]}".')
                return
            self.db.set_task_status(task_id, "todo")
        else:
            self.db.set_task_status(task_id, "done")
        self._after_change()

    def delete_selected(self):
        task_id = self.selected_task_id()
        if not task_id:
            return
        task = self.db.get_task(task_id)
        answer = QMessageBox.question(
            self, "Delete task",
            f'Delete "{task["title"]}"?\n\nIts {task["pomodoros"]} pomodoro(s) stay in your '
            "daily totals but will no longer be linked to a task.\n\n"
            "Tip: use Mark done instead if you finished it.")
        if answer == QMessageBox.Yes:
            self.db.delete_task(task_id)
            self._after_change()

    def _start_selected(self):
        task_id = self.selected_task_id()
        if task_id:
            self.start_requested.emit(task_id)

    def _after_change(self):
        self._reload_categories()
        self.refresh()
        self.tasks_changed.emit()

    def _select(self, task_id: int | None):
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.UserRole) == task_id:
                self.table.selectRow(row)
                return
