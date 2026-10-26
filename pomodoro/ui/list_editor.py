"""An editable list (name + colour) used for categories and task types in Settings.

Add, rename, recolour, delete and reorder. Changes are saved straight away.
"""

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QColorDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPushButton, QVBoxLayout,
                               QWidget)

from pomodoro.models import CATEGORY_PALETTE
from pomodoro.ui.project_picker import color_dot

PALETTE_NAMES = ["Blue", "Orange", "Aqua", "Yellow", "Pink", "Green", "Violet", "Red"]


@dataclass
class ListOps:
    """How the editor talks to the database for one kind of list."""
    noun: str                                   # "category" / "type"
    load: Callable[[], list[dict]]              # rows with id/key, name, color, tasks
    id_key: str                                 # "id" or "key"
    add: Callable[[str], object]
    rename: Callable[[object, str], None]
    set_color: Callable[[object, str], None]
    delete: Callable[[object, object], None]    # (item id, id its tasks move to)
    move: Callable[[object, int], None]
    none_choice: str | None = None              # e.g. "No category"; None = must pick one


class ListEditor(QWidget):
    def __init__(self, ops: ListOps, parent=None):
        super().__init__(parent)
        self.ops = ops

        self.list = QListWidget()
        self.list.setMinimumHeight(170)
        self.list.itemDoubleClicked.connect(lambda _: self._rename())

        add = QPushButton(f"+ Add {ops.noun}")
        self.rename_button = QPushButton("Rename…")
        self.color_button = QPushButton("Colour")
        self.delete_button = QPushButton("Delete…")
        self.up_button = QPushButton("↑")
        self.down_button = QPushButton("↓")
        for button in (self.up_button, self.down_button):
            button.setFixedWidth(36)
        self.up_button.setToolTip("Move up")
        self.down_button.setToolTip("Move down")

        add.clicked.connect(self._add)
        self.rename_button.clicked.connect(self._rename)
        self.color_button.clicked.connect(self._pick_color)
        self.delete_button.clicked.connect(self._delete)
        self.up_button.clicked.connect(lambda: self._move(-1))
        self.down_button.clicked.connect(lambda: self._move(1))
        self.list.currentRowChanged.connect(lambda _: self._update_buttons())

        buttons = QVBoxLayout()
        for button in (add, self.rename_button, self.color_button, self.delete_button):
            buttons.addWidget(button)
        arrows = QHBoxLayout()
        arrows.addWidget(self.up_button)
        arrows.addWidget(self.down_button)
        arrows.addStretch()
        buttons.addLayout(arrows)
        buttons.addStretch()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        self.reload()

    # ---------- list ----------

    def reload(self, select=None):
        if select is None and self.list.currentItem():
            select = self.list.currentItem().data(Qt.UserRole)
        self.list.clear()
        for row in self.ops.load():
            used = row["tasks"]
            item = QListWidgetItem(color_dot(row["color"]),
                                   f"{row['name']}    ·  {used} task{'s' if used != 1 else ''}")
            item.setData(Qt.UserRole, row[self.ops.id_key])
            item.setData(Qt.UserRole + 1, row["name"])
            item.setData(Qt.UserRole + 2, used)
            self.list.addItem(item)
            if row[self.ops.id_key] == select:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self._update_buttons()

    def _selected(self):
        item = self.list.currentItem()
        return (item.data(Qt.UserRole), item.data(Qt.UserRole + 1),
                item.data(Qt.UserRole + 2)) if item else (None, None, 0)

    def _update_buttons(self):
        has = self.list.currentItem() is not None
        row = self.list.currentRow()
        for button in (self.rename_button, self.color_button, self.delete_button):
            button.setEnabled(has)
        self.up_button.setEnabled(has and row > 0)
        self.down_button.setEnabled(has and row < self.list.count() - 1)

    def _try(self, action) -> bool:
        try:
            action()
            return True
        except ValueError as error:
            QMessageBox.warning(self, self.ops.noun.capitalize(), str(error))
            return False

    # ---------- actions ----------

    def _add(self):
        name, ok = QInputDialog.getText(self, f"New {self.ops.noun}", "Name:")
        if ok and name.strip():
            result = {}
            if self._try(lambda: result.setdefault("id", self.ops.add(name))):
                self.reload(select=result["id"])

    def _rename(self):
        item_id, name, _ = self._selected()
        if item_id is None:
            return
        new, ok = QInputDialog.getText(self, f"Rename {self.ops.noun}", "Name:", text=name)
        if ok and new.strip() and new.strip() != name:
            if self._try(lambda: self.ops.rename(item_id, new)):
                self.reload(select=item_id)

    def _pick_color(self):
        item_id, _, _ = self._selected()
        if item_id is None:
            return
        menu = QMenu(self)
        for color, label in zip(CATEGORY_PALETTE, PALETTE_NAMES):
            action = QAction(color_dot(color), label, menu)
            action.triggered.connect(lambda _=False, c=color: self._set_color(item_id, c))
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction("Custom colour…", lambda: self._custom_color(item_id))
        menu.exec(self.color_button.mapToGlobal(self.color_button.rect().bottomLeft()))

    def _custom_color(self, item_id):
        color = QColorDialog.getColor(parent=self, title="Pick a colour")
        if color.isValid():
            self._set_color(item_id, color.name())

    def _set_color(self, item_id, color: str):
        self.ops.set_color(item_id, color)
        self.reload(select=item_id)

    def _delete(self):
        item_id, name, used = self._selected()
        if item_id is None:
            return
        others = [(row[self.ops.id_key], row["name"]) for row in self.ops.load()
                  if row[self.ops.id_key] != item_id]
        if self.ops.none_choice is None and not others:
            QMessageBox.warning(self, f"Delete {self.ops.noun}",
                                f"You need at least one {self.ops.noun}.")
            return
        move_to = None
        if used:
            choices = ([self.ops.none_choice] if self.ops.none_choice else []) + \
                      [label for _, label in others]
            picked, ok = QInputDialog.getItem(
                self, f"Delete {self.ops.noun}",
                f'"{name}" is used by {used} task{"s" if used != 1 else ""}.\n'
                "Move them to:", choices, 0, False)
            if not ok:
                return
            move_to = dict((label, value) for value, label in others).get(picked)
        else:
            if self.ops.none_choice is None:
                move_to = others[0][0]          # nothing to move, but a target is required
            answer = QMessageBox.question(self, f"Delete {self.ops.noun}", f'Delete "{name}"?')
            if answer != QMessageBox.Yes:
                return
        if self._try(lambda: self.ops.delete(item_id, move_to)):
            self.reload()

    def _move(self, step: int):
        item_id, _, _ = self._selected()
        if item_id is not None:
            self.ops.move(item_id, step)
            self.reload(select=item_id)


def category_ops(db) -> ListOps:
    return ListOps("category", db.list_categories, "id", db.create_category,
                   db.rename_category, db.set_category_color, db.delete_category,
                   db.move_category, none_choice="No category")


def type_ops(db) -> ListOps:
    return ListOps("type", db.list_types, "key", db.create_type, db.rename_type,
                   db.set_type_color, db.delete_type, db.move_type)


def editor_page(db) -> QWidget:
    """The 'Categories & Types' page for the Settings window."""
    page = QWidget()
    layout = QVBoxLayout(page)
    note = QLabel("Changes here are saved straight away. Renaming updates every task that "
                  "uses the name. The first type is the default for new tasks.",
                  objectName="cardNote", wordWrap=True)
    layout.addWidget(note)
    layout.addWidget(QLabel("<b>Categories</b>  <span style='color:#8B8D98'>- the kind of "
                            "work (Development, Meetings…)</span>"))
    page.category_editor = ListEditor(category_ops(db))
    layout.addWidget(page.category_editor)
    layout.addWidget(QLabel("<b>Types</b>  <span style='color:#8B8D98'>- a broader split "
                            "(Coding, Non-coding, Research…)</span>"))
    page.type_editor = ListEditor(type_ops(db))
    layout.addWidget(page.type_editor)
    return page
