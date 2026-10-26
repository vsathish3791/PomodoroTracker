# Pomodoro Tracker

A Windows desktop pomodoro timer that tracks how many 25-minute focus blocks you
spend on each task, built with Python and PySide6 (Qt).

## Run it

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

Run the tests:

```bash
.venv\Scripts\python -m unittest discover tests
```

## What works now

### Tasks (Phase 2)

- **Tasks tab**: every task with its category, type (coding / non-coding),
  priority (P1 Critical to P4 Low), due date, 🍅 done vs. estimate, and status.
  Open tasks are sorted by priority, then due date. Overdue dates show in red.
- **+ New task / Edit** (or double-click a row) opens a form for all the details.
  Type a new category name in the form to create it.
- **Filter** by Open / Done / All and by category, or search by name and notes.
- **▶ Start pomodoro** on a selected task jumps to the timer and starts it.
- **✓ Mark done** in the Tasks tab or under the timer's task box. Done tasks
  can be reopened. **Delete** keeps the task's time in your daily totals.
- The Timer tab shows the selected task's priority, category, due date and progress.
- Tasks typed straight into the timer are created as P3 Medium with no
  category; add details later in the Tasks tab.

### Timer (Phase 1)

- **Enter a task name before starting.** Type a new name or pick a recent task
  from the drop-down, then press **Start** (or Enter). Each pomodoro is saved
  against that task, and the window shows the task's total so far.
  The task can't be changed in the middle of a focus block.
- 25-minute focus, then a 5-minute break that starts automatically.
  After the break, the next focus block waits for you to press **Start**.
- **Start / Pause / Resume / Skip / Stop.** Paused time is not counted.
- A pomodoro only counts if it runs the full 25 minutes. Stopped or skipped
  blocks longer than 1 minute are still logged as partial time.
- Sound + Windows notification when a block ends.
- Tray icon shows minutes left; right-click it for Start/Pause, Skip, Quit.
  Closing the window keeps the app running in the tray.
- Today's count (🍅 done / daily goal) and minutes focused.

Your data is stored in `%APPDATA%\PomodoroTracker\pomodoro.db` (SQLite).
Settings such as durations live in its `settings` table; a settings screen comes in Phase 5.

## Code map

| File | What it does |
|---|---|
| `main.py` | Entry point |
| `pomodoro/timer.py` | The focus/break cycle - plain Python, no UI |
| `pomodoro/database.py` | SQLite schema, tasks, categories, settings, session log, stats |
| `pomodoro/app.py` | Connects the timer, database, window and tray |
| `pomodoro/models.py` | Priorities, statuses, types, default categories, date labels |
| `pomodoro/ui/main_window.py` | The main window and Timer tab |
| `pomodoro/ui/tasks_tab.py` | The Tasks tab (list, filters, actions) |
| `pomodoro/ui/task_dialog.py` | Add / edit task form |
| `pomodoro/ui/tray.py` | System tray icon, menu and notifications |
| `pomodoro/ui/theme.py` | Colours, icon drawing, stylesheet |

## Roadmap

1. ~~Core timer~~ (done)
2. ~~Tasks: categories, coding/non-coding type, priority, due date, estimate, status~~ (done)
3. Prioritization: Focus Score, "Focus Next" panel, low-priority warnings, at-risk deadlines
4. Reports: effort by category, priority and type; deadline board; CSV export
5. Polish: settings screen, mini window, global hotkey, calendar, installer
