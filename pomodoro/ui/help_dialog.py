"""The in-app guide (? Help or F1): pomodoro/USER_GUIDE.md shown as formatted text."""

from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from pomodoro import __version__

GUIDE = Path(__file__).resolve().parent.parent / "USER_GUIDE.md"


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Pomodoro Tracker {__version__} – Help")
        view = QTextBrowser(objectName="helpView")
        view.setOpenExternalLinks(True)
        try:
            text = GUIDE.read_text(encoding="utf-8")
        except OSError:
            text = "The guide file (USER_GUIDE.md) is missing."
        view.setMarkdown(text + f"\n\n---\n*Version {__version__}*")
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(view)
        layout.addWidget(buttons)
        screen = self.screen().availableGeometry() if self.screen() else None
        height = min(720, screen.height() - 80) if screen else 640
        self.resize(760, height)
