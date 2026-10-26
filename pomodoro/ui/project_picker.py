"""A drop-down for choosing a task's project, with "+ New project…" at the bottom."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QComboBox, QInputDialog, QMessageBox

from pomodoro.database import Database

NEW_PROJECT = "new"


def color_dot(color: str) -> QIcon:
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(1, 1, 10, 10)
    painter.end()
    return QIcon(pixmap)


class ProjectPicker(QComboBox):
    project_created = Signal(int)
    project_chosen = Signal(object)     # project id or None, when the user picks one

    def __init__(self, db: Database, parent=None):
        super().__init__(parent, objectName="projectPicker")
        self.db = db
        self._current: int | None = None
        self.setToolTip("Project for this task")
        self.setMinimumContentsLength(12)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.activated.connect(self._on_activated)
        self.reload()

    def reload(self):
        """Refill the list (e.g. after projects were added or renamed), keeping the choice."""
        self.blockSignals(True)
        self.clear()
        self.addItem(color_dot("#C9CAD1"), "No project", None)
        for project in self.db.list_projects():
            self.addItem(color_dot(project["color"]), project["name"], project["id"])
        self.insertSeparator(self.count())
        self.addItem("+ New project…", NEW_PROJECT)
        self.blockSignals(False)
        self.set_project_id(self._current)

    def project_id(self) -> int | None:
        return self._current

    def set_project_id(self, project_id: int | None):
        index = self.findData(project_id)
        self._current = project_id if index >= 0 else None
        self.blockSignals(True)
        self.setCurrentIndex(max(index, 0))
        self.blockSignals(False)

    def _on_activated(self, index: int):
        data = self.itemData(index)
        if data == NEW_PROJECT:
            self._create_project()
            return
        self._current = data
        self.project_chosen.emit(data)

    def _create_project(self):
        name, ok = QInputDialog.getText(self, "New project", "Project name:")
        if ok and name.strip():
            try:
                project_id = self.db.create_project(name)
            except ValueError as error:
                QMessageBox.warning(self, "New project", str(error))
            else:
                self._current = project_id
                self.reload()
                # "chosen" first, so listeners save the choice before any refresh
                self.project_chosen.emit(project_id)
                self.project_created.emit(project_id)
                return
        self.set_project_id(self._current)   # cancelled: show the previous choice again
