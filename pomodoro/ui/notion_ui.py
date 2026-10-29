"""Notion pieces of the UI: the Settings -> Notion page and a helper that talks to Notion
in the background so the window never freezes.

Notion is optional. With "Use Notion" off (the default for new users) the app shows no
Notion buttons or wording at all."""

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QWidget)

from pomodoro.database import Database
from pomodoro.notion import NotionClient, NotionError, parse_id
from pomodoro.secret_store import protect, unprotect

SETUP_HELP = (
    "<b>Connect once (about 3 minutes):</b><ol>"
    "<li>Open <a href='https://www.notion.so/profile/integrations'>notion.so/profile/"
    "integrations</a> → <b>New integration</b> (Internal), name it “Pomodoro Tracker”.</li>"
    "<li>Copy its <b>Internal Integration Secret</b> and paste it below.</li>"
    "<li>In Notion, open the page that holds your Journal (and your weekly-review page) → "
    "<b>•••</b> → <b>Connections</b> → add “Pomodoro Tracker”.</li>"
    "<li>Paste your Journal link, press <b>Create…</b> for the Day Log, then <b>Test</b>."
    "</li></ol>"
    "The secret is stored encrypted for your Windows account only. The app only sends "
    "facts (task titles and numbers) – your reflection stays yours, in Notion.")


def notion_client(db: Database) -> NotionClient:
    return NotionClient(unprotect(db.get_setting("notion_token")))


def notion_enabled(db: Database) -> bool:
    """Whether to show Notion features. Until chosen in Settings: on only if Notion was
    already set up (so upgrading users keep it), off for everyone else."""
    value = db.get_setting("notion_enabled")
    if value in ("0", "1"):
        return value == "1"
    return bool(db.get_setting("notion_token") or db.get_setting("notion_journal_url")
                or db.get_setting("notion_weekly_url") or db.has_notion_links())


def is_connected(db: Database) -> bool:
    return notion_enabled(db) and bool(db.get_setting("notion_token"))


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
        self.enabled = QCheckBox("Use Notion (optional)")
        self.enabled.setToolTip("Off: the app works on its own and shows no Notion buttons.")
        help_label = QLabel(SETUP_HELP, objectName="cardNote", wordWrap=True)
        help_label.setOpenExternalLinks(True)
        help_label.setTextFormat(Qt.RichText)
        self.token = QLineEdit(echoMode=QLineEdit.Password,
                               placeholderText="ntn_… or secret_…")
        self.journal = QLineEdit(placeholderText="Link to your Journal database")
        self.day_log = QLineEdit(placeholderText="Link to your Day Log database")
        self.create = QPushButton("Create…")
        self.create.setToolTip("Create the Day Log database next to your Journal, "
                               "linked to it")
        self.create.clicked.connect(self._create_day_log)
        day_log_row = QHBoxLayout()
        day_log_row.addWidget(self.day_log, 1)
        day_log_row.addWidget(self.create)
        self.weekly = QLineEdit(placeholderText="Link to the page that holds weekly reviews")
        self.test = QPushButton("Test")
        self.test.clicked.connect(self._test)
        self.result = QLabel(objectName="cardNote", wordWrap=True)

        form = QFormLayout(self)
        form.addRow(self.enabled)
        form.addRow(QLabel("Everything in the app works without Notion. Turn this on only "
                           "if you keep a journal or weekly reviews in Notion.",
                           objectName="cardNote", wordWrap=True))
        form.addRow(help_label)
        form.addRow("Integration secret", self.token)
        form.addRow("Journal database", self.journal)
        form.addRow("Day Log database", day_log_row)
        form.addRow("Weekly reviews page", self.weekly)
        form.addRow(self.test, self.result)

        self.token.setText(unprotect(db.get_setting("notion_token")))
        self.journal.setText(db.get_setting("notion_journal_url"))
        self.day_log.setText(db.get_setting("notion_day_log_url"))
        self.weekly.setText(db.get_setting("notion_weekly_url"))
        self.enabled.toggled.connect(self._show_enabled)
        self.enabled.setChecked(notion_enabled(db))
        self._show_enabled(self.enabled.isChecked())

    def _show_enabled(self, on: bool):
        for widget in (self.token, self.journal, self.day_log, self.create, self.weekly,
                       self.test):
            widget.setEnabled(on)

    def _links(self):
        return (("Journal database", self.journal), ("Day Log database", self.day_log),
                ("Weekly reviews page", self.weekly))

    def values_ok(self) -> str:
        """'' when the links are usable (or empty), else what's wrong."""
        if not self.enabled.isChecked():
            return ""
        for name, box in self._links():
            if box.text().strip():
                try:
                    parse_id(box.text())
                except NotionError:
                    return f"{name}: that doesn't look like a Notion link."
        return ""

    def save(self):
        self.db.set_setting("notion_enabled", self.enabled.isChecked())
        self.db.set_setting("notion_token", protect(self.token.text().strip()))
        self.db.set_setting("notion_journal_url", self.journal.text().strip())
        self.db.set_setting("notion_day_log_url", self.day_log.text().strip())
        self.db.set_setting("notion_weekly_url", self.weekly.text().strip())

    def _busy(self, busy: bool, text: str = ""):
        self.test.setEnabled(not busy)
        self.create.setEnabled(not busy)
        if text:
            self.result.setText(text)

    def _test(self):
        problem = self.values_ok()
        if problem:
            self.result.setText(problem)
            return
        token, journal, day_log, weekly = (box.text().strip() for box in
                                           (self.token, self.journal, self.day_log, self.weekly))

        def work():
            client = NotionClient(token)
            lines = [f"Secret ✓ {client.whoami()}"]      # a bad secret stops here
            checks = []
            if journal:
                checks.append(("Journal", lambda: client.database_title(parse_id(journal))))
            if day_log:
                checks.append(("Day Log", lambda: client.database_title(parse_id(day_log))))
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
            self._busy(False, text or f"✗ {error}")

        self._busy(True, "Checking…")
        run_in_background(self, work, done)

    # ---------- create the Day Log database ----------

    def _create_day_log(self):
        problem = self.values_ok()
        if problem:
            self.result.setText(problem)
            return
        token, journal = self.token.text().strip(), self.journal.text().strip()
        if not token:
            self.result.setText("Paste your integration secret first.")
            return
        journal_id = parse_id(journal) if journal else None

        def find_parent():
            return NotionClient(token).parent_page(journal_id) if journal_id else None

        def found(parent, error):
            self._busy(False, "")
            if parent:
                answer = QMessageBox.question(
                    self, "Create Day Log",
                    f"Create the “Day Log” database in “{parent[1]}”, next to your Journal "
                    "and linked to it?\n\nYour Journal gets one new property, “Day Log”. "
                    "Nothing else in it changes.")
                if answer == QMessageBox.Yes:
                    self._create_in(token, parent[0], journal_id)
                return
            link, ok = QInputDialog.getText(
                self, "Create Day Log", (f"{error}\n\n" if error else "")
                + "Paste the link of the Notion page to put the Day Log in:")
            if not ok or not link.strip():
                return
            try:
                page_id = parse_id(link)
            except NotionError as bad:
                self.result.setText(f"✗ {bad}")
                return
            self._create_in(token, page_id, journal_id)

        self._busy(True, "Finding your Journal's page…")
        run_in_background(self, find_parent, found)

    def _create_in(self, token: str, page_id: str, journal_id: str | None):
        def create():
            return NotionClient(token).create_day_log_database(page_id, journal_id)

        def done(created, error):
            if error:
                self._busy(False, f"✗ {error}")
                return
            self.day_log.setText(created[1])
            self._busy(False, "Day Log ✓ created – press Save to keep it.")

        self._busy(True, "Creating the Day Log…")
        run_in_background(self, create, done)
