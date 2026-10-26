"""Wires the pieces together: database + timer + window + tray icon."""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from pomodoro.database import Database
from pomodoro.models import PRIORITIES, due_label, pomodoro_progress
from pomodoro.timer import Phase, PhaseRecord, PomodoroTimer, TimerSettings
from pomodoro.ui.main_window import MainWindow
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

        self.tasks_tab = TasksTab(db)
        self.tasks_tab.start_requested.connect(self.start_task)
        self.tasks_tab.tasks_changed.connect(self._on_tasks_changed)
        self.window.tabs.addTab(self.tasks_tab, "Tasks")

        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = TrayIcon()
            self.tray.show_window.connect(self.show_window)
            self.tray.toggle_timer.connect(self.start_or_pause)
            self.tray.skip_phase.connect(self.timer.skip)
            self.tray.quit_app.connect(self.quit)
            self.tray.show()
        self._told_about_tray = False

        # Refresh the display 4x a second; the timer itself measures real time.
        self.ticker = QTimer(interval=250)
        self.ticker.timeout.connect(self._tick)
        self.ticker.start()

        self.window.show_hint("Enter a task, then press Start.")
        self._refresh_stats()
        self._refresh_task_info()
        self._refresh_display()

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
            self.focus_task_id = self.db.get_or_create_task(name)
            self.focus_task_name = self.db.get_task(self.focus_task_id)["title"]
            self.window.set_task_choices(self.db.recent_open_tasks())
            self.tasks_tab.refresh()
        t.start()
        self._refresh_task_info()

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
        self.window.show_hint(f'✓ "{title}" marked done. Nice work!')
        self._on_tasks_changed()
        self.tasks_tab.refresh()

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
        self._refresh_task_info()

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
        self._notify(title, message)

    # ---------- display ----------

    def _refresh_display(self):
        t = self.timer
        remaining = t.remaining_seconds()
        self.window.show_state(t.phase, t.running, t.started, remaining, t.duration_seconds())
        if self.tray:
            self.tray.show_state(t.phase, t.running, t.started, remaining)

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

    def _on_tasks_changed(self):
        self.window.set_task_choices(self.db.recent_open_tasks())
        if self.timer.phase == Phase.FOCUS and self.timer.started:
            task = self.db.get_task(self.focus_task_id)
            if task:
                self.focus_task_name = task["title"]   # it may have been renamed
                self.window.set_task_name(task["title"])
        self._refresh_task_info()

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
        self.window.allow_close = True
        self.window.close()
        if self.tray:
            self.tray.hide()
        self.db.close()
        self.app.quit()


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("Pomodoro Tracker")
    app.setQuitOnLastWindowClosed(False)  # keep running in the tray
    app.setStyle("Fusion")

    pomodoro_app = PomodoroApp(app, Database())
    pomodoro_app.show_window()
    return app.exec()
