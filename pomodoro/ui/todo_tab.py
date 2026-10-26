"""The To-Do tab: a list view in the style of Focus To-Do.

Left: smart lists (Today, Tomorrow, This Week, Planned, Completed, Tasks) and your
projects, each with its task count and estimated time. Right: the chosen list with
its totals, a quick-add box, and the tasks grouped by project.
"""

from datetime import date, timedelta

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
                               QPushButton, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout,
                               QWidget)

from pomodoro import lists
from pomodoro.database import Database
from pomodoro.models import CATEGORY_PALETTE, PRIORITIES, due_label, is_overdue
from pomodoro.ui.task_dialog import TaskDialog

RED = "#E5484D"
RED_LIGHT = "#F4A9AA"
MUTED = "#8B8D98"

SMART_ICONS = {   # symbol and tint for each smart list
    "today": ("☀", "#30A46C"), "tomorrow": ("◒", "#F76B15"), "week": ("▦", "#6250d6"),
    "planned": ("▤", "#0090FF"), "completed": ("✓", "#8B8D98"), "all": ("☰", "#0090FF"),
}


# ---------- small building blocks ----------

class CheckCircle(QAbstractButton):
    """Round tick box: empty circle for open tasks, filled with a tick when done."""

    def __init__(self, done: bool):
        super().__init__()
        self.done = done
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Reopen" if done else "Mark done")

    def sizeHint(self) -> QSize:
        return QSize(22, 22)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        hover = self.underMouse()
        if self.done:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#B9BBC6"))
            p.drawEllipse(2, 2, 18, 18)
            p.setPen(QPen(QColor("white"), 2))
            p.drawLine(7, 11, 10, 14)
            p.drawLine(10, 14, 15, 8)
        else:
            p.setPen(QPen(QColor("#30A46C" if hover else "#B9BBC6"), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(2, 2, 18, 18)
            if hover:
                p.setPen(QPen(QColor("#30A46C"), 2))
                p.drawLine(7, 11, 10, 14)
                p.drawLine(10, 14, 15, 8)

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


def tomato_html(done: int, estimate: int | None) -> str:
    """Dots for pomodoros: filled = done, hollow = still estimated. Long runs become numbers."""
    estimate = estimate or 0
    total = max(done, estimate)
    if total == 0:
        return ""
    if total > 8:
        text = f"{done}/{estimate}" if estimate else str(done)
        return f'<span style="color:{RED}">●</span> <span style="color:{MUTED}">{text}</span>'
    filled = f'<span style="color:{RED}">{"●" * done}</span>'
    hollow = f'<span style="color:{RED_LIGHT}">{"○" * (total - done)}</span>'
    return filled + hollow


class TaskRow(QFrame):
    toggled = Signal(int)
    start = Signal(int)
    edit = Signal(int)
    menu_requested = Signal(int, object)   # task id, global position

    def __init__(self, task: dict, show_project: bool, today: date):
        super().__init__(objectName="todoRow")
        self.task_id = task["id"]
        done = task["status"] == "done"

        check = CheckCircle(done)
        check.clicked.connect(lambda: self.toggled.emit(self.task_id))

        play = QToolButton(objectName="rowPlay")
        play.setText("▶")
        play.setToolTip("Start a pomodoro")
        play.setCursor(Qt.PointingHandCursor)
        play.setFixedSize(24, 24)
        play.setEnabled(not done)
        play.clicked.connect(lambda: self.start.emit(self.task_id))

        title = QLabel(task["title"], objectName="todoTitle")
        title.setTextInteractionFlags(Qt.NoTextInteraction)
        if done:
            font = title.font()
            font.setStrikeOut(True)
            title.setFont(font)
            title.setStyleSheet(f"color: {MUTED};")

        meta_parts = []
        tomatoes = tomato_html(task["pomodoros"], task["estimate_pomodoros"])
        if tomatoes:
            meta_parts.append(tomatoes)
        if task["priority"] <= 2 and not done:
            color = "#CE2C31" if task["priority"] == 1 else "#DC6B19"
            meta_parts.append(f'<span style="color:{color}">⚑ {PRIORITIES[task["priority"]]}</span>')
        if show_project and task.get("project"):
            meta_parts.append(f'<span style="color:{task["project_color"]}">●</span> '
                              f'<span style="color:{MUTED}">{task["project"]}</span>')
        if task.get("category"):
            meta_parts.append(f'<span style="color:{MUTED}">{task["category"]}</span>')
        if task.get("notes"):
            meta_parts.append(f'<span style="color:{MUTED}">✎</span>')
        meta = QLabel("&nbsp;&nbsp;".join(meta_parts), objectName="todoMeta")
        meta.setTextFormat(Qt.RichText)

        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(title)
        if meta_parts:
            text.addWidget(meta)

        due_text = due_label(task["due_date"], today) if task["due_date"] else ""
        due = QLabel(due_text, objectName="todoDue")
        if done and task.get("completed_at"):
            due.setText("Done " + date.fromisoformat(task["completed_at"][:10]).strftime("%d %b"))
        elif is_overdue(task["due_date"], today) or due_text == "Today":
            due.setStyleSheet(f"color: {RED};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 16, 10)
        layout.setSpacing(10)
        layout.addWidget(check)
        layout.addWidget(play)
        layout.addLayout(text, 1)
        layout.addWidget(due)

        self.setToolTip(task["notes"] or "")
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.menu_requested.emit(self.task_id, self.mapToGlobal(pos)))

    def mouseDoubleClickEvent(self, _event):
        self.edit.emit(self.task_id)


class EstimatePicker(QWidget):
    """Five tomatoes for the quick-add estimate; click to set, click again to clear."""
    MAX = 5

    def __init__(self):
        super().__init__()
        self.value = 0
        self.buttons = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for n in range(1, self.MAX + 1):
            button = QToolButton(objectName="estimateDot")
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(f"Estimate {n} pomodoro{'s' if n > 1 else ''}")
            button.clicked.connect(lambda _=False, n=n: self.set_value(0 if self.value == n else n))
            layout.addWidget(button)
            self.buttons.append(button)
        self.set_value(0)

    def set_value(self, value: int):
        self.value = value
        for n, button in enumerate(self.buttons, start=1):
            button.setText("●" if n <= value else "○")
            button.setStyleSheet(f"color: {RED if n <= value else '#C9CAD1'};")


class StatBlock(QWidget):
    def __init__(self, caption: str):
        super().__init__()
        self.value = QLabel(objectName="todoStatValue", alignment=Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.addWidget(self.value)
        layout.addWidget(QLabel(caption, objectName="todoStatCaption", alignment=Qt.AlignCenter))

    def set_minutes(self, minutes: int):
        hours, mins = divmod(round(minutes), 60)
        small = '<span style="font-size:13px">{}</span>'
        if hours:
            self.value.setText(f"{hours}{small.format('h')} {mins}{small.format('m')}")
        else:
            self.value.setText(f"{mins}{small.format('m')}")

    def set_number(self, number: int):
        self.value.setText(str(number))


# ---------- the tab ----------

class TodoTab(QWidget):
    start_requested = Signal(int)
    tasks_changed = Signal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.current = "today"
        self.sort = "score"
        self.show_done = True
        # Set by the app: {task id: position in the Focus Score ranking}.
        self.score_order = lambda: {}

        # ----- sidebar -----
        self.search_input = QLineEdit(placeholderText="🔍  Search", clearButtonEnabled=True,
                                      objectName="todoSearch")
        self.nav = QListWidget(objectName="todoNav")
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setContextMenuPolicy(Qt.CustomContextMenu)
        new_project = QPushButton("+  New project", objectName="todoNewProject")
        new_project.setCursor(Qt.PointingHandCursor)

        sidebar = QFrame(objectName="todoSidebar")
        sidebar.setFixedWidth(250)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 14, 12, 12)
        side.setSpacing(8)
        side.addWidget(self.search_input)
        side.addWidget(self.nav, 1)
        side.addWidget(new_project)

        # ----- main panel -----
        self.title_label = QLabel(objectName="todoHeading")
        self.sort_button = QToolButton(objectName="todoSort")
        self.sort_button.setText("⇅")
        self.sort_button.setToolTip("Sort tasks")
        self.sort_button.setPopupMode(QToolButton.InstantPopup)
        self.sort_button.setCursor(Qt.PointingHandCursor)
        self._build_sort_menu()
        heading = QHBoxLayout()
        heading.addWidget(self.title_label)
        heading.addStretch()
        heading.addWidget(self.sort_button)

        self.stat_estimated = StatBlock("Estimated Time")
        self.stat_to_complete = StatBlock("Tasks to be Completed")
        self.stat_elapsed = StatBlock("Elapsed Time")
        self.stat_completed = StatBlock("Completed Tasks")
        stats = QFrame(objectName="todoCard")
        stats_layout = QHBoxLayout(stats)
        stats_layout.setContentsMargins(10, 14, 10, 12)
        for block in (self.stat_estimated, self.stat_to_complete, self.stat_elapsed,
                      self.stat_completed):
            stats_layout.addWidget(block, 1)

        self.add_input = QLineEdit(objectName="todoAdd")
        self.estimate_picker = EstimatePicker()
        add_card = QFrame(objectName="todoCard")
        add_layout = QHBoxLayout(add_card)
        add_layout.setContentsMargins(16, 6, 14, 6)
        plus = QLabel("+", objectName="todoPlus")
        add_layout.addWidget(plus)
        add_layout.addWidget(self.add_input, 1)
        add_layout.addWidget(self.estimate_picker)

        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(6)
        list_widget = QWidget(objectName="todoList")
        list_container = QVBoxLayout(list_widget)
        list_container.setContentsMargins(0, 0, 0, 0)
        list_container.addLayout(self.list_layout)
        list_container.addStretch()

        main = QWidget(objectName="todoMain")
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(24, 16, 24, 16)
        main_layout.setSpacing(12)
        main_layout.addLayout(heading)
        main_layout.addWidget(stats)
        main_layout.addWidget(add_card)
        main_layout.addWidget(list_widget)
        main_layout.addStretch()
        scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        scroll.setWidget(main)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(scroll, 1)

        self.nav.currentItemChanged.connect(self._on_nav_changed)
        self.nav.customContextMenuRequested.connect(self._nav_menu)
        self.search_input.textChanged.connect(lambda _: self.refresh_list())
        self.add_input.returnPressed.connect(self._quick_add)
        new_project.clicked.connect(self.new_project)
        self.refresh()

    # ---------- sidebar ----------

    def _nav_row(self, symbol: str, tint: str, name: str, minutes: int | None, count: int,
                 dot: bool = False) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 0, 8, 0)
        icon = QLabel("●" if dot else symbol, objectName="navIcon")
        icon.setFixedWidth(22)
        icon.setStyleSheet(f"color: {tint}; font-size: {'12' if dot else '16'}px;")
        label = QLabel(name, objectName="navName")
        label.setToolTip(name)
        label.setMinimumWidth(40)
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(icon)
        layout.addWidget(label, 1)
        if minutes is not None:
            layout.addWidget(QLabel(lists.format_minutes(minutes), objectName="navMeta"))
        count_label = QLabel(str(count), objectName="navMeta")
        count_label.setFixedWidth(28)
        count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(count_label)
        return row

    def refresh_nav(self):
        focus = self.db.get_int("focus_minutes")
        counts = lists.sidebar_counts(self.db, focus)
        self.nav.blockSignals(True)
        self.nav.clear()
        selected = None

        def add(key: str | None, widget: QWidget, selectable=True, height=40):
            nonlocal selected
            item = QListWidgetItem()
            item.setData(Qt.UserRole, key)
            item.setSizeHint(QSize(0, height))
            if not selectable:
                item.setFlags(Qt.NoItemFlags)
            self.nav.addItem(item)
            self.nav.setItemWidget(item, widget)
            if key == self.current:
                selected = item

        for key, name in lists.SMART_LISTS:
            symbol, tint = SMART_ICONS[key]
            count, minutes = counts[key]
            add(key, self._nav_row(symbol, tint, name, None if key == "completed" else minutes,
                                   count))
        header = QLabel("PROJECTS", objectName="navHeader")
        header.setContentsMargins(10, 8, 0, 0)
        add(None, header, selectable=False, height=36)
        projects = self.db.list_projects()
        if not projects:
            hint = QLabel("No projects yet", objectName="navMeta")
            hint.setContentsMargins(12, 0, 0, 0)
            add(None, hint, selectable=False, height=28)
        for project in projects:
            key = f"project:{project['id']}"
            count, minutes = counts[key]
            add(key, self._nav_row("", project["color"], project["name"], minutes, count,
                                   dot=True))

        if selected is None:            # e.g. the shown project was deleted
            self.current = "today"
            selected = self.nav.item(0)
        self.nav.setCurrentItem(selected)
        self.nav.blockSignals(False)

    def _on_nav_changed(self, item, _previous):
        if item is not None and item.data(Qt.UserRole):
            self.current = item.data(Qt.UserRole)
            self.search_input.clear()
            self.refresh_list()

    def _nav_menu(self, pos):
        item = self.nav.itemAt(pos)
        key = item.data(Qt.UserRole) if item else None
        if not key or not key.startswith("project:"):
            return
        project_id = int(key.split(":")[1])
        menu = QMenu(self)
        menu.addAction("Rename…", lambda: self.rename_project(project_id))
        colors = menu.addMenu("Colour")
        for color in CATEGORY_PALETTE:
            action = QAction("●  " + color, colors)
            action.triggered.connect(lambda _=False, c=color: self._recolor(project_id, c))
            colors.addAction(action)
        menu.addSeparator()
        menu.addAction("Delete project…", lambda: self.delete_project(project_id))
        menu.exec(self.nav.mapToGlobal(pos))

    # ---------- projects ----------

    def new_project(self):
        name, ok = QInputDialog.getText(self, "New project", "Project name:")
        if not ok or not name.strip():
            return
        try:
            project_id = self.db.create_project(name)
        except ValueError as error:
            QMessageBox.warning(self, "New project", str(error))
            return
        self.current = f"project:{project_id}"
        self._changed()

    def rename_project(self, project_id: int):
        project = self.db.get_project(project_id)
        name, ok = QInputDialog.getText(self, "Rename project", "Project name:",
                                        text=project["name"])
        if not ok:
            return
        try:
            self.db.rename_project(project_id, name)
        except ValueError as error:
            QMessageBox.warning(self, "Rename project", str(error))
            return
        self._changed()

    def _recolor(self, project_id: int, color: str):
        self.db.set_project_color(project_id, color)
        self._changed()

    def delete_project(self, project_id: int):
        project = self.db.get_project(project_id)
        count = len(self.db.list_tasks("all", project_id=project_id))
        answer = QMessageBox.question(
            self, "Delete project",
            f'Delete the project "{project["name"]}"?\n\n'
            f"Its {count} task(s) are kept; they just won't belong to a project.")
        if answer == QMessageBox.Yes:
            self.db.delete_project(project_id)
            self._changed()

    # ---------- the list ----------

    def _view_name(self) -> str:
        if self.current.startswith("project:"):
            project = self.db.get_project(int(self.current.split(":")[1]))
            return project["name"] if project else "Project"
        return lists.SMART_NAMES[self.current]

    def refresh(self):
        self.refresh_nav()
        self.refresh_list()

    def refresh_list(self):
        today = date.today()
        search = self.search_input.text().strip().lower()
        if search:
            title = f'Search: "{self.search_input.text().strip()}"'
            everything = self.db.list_tasks("all", search=search)
            content = lists.ListContent([t for t in everything if t["status"] != "done"],
                                        [t for t in everything if t["status"] == "done"])
        else:
            title = self._view_name()
            content = lists.list_content(self.db, self.current, today)
        self.title_label.setText(title)

        stats = lists.list_stats(self.db, content, self.db.get_int("focus_minutes"), today)
        self.stat_estimated.set_minutes(stats.estimated_minutes)
        self.stat_to_complete.set_number(stats.to_complete)
        self.stat_elapsed.set_minutes(stats.elapsed_minutes)
        self.stat_completed.set_number(stats.completed)

        can_add = self.current != "completed" and not search
        self.add_input.setEnabled(can_add)
        self.estimate_picker.setEnabled(can_add)
        self.add_input.setPlaceholderText(
            f'Add a task to "{self._view_name()}", press Enter to save' if can_add
            else "Pick a list to add tasks")

        # Clear old rows
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().hide()          # hide now; delete once any click on it has finished
                item.widget().deleteLater()

        open_tasks = lists.sort_tasks(content.open_tasks, self.sort, self.score_order())
        in_project = self.current.startswith("project:") and not search
        focus = self.db.get_int("focus_minutes")
        if in_project or not open_tasks:
            groups = [("Tasks", None, open_tasks)] if open_tasks else []
        else:
            groups = lists.group_by_project(open_tasks, self.db.list_projects())
        for name, color, tasks in groups:
            est = sum(lists.remaining_estimate(t) for t in tasks) * focus
            self.list_layout.addWidget(self._group_header(name, color, len(tasks), est))
            for task in tasks:
                self.list_layout.addWidget(self._row(task, show_project=not in_project))

        if not open_tasks and self.current != "completed":
            empty = QLabel("No tasks here. Add one above. 🎉" if not search else "No matching tasks.",
                           objectName="todoEmpty", alignment=Qt.AlignCenter)
            self.list_layout.addWidget(empty)

        if content.done_tasks:
            label = "Completed" if self.current == "completed" else "Completed today"
            toggle = QPushButton(f"{'▾' if self.show_done else '▸'}  {label} · "
                                 f"{len(content.done_tasks)}", objectName="todoDoneToggle")
            toggle.setCursor(Qt.PointingHandCursor)
            toggle.clicked.connect(self._toggle_done)
            self.list_layout.addWidget(toggle)
            if self.show_done:
                for task in content.done_tasks:
                    self.list_layout.addWidget(self._row(task, show_project=True))

    def _group_header(self, name: str, color: str | None, count: int, minutes: int) -> QWidget:
        dot = f'<span style="color:{color}">●</span>&nbsp;' if color else ""
        label = QLabel(f"{dot}<b>{name}</b> &nbsp;·&nbsp; {lists.format_minutes(minutes)}"
                       f'&nbsp;&nbsp;<span style="color:{MUTED}">{count}</span>',
                       objectName="todoGroup")
        label.setTextFormat(Qt.RichText)
        label.setContentsMargins(4, 8, 0, 2)
        return label

    def _row(self, task: dict, show_project: bool) -> TaskRow:
        row = TaskRow(task, show_project, date.today())
        row.toggled.connect(self._toggle_task)
        row.start.connect(self.start_requested.emit)
        row.edit.connect(self.edit_task)
        row.menu_requested.connect(self._row_menu)
        return row

    def _toggle_done(self):
        self.show_done = not self.show_done
        self.refresh_list()

    def _build_sort_menu(self):
        menu = QMenu(self)
        self.sort_actions = {}
        for key, label in lists.SORTS:
            action = QAction(label, menu, checkable=True, checked=key == self.sort)
            action.triggered.connect(lambda _=False, k=key: self._set_sort(k))
            menu.addAction(action)
            self.sort_actions[key] = action
        self.sort_button.setMenu(menu)

    def _set_sort(self, key: str):
        self.sort = key
        for k, action in self.sort_actions.items():
            action.setChecked(k == key)
        self.refresh_list()

    # ---------- task actions ----------

    def _quick_add(self):
        title = self.add_input.text().strip()
        if not title or self.current == "completed":
            return
        if self.db.find_open_task(title) is not None:
            QMessageBox.warning(self, "Task already exists",
                                f'There is already an open task called "{title}".')
            return
        today = date.today()
        fields = {"estimate_pomodoros": self.estimate_picker.value or None}
        if self.current.startswith("project:"):
            fields["project_id"] = int(self.current.split(":")[1])
        elif self.current in ("today", "week"):
            fields["due_date"] = today.isoformat()
        elif self.current == "tomorrow":
            fields["due_date"] = (today + timedelta(days=1)).isoformat()
        elif self.current == "planned":
            fields["due_date"] = today.isoformat()
        self.db.create_task(title, **fields)
        self.add_input.clear()
        self.estimate_picker.set_value(0)
        self._changed()

    def _toggle_task(self, task_id: int):
        task = self.db.get_task(task_id)
        if task["status"] == "done":
            if self.db.find_open_task(task["title"]) is not None:
                QMessageBox.warning(self, "Can't reopen",
                                    f'There is already an open task called "{task["title"]}".')
                return
            self.db.set_task_status(task_id, "todo")
        else:
            self.db.set_task_status(task_id, "done")
        self._changed()

    def edit_task(self, task_id: int):
        if TaskDialog(self.db, task_id, parent=self).exec():
            self._changed()

    def _row_menu(self, task_id: int, global_pos):
        task = self.db.get_task(task_id)
        done = task["status"] == "done"
        menu = QMenu(self)
        if not done:
            menu.addAction("▶  Start pomodoro", lambda: self.start_requested.emit(task_id))
        menu.addAction("Edit…", lambda: self.edit_task(task_id))
        menu.addAction("Reopen" if done else "✓  Mark done", lambda: self._toggle_task(task_id))
        move = menu.addMenu("Move to project")
        move.addAction("No project", lambda: self._move(task_id, None))
        for project in self.db.list_projects():
            move.addAction(project["name"], lambda p=project["id"]: self._move(task_id, p))
        due = menu.addMenu("Due")
        today = date.today()
        due.addAction("Today", lambda: self._set_due(task_id, today))
        due.addAction("Tomorrow", lambda: self._set_due(task_id, today + timedelta(days=1)))
        due.addAction("Next week", lambda: self._set_due(task_id, today + timedelta(days=7)))
        due.addAction("No date", lambda: self._set_due(task_id, None))
        menu.addSeparator()
        menu.addAction("Delete…", lambda: self._delete(task_id))
        menu.exec(global_pos)

    def _move(self, task_id: int, project_id: int | None):
        self.db.update_task(task_id, project_id=project_id)
        self._changed()

    def _set_due(self, task_id: int, day: date | None):
        self.db.update_task(task_id, due_date=day.isoformat() if day else None)
        self._changed()

    def _delete(self, task_id: int):
        task = self.db.get_task(task_id)
        answer = QMessageBox.question(
            self, "Delete task", f'Delete "{task["title"]}"?\n\nIts time stays in your daily '
                                 "totals. Tip: use Mark done if you finished it.")
        if answer == QMessageBox.Yes:
            self.db.delete_task(task_id)
            self._changed()

    def _changed(self):
        self.refresh()
        self.tasks_changed.emit()
