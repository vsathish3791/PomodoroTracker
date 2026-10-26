"""Wires the pieces together: database + timer + window + tray icon."""

import os
import sys
from datetime import date

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from pomodoro import __version__
from pomodoro.database import Database
from pomodoro.hotkey import GlobalHotkey
from pomodoro.models import PRIORITIES, due_label, pomodoro_progress
from pomodoro.priority import ScoredTask, ScoreWeights, day_summary, rank_tasks, should_warn
from pomodoro.timer import Phase, PhaseRecord, PomodoroTimer, TimerSettings
from pomodoro.ui.main_window import MainWindow
from pomodoro.ui.mini_window import MiniWindow
from pomodoro.ui.settings_dialog import SettingsDialog
from pomodoro.ui.deadlines_tab import DeadlinesTab
from pomodoro.ui.reports_tab import ReportsTab
from pomodoro.ui.tasks_tab import TasksTab
from pomodoro.ui.theme import PHASE_COLORS, make_icon
from pomodoro.ui.tray import TrayIcon

# Partial blocks shorter than this are not worth logging (e.g. pressed Start by mistake).
MIN_LOGGED_SECONDS = 60


def play_sound():
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        QApplication.beep()


class PomodoroApp:
    def __init__(self, app: QApplication, db: Database):
        self.app = app
        self.db = db
        self.timer = PomodoroTimer(TimerSettings.from_db(db))
        self.timer.on_phase_changed = self._on_phase_changed
        self.timer.on_phase_finished = self._on_phase_finished

        # The task the current/last focus block belongs to.
        self.focus_task_id: int | None = None
        self.focus_task_name = ""
        # Warnings you already answered with "Continue anyway": (day, task name, suggested id).
        self._dismissed_warnings: set[tuple] = set()

        self.window = MainWindow()
        self.window.setWindowIcon(make_icon(PHASE_COLORS[Phase.FOCUS]))
        self.window.start_button.clicked.connect(self.start_or_pause)
        self.window.task_entered.connect(self._on_task_entered)
        self.window.skip_button.clicked.connect(self.timer.skip)
        self.window.stop_button.clicked.connect(self.timer.stop)
        self.window.close_requested.connect(self._on_close_requested)
        self.window.mark_done_button.clicked.connect(self.mark_current_task_done)
        self.window.task_input.currentTextChanged.connect(self._refresh_task_info)
        self.window.set_task_choices(self.db.recent_open_tasks())
        self.window.focus_next.start_requested.connect(self.start_task)

        self.tasks_tab = TasksTab(db)
        self.tasks_tab.rank_lookup = lambda: {s.id: s for s in self.rank()}
        self.tasks_tab.start_requested.connect(self.start_task)
        self.tasks_tab.tasks_changed.connect(self._on_tasks_changed)
        self.window.tabs.addTab(self.tasks_tab, "Tasks")

        self.deadlines_tab = DeadlinesTab()
        self.deadlines_tab.plan_provider = lambda: (
            self.rank(), self.db.get_int("daily_goal"), self.db.day_stats()["pomodoros"],
            self.db.get_working_days())
        self.deadlines_tab.start_requested.connect(self.start_task)
        self.window.tabs.addTab(self.deadlines_tab, "Deadlines")

        self.reports_tab = ReportsTab(db)
        self.window.tabs.addTab(self.reports_tab, "Reports")
        # Reports and Deadlines are redrawn when you open them.
        self.window.tabs.currentChanged.connect(lambda _: self._refresh_open_tab())

        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = TrayIcon()
            self.tray.show_window.connect(self.show_window)
            self.tray.toggle_timer.connect(self.start_or_pause)
            self.tray.skip_phase.connect(self.timer.skip)
            self.tray.toggle_mini.connect(self.toggle_mini)
            self.tray.open_settings.connect(self.open_settings)
            self.tray.quit_app.connect(self.quit)
            self.tray.show()
        self._told_about_tray = False

        self.window.settings_button.clicked.connect(self.open_settings)
        self.window.mini_button.clicked.connect(self.toggle_mini)

        # Small always-on-top timer
        self.mini = MiniWindow()
        self.mini.toggle_requested.connect(self.start_or_pause)
        self.mini.open_main.connect(self.show_window)
        self.mini.hidden_by_user.connect(lambda: self._set_mini_visible(False))
        self.mini.moved.connect(lambda pos: self.db.set_setting("mini_window_pos",
                                                                f"{pos.x()},{pos.y()}"))

        # System-wide Start / Pause shortcut
        self.hotkey = GlobalHotkey(app, int(self.window.winId()), self._on_hotkey)
        self._apply_hotkey(show_errors=False)

        # Refresh the display 4x a second; the timer itself measures real time.
        self.ticker = QTimer(interval=250)
        self.ticker.timeout.connect(self._tick)
        self.ticker.start()

        self.window.show_hint("Enter a task, then press Start.")
        self._refresh_stats()
        self._prefill_top_task()
        if self.window.task_name():
            self.window.show_hint("Your top task is filled in. Press Start, or pick another.")
        self._refresh_task_info()
        self._refresh_focus_next()
        self.tasks_tab.refresh()
        self._refresh_display()
        if self.db.get_bool("mini_window_visible"):
            self._set_mini_visible(True)
        # Give the tray icon a moment to appear before the first notification.
        QTimer.singleShot(1500, self._maybe_show_daily_summary)

    # ---------- settings, mini timer, shortcut ----------

    def open_settings(self):
        self.show_window()
        if not SettingsDialog(self.db, self.window).exec():
            return
        self.timer.settings = TimerSettings.from_db(self.db)   # used from the next block
        self._apply_hotkey(show_errors=True)
        self._refresh_stats()
        self._refresh_focus_next()
        self.tasks_tab.refresh()
        self._refresh_display()
        self.window.show_hint("Settings saved.")

    def _apply_hotkey(self, show_errors: bool):
        if not self.db.get_bool("hotkey_enabled"):
            self.hotkey.unregister()
            return
        shortcut = self.db.get_setting("hotkey")
        if self.hotkey.register(shortcut):
            self.window.start_button.setToolTip(f"Start / Pause ({shortcut} from any app)")
            return
        message = (f"The shortcut {shortcut} couldn't be set up. Another app may already use "
                   "it - pick a different one in Settings > Shortcut.")
        if show_errors:
            QMessageBox.warning(self.window, "Shortcut not available", message)
        else:
            self._notify("Shortcut not available", message)

    def _on_hotkey(self):
        self.start_or_pause()
        if self.tray and not self.window.isVisible() and not self.mini.isVisible():
            t = self.timer
            state = "Running" if t.running else ("Paused" if t.started else "Ready")
            self.tray.notify(f"{state}: {t.phase.label}", self._task_label())

    def toggle_mini(self):
        self._set_mini_visible(not self.mini.isVisible())

    def _set_mini_visible(self, visible: bool):
        self.db.set_setting("mini_window_visible", visible)
        if self.tray:
            self.tray.mini_action.setChecked(visible)
        if not visible:
            self.mini.hide()
            return
        self.mini.move(self._mini_position())
        self._refresh_display()
        self.mini.show()

    def _mini_position(self) -> QPoint:
        """Saved position if it's still on a screen, else the bottom-right of the main screen."""
        saved = self.db.get_setting("mini_window_pos")
        if saved:
            x, y = (int(v) for v in saved.split(","))
            if QGuiApplication.screenAt(QPoint(x + 20, y + 20)) is not None:
                return QPoint(x, y)
        area = QGuiApplication.primaryScreen().availableGeometry()
        return QPoint(area.right() - MiniWindow.WIDTH - 24, area.bottom() - MiniWindow.HEIGHT - 24)

    def _task_label(self) -> str:
        if self.timer.phase == Phase.FOCUS and self.timer.started:
            return self.focus_task_name
        return self.window.task_name() or "No task chosen"

    # ---------- prioritization ----------

    def rank(self) -> list[ScoredTask]:
        """Open tasks, best next task first (see pomodoro/priority.py)."""
        return rank_tasks(self.db.list_tasks("open"), date.today(),
                          self.db.get_int("daily_goal"), self.db.day_stats()["pomodoros"],
                          self.db.get_working_days(), self.weights())

    def weights(self) -> ScoreWeights:
        return ScoreWeights.from_dict(self.db.get_json("score_weights"))

    def _summary(self, ranked: list[ScoredTask]) -> str:
        return day_summary(ranked, date.today(), self.db.get_int("daily_goal"),
                           self.db.day_stats()["pomodoros"])

    def _focus_in_progress(self) -> bool:
        return self.timer.phase == Phase.FOCUS and self.timer.started

    def _prefill_top_task(self):
        """If the task box is empty, suggest the best task (you can still change it)."""
        if self._focus_in_progress() or self.window.task_name():
            return
        ranked = self.rank()
        if ranked:
            self.window.set_task_name(ranked[0].title)

    def _ask_to_switch(self, title: str, chosen_name: str, top: ScoredTask) -> str:
        """Ask whether to switch to a more urgent task. Returns 'switch', 'continue' or 'cancel'."""
        self.show_window()
        box = QMessageBox(self.window)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(title)
        box.setText(f'<b>"{top.title}"</b> needs attention<br>({top.short_reason()}).')
        box.setInformativeText(f'Switch to it, or continue with "{chosen_name}"?')
        switch = box.addButton(f'Switch to "{top.title}"', QMessageBox.AcceptRole)
        keep = box.addButton("Continue anyway", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(switch)
        box.exec()
        clicked = box.clickedButton()
        if clicked is switch:
            return "switch"
        if clicked is keep:
            return "continue"
        return "cancel"

    def _suggest_after_break(self):
        """After a break: point you at the most important task before you press Start."""
        if self.timer.running:
            return   # auto-start is on; the next block has already begun
        ranked = self.rank()
        if not ranked:
            return
        top = ranked[0]
        current_id = self.db.find_open_task(self.window.task_name())
        if current_id is None:
            self.window.set_task_name(top.title)
            self.window.show_hint(f'Suggested next: "{top.title}" ({top.short_reason()}).')
            return
        if should_warn(current_id, ranked, weights=self.weights()) is None:
            return
        current = self.db.get_task(current_id)["title"]
        choice = self._ask_to_switch("Break over - what next?", current, top)
        if choice == "switch":
            self.window.set_task_name(top.title)
        elif choice == "continue":
            self._dismissed_warnings.add((date.today(), current.lower(), top.id))
            self.db.add_override(current_id, top.id)
        self.window.show_hint("Press Start when you're ready for the next pomodoro.")

    def _maybe_show_daily_summary(self):
        """Once a day, on the first launch: what's urgent today."""
        today = date.today().isoformat()
        if self.db.get_setting("last_summary_date") == today:
            return
        ranked = self.rank()
        if not ranked:
            return
        self.db.set_setting("last_summary_date", today)
        self._notify("Today's focus",
                     f"{self._summary(ranked)}\nStart with: {ranked[0].title}")

    # ---------- user actions ----------

    def start_or_pause(self):
        """Start/Pause/Resume. A new focus block needs a task name first."""
        t = self.timer
        if t.running:
            t.pause()
            return

        starting_new_focus = t.phase in (Phase.IDLE, Phase.FOCUS) and not t.started
        if starting_new_focus:
            name = self.window.task_name()
            if not name:
                self.show_window()
                self.window.ask_for_task()
                return
            # Is something more urgent waiting? (Asked only once per task pair per day.)
            ranked = self.rank()
            existing_id = self.db.find_open_task(name)
            top = should_warn(existing_id, ranked, weights=self.weights())
            override_of = None
            if top and (date.today(), name.lower(), top.id) not in self._dismissed_warnings:
                choice = self._ask_to_switch("Higher-priority task waiting", name, top)
                if choice == "cancel":
                    return
                if choice == "switch":
                    name = top.title
                    self.window.set_task_name(name)
                else:
                    override_of = top.id
                    self._dismissed_warnings.add((date.today(), name.lower(), top.id))

            self.focus_task_id = self.db.get_or_create_task(name)
            self.focus_task_name = self.db.get_task(self.focus_task_id)["title"]
            if override_of is not None:
                self.db.add_override(self.focus_task_id, override_of)
            self.window.set_task_choices(self.db.recent_open_tasks())
            self.tasks_tab.refresh()
        t.start()
        self._refresh_task_info()
        self._refresh_focus_next()

    def start_task(self, task_id: int):
        """'Start pomodoro' from the Tasks tab."""
        t = self.timer
        task = self.db.get_task(task_id)
        if t.phase == Phase.FOCUS and t.started:
            if task_id != self.focus_task_id:
                QMessageBox.information(
                    self.window, "Pomodoro in progress",
                    f'You are in the middle of a pomodoro for "{self.focus_task_name}".\n\n'
                    "Let it finish, or press Stop first, then start the new task.")
                return
        else:
            self.window.set_task_name(task["title"])
        self.window.tabs.setCurrentIndex(0)
        self.show_window()
        if t.phase in (Phase.BREAK, Phase.LONG_BREAK) and t.started:
            self.window.show_hint(f'Next up: "{task["title"]}". Press Start after your break.')
        elif not t.running:
            self.start_or_pause()

    def mark_current_task_done(self):
        task_id = self._current_task_id()
        if task_id is None:
            return
        title = self.db.get_task(task_id)["title"]
        self.db.set_task_status(task_id, "done")
        if not (self.timer.phase == Phase.FOCUS and self.timer.started):
            self.window.set_task_name("")
        self._on_tasks_changed()
        self.tasks_tab.refresh()
        self._prefill_top_task()
        self.window.show_hint(f'✓ "{title}" marked done. Nice work!')

    def _on_task_entered(self):
        # Enter in the task box starts the pomodoro (but never pauses one).
        if not self.timer.running:
            self.start_or_pause()

    # ---------- timer events ----------

    def _tick(self):
        self.timer.tick()
        self._refresh_display()

    def _on_phase_changed(self, phase: Phase, running: bool):
        hints = {
            Phase.IDLE: "Enter a task, then press Start.",
            Phase.FOCUS: "Stay on one task until the timer rings.",
            Phase.BREAK: "Step away from the screen for a few minutes.",
            Phase.LONG_BREAK: "Nice streak! Take a longer rest.",
        }
        hint = hints[phase]
        if not running and not self.timer.started and phase != Phase.IDLE:
            what = "next pomodoro" if phase == Phase.FOCUS else phase.label.lower()
            hint = f"Press Start when you're ready for the {what}."
        self.window.show_hint(hint)
        self.window.set_task_locked(phase == Phase.FOCUS and self.timer.started)
        self._refresh_task_info()
        self._refresh_focus_next()
        self._refresh_display()

    def _on_phase_finished(self, record: PhaseRecord):
        is_focus = record.phase == Phase.FOCUS
        if record.completed or record.elapsed_seconds >= MIN_LOGGED_SECONDS:
            self.db.add_session(
                kind=record.phase.value,
                start=record.start,
                end=record.end,
                duration_min=record.elapsed_seconds / 60,
                completed=record.completed,
                task_id=self.focus_task_id if is_focus else None,
            )
            self._refresh_stats()
            self.tasks_tab.refresh()
        if is_focus and self.focus_task_id is not None:
            task = self.db.get_task(self.focus_task_id)
            if task is None or task["status"] == "done":
                self.window.set_task_name("")   # finished task: pick the next one
                self._prefill_top_task()
        self._refresh_task_info()
        self._refresh_focus_next()

        if not record.completed:
            return  # skipped/stopped by the user - no need to notify

        if self.db.get_bool("sound_enabled"):
            play_sound()
        if is_focus:
            done = self.db.task_stats(self.focus_task_id)["pomodoros"]
            title = "🍅 Pomodoro complete!"
            message = (f"{self.focus_task_name}: {done} so far. "
                       f"Time for a {self.db.get_int('break_minutes')}-minute break.")
        else:
            title = "Break over"
            message = "Ready for the next pomodoro? Press Start when you are."
            ranked = self.rank()
            if ranked:
                message += f"\nMost important now: {ranked[0].title}"
        self._notify(title, message)
        if not is_focus:
            # Let the notification show first, then ask what to do next.
            QTimer.singleShot(300, self._suggest_after_break)

    # ---------- display ----------

    def _refresh_display(self):
        t = self.timer
        remaining = t.remaining_seconds()
        self.window.show_state(t.phase, t.running, t.started, remaining, t.duration_seconds())
        if self.tray:
            self.tray.show_state(t.phase, t.running, t.started, remaining)
        if self.mini.isVisible():
            self.mini.show_state(t.phase, t.running, t.started, remaining, self._task_label())

    def _refresh_stats(self):
        stats = self.db.day_stats()
        self.window.show_stats(stats["pomodoros"], self.db.get_int("daily_goal"),
                               stats["focus_minutes"])

    def _current_task_id(self) -> int | None:
        """The task in the focus block, or else the open task named in the task box."""
        if self.timer.phase == Phase.FOCUS and self.timer.started:
            return self.focus_task_id
        return self.db.find_open_task(self.window.task_name())

    def _refresh_task_info(self):
        """The line under the task box: priority, category, due date and progress."""
        task_id = self._current_task_id()
        task = self.db.get_task(task_id) if task_id is not None else None
        if task is None:
            text = ("New task - it's created when you start. Add details in the Tasks tab."
                    if self.window.task_name() else "")
            self.window.show_task_info(text, can_mark_done=False)
            return
        parts = [PRIORITIES[task["priority"]]]
        if task["category"]:
            parts.append(task["category"])
        if task["due_date"]:
            due = due_label(task["due_date"])
            if due.startswith("Overdue"):
                parts.append("⚠ " + due)
            else:
                parts.append("Due " + (due.lower() if due in ("Today", "Tomorrow") else due))
        parts.append("🍅 " + pomodoro_progress(task["pomodoros"], task["estimate_pomodoros"]))
        parts.append(f"{round(task['focus_minutes'])} min")
        if task["status"] == "done":
            parts.insert(0, "✓ Done")
        # Non-breaking spaces inside each part, so lines only wrap between parts.
        parts = [part.replace(" ", " ") for part in parts]
        self.window.show_task_info("  ·  ".join(parts),
                                   can_mark_done=task["status"] != "done")

    def _refresh_open_tab(self):
        current = self.window.tabs.currentWidget()
        if current in (self.reports_tab, self.deadlines_tab):
            current.refresh()

    def _refresh_focus_next(self):
        ranked = self.rank()
        self.window.focus_next.show_tasks(ranked, self._summary(ranked))
        self.window.focus_next.set_start_enabled(not self._focus_in_progress())
        self._refresh_open_tab()

    def _on_tasks_changed(self):
        self.window.set_task_choices(self.db.recent_open_tasks())
        if self.timer.phase == Phase.FOCUS and self.timer.started:
            task = self.db.get_task(self.focus_task_id)
            if task:
                self.focus_task_name = task["title"]   # it may have been renamed
                self.window.set_task_name(task["title"])
        self._refresh_task_info()
        self._refresh_focus_next()

    def _notify(self, title: str, message: str):
        if self.tray:
            self.tray.notify(title, message)
        else:
            self.show_window()

    # ---------- window / app lifecycle ----------

    def show_window(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _on_close_requested(self):
        if not self.tray:
            self.quit()
            return
        self.window.hide()
        if not self._told_about_tray:
            self.tray.notify("Still running", "Pomodoro Tracker keeps running in the tray. "
                                              "Right-click the icon to quit.")
            self._told_about_tray = True

    def quit(self):
        self.timer.stop()  # logs a partial block if one is in progress
        self.hotkey.unregister()
        self.mini.close()
        self.window.allow_close = True
        self.window.close()
        if self.tray:
            self.tray.hide()
        self.db.close()
        self.app.quit()


INSTANCE_NAME = "PomodoroTracker-" + (os.environ.get("USERNAME") or "user")


def already_running() -> bool:
    """If the app is already open, ask it to show its window and return True."""
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_NAME)
    if socket.waitForConnected(300):
        socket.write(b"show")
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return True
    return False


def listen_for_second_launch(pomodoro_app: PomodoroApp) -> QLocalServer:
    """Opening the app again (e.g. from the Start menu) just brings this window forward."""
    QLocalServer.removeServer(INSTANCE_NAME)   # clean up after a crash
    server = QLocalServer()
    server.newConnection.connect(lambda: (server.nextPendingConnection(),
                                          pomodoro_app.show_window()))
    server.listen(INSTANCE_NAME)
    return server


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("Pomodoro Tracker")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)  # keep running in the tray
    app.setStyle("Fusion")
    if already_running():
        return 0

    pomodoro_app = PomodoroApp(app, Database())
    server = listen_for_second_launch(pomodoro_app)  # noqa: F841 (keep it alive)
    pomodoro_app.show_window()
    return app.exec()
