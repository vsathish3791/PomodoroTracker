"""Notion pieces of the UI: the Settings -> Notion page and a helper that talks to Notion
in the background so the window never freezes."""

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QPushButton, QWidget

from pomodoro.database import Database
from pomodoro.notion import NotionClient, NotionError, parse_id
from pomodoro.secret_store import protect, unprotect

SETUP_HELP = (
    "<b>Connect once (about 3 minutes):</b><ol>"
    "<li>Open <a href='https://www.notion.so/profile/integrations'>notion.so/profile/"
    "integrations</a> → <b>New integration</b> (Internal), name it “Pomodoro Tracker”.</li>"
    "<li>Copy its <b>Internal Integration Secret</b> and paste it below.</li>"
    "<li>In Notion, open your Journal database and your weekly-review page → <b>•••</b> → "
    "<b>Connections</b> → add “Pomodoro Tracker”.</li>"
    "<li>Paste their links below and press <b>Test</b>.</li></ol>"
    "The secret is stored encrypted for your Windows account only. The app only sends "
    "numbers – your reflection stays yours, in Notion.")


def notion_client(db: Database) -> NotionClient:
    return NotionClient(unprotect(db.get_setting("notion_token")))


def is_connected(db: Database) -> bool:
    return bool(db.get_setting("notion_token"))


class _Relay(QObject):
    finished = Signal(object, object)          # result, error message


def run_in_background(parent: QObject, work, on_done):
    """Run `work()` off the UI thread; call `on_done(result, error)` back on it.

    `error` is a message string when `work` raised NotionError (or anything else)."""
    relay = _Relay(parent)

    def done(result, error):
        relay.deleteLater()
        on_done(result, error)

    relay.finished.connect(done, Qt.QueuedConnection)

    def target():
        try:
            relay.finished.emit(work(), None)
        except NotionError as error:
            relay.finished.emit(None, str(error))
        except Exception as error:                 # never let a worker crash the app
            relay.finished.emit(None, f"Unexpected problem: {error}")

    threading.Thread(target=target, daemon=True).start()


class NotionPage(QWidget):
    """Settings -> Notion."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        help_label = QLabel(SETUP_HELP, objectName="cardNote", wordWrap=True)
        help_label.setOpenExternalLinks(True)
        help_label.setTextFormat(Qt.RichText)
        self.token = QLineEdit(echoMode=QLineEdit.Password,
                               placeholderText="ntn_… or secret_…")
        self.journal = QLineEdit(placeholderText="Link to your Journal database")
        self.weekly = QLineEdit(placeholderText="Link to the page that holds weekly reviews")
        self.test = QPushButton("Test")
        self.test.clicked.connect(self._test)
        self.result = QLabel(objectName="cardNote", wordWrap=True)

        form = QFormLayout(self)
        form.addRow(help_label)
        form.addRow("Integration secret", self.token)
        form.addRow("Journal database", self.journal)
        form.addRow("Weekly reviews page", self.weekly)
        form.addRow(self.test, self.result)

        self.token.setText(unprotect(db.get_setting("notion_token")))
        self.journal.setText(db.get_setting("notion_journal_url"))
        self.weekly.setText(db.get_setting("notion_weekly_url"))

    def values_ok(self) -> str:
        """'' when the links are usable (or empty), else what's wrong."""
        for name, box in (("Journal database", self.journal), ("Weekly reviews page", self.weekly)):
            if box.text().strip():
                try:
                    parse_id(box.text())
                except NotionError:
                    return f"{name}: that doesn't look like a Notion link."
        return ""

    def save(self):
        self.db.set_setting("notion_token", protect(self.token.text().strip()))
        self.db.set_setting("notion_journal_url", self.journal.text().strip())
        self.db.set_setting("notion_weekly_url", self.weekly.text().strip())

    def _test(self):
        problem = self.values_ok()
        if problem:
            self.result.setText(problem)
            return
        token, journal, weekly = (self.token.text().strip(), self.journal.text().strip(),
                                  self.weekly.text().strip())

        def work():
            client = NotionClient(token)
            lines = [f"Secret ✓ {client.whoami()}"]      # a bad secret stops here
            checks = []
            if journal:
                checks.append(("Journal", lambda: client.journal_fields(parse_id(journal))
                               and client.database_title(parse_id(journal))))
            if weekly:
                checks.append(("Weekly page", lambda: client.page_title(parse_id(weekly))))
            for name, check in checks:
                try:
                    lines.append(f"{name} ✓ “{check()}”")
                except NotionError as error:
                    lines.append(f"{name} ✗ {error}")
            if not checks:
                lines.append("Now add the links.")
            return "\n".join(lines)

        def done(text, error):
            self.test.setEnabled(True)
            self.result.setText(text or f"✗ {error}")

        self.test.setEnabled(False)
        self.result.setText("Checking…")

        run_in_background(self, work, done)
