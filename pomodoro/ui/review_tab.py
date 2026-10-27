"""Weekly review: Falconi's three-generation report (Planned -> Done & results -> Problems
& next actions). Copy it into your Notion weekly review, or save it as a file."""

from datetime import date, timedelta

from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QTextBrowser, QVBoxLayout, QWidget)

from pomodoro import planning
from pomodoro.database import Database
from pomodoro.ui.clipboard import copy_text


class ReviewTab(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.week_input = QComboBox()
        self.week_input.currentIndexChanged.connect(lambda _: self.refresh_report())
        copy = QPushButton("Copy for Notion")
        copy.setToolTip("Copies the report as Markdown - paste it into a Notion page.")
        copy.clicked.connect(self._copy)
        save = QPushButton("Save as…")
        save.clicked.connect(self._save)
        self.status = QLabel(objectName="cardNote")

        top = QHBoxLayout()
        top.addWidget(QLabel("Week of"))
        top.addWidget(self.week_input)
        top.addStretch()
        top.addWidget(self.status)
        top.addWidget(copy)
        top.addWidget(save)

        self.view = QTextBrowser(objectName="reviewView")
        self.view.setOpenExternalLinks(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.addLayout(top)
        layout.addWidget(QLabel("Three generations: what was planned · what was done and its "
                                "results · problems and next actions. Reflect on it in your "
                                "Notion weekly review.", objectName="cardNote", wordWrap=True))
        layout.addWidget(self.view, 1)
        self.report = None

    def refresh(self):
        monday = planning.last_monday()
        current = self.week_input.currentData()
        self.week_input.blockSignals(True)
        self.week_input.clear()
        for weeks_back in range(0, 8):
            start = monday - timedelta(weeks=weeks_back)
            label = ("This week" if weeks_back == 0 else "Last week" if weeks_back == 1
                     else f"{weeks_back} weeks ago")
            self.week_input.addItem(f"{label} – {start:%d %b}", start.isoformat())
        index = self.week_input.findData(current) if current else 0
        self.week_input.setCurrentIndex(max(index, 0))
        self.week_input.blockSignals(False)
        self.refresh_report()

    def refresh_report(self):
        monday = date.fromisoformat(self.week_input.currentData() or
                                    planning.last_monday().isoformat())
        self.report = planning.week_report(self.db, monday)
        self.view.setMarkdown(self.report.markdown())
        self.status.setText("")

    def _copy(self):
        if self.report:
            if copy_text(self, self.report.markdown()):
                self.status.setText("Copied – paste into Notion.")

    def _save(self):
        if not self.report:
            return
        name = f"weekly-review-{self.report.start.isoformat()}.md"
        path, _ = QFileDialog.getSaveFileName(self, "Save weekly review", name,
                                              "Markdown (*.md);;Text (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.report.markdown())
        except OSError as error:
            QMessageBox.warning(self, "Save failed", str(error))
            return
        self.status.setText("Saved.")
