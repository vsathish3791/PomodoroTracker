"""Small containers that group related views under one main tab."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)


class SwitchPanel(QWidget):
    """Several views of the same thing with a small switch at the top right
    (e.g. To-Do: ☰ List | ▦ Table)."""
    changed = Signal(int)

    def __init__(self, views: list[tuple[str, QWidget]], parent=None):
        super().__init__(parent)
        self.stack = QStackedWidget()
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        switch = QHBoxLayout()
        switch.setContentsMargins(0, 6, 12, 0)
        switch.setSpacing(0)
        switch.addStretch()
        for index, (label, widget) in enumerate(views):
            self.stack.addWidget(widget)
            button = QPushButton(label, objectName="segment", checkable=True)
            button.setCursor(Qt.PointingHandCursor)
            button.setChecked(index == 0)
            self.group.addButton(button, index)
            switch.addWidget(button)
        self.group.idClicked.connect(self._switch)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(switch)
        layout.addWidget(self.stack, 1)

    def _switch(self, index: int):
        self.stack.setCurrentIndex(index)
        self.changed.emit(index)

    def current(self) -> QWidget:
        return self.stack.currentWidget()
