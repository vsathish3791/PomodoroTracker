"""Copy text to the clipboard, with a fallback window if Windows refuses."""

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout,
                               QWidget)


def copy_text(parent: QWidget, text: str) -> bool:
    """Put text on the clipboard. If that didn't work (another app can lock the clipboard),
    show the text selected so it can be copied with Ctrl+C. Returns True if copied."""
    clipboard = QGuiApplication.clipboard()
    clipboard.setText(text)
    QGuiApplication.processEvents()
    if clipboard.text() == text:
        return True
    dialog = QDialog(parent)
    dialog.setWindowTitle("Copy")
    view = QPlainTextEdit(text)
    view.setReadOnly(True)
    view.selectAll()
    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.rejected.connect(dialog.reject)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("The clipboard is busy. The text is selected – press Ctrl+C."))
    layout.addWidget(view)
    layout.addWidget(buttons)
    dialog.resize(560, 320)
    view.setFocus()
    dialog.exec()
    return False
