"""A slim bar at the bottom of the window for one-click questions.

Used for "Done: X – how did it feel?" and "Practice – how hard was it?". It never
blocks: answer with one click, press Skip, or ignore it and it goes away.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton


class PromptBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent, objectName="promptBar")
        self.setStyleSheet(
            "QFrame#promptBar { background: #EEF4FF; border-top: 1px solid #C9DAF8; }"
            "QFrame#promptBar QLabel { color: #1C2024; font-size: 13px; background: transparent; }"
            "QFrame#promptBar QPushButton { font-size: 12px; padding: 4px 10px; border-radius: 12px;"
            " background: white; border: 1px solid #B8CCF0; color: #1C2024; }"
            "QFrame#promptBar QPushButton:hover { background: #DCE8FF; }")
        self.layout_ = QHBoxLayout(self)
        self.layout_.setContentsMargins(16, 6, 16, 6)
        self.label = QLabel()
        self.timer = QTimer(self, singleShot=True, timeout=self.hide)
        self.hide()

    def ask(self, text: str, options: list[tuple[str, object]], on_answer,
            seconds: int = 90):
        """Show a question with one button per option (plus Skip)."""
        while self.layout_.count():
            item = self.layout_.takeAt(0)
            if item.widget() and item.widget() is not self.label:
                item.widget().hide()            # hide now; delete after any click finishes
                item.widget().deleteLater()
        self.label.setText(text)
        self.layout_.addWidget(self.label, 1)
        for label, value in [*options, ("Skip", None)]:
            button = QPushButton(label)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, v=value: self._answer(on_answer, v))
            self.layout_.addWidget(button)
        self.show()
        self.timer.start(seconds * 1000)

    def _answer(self, on_answer, value):
        self.hide()
        self.timer.stop()
        if value is not None:
            on_answer(value)
