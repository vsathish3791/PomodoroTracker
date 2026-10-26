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

### Reports and deadlines (Phase 4)

- **Reports tab**: pick a period (today, this week, last 7 days, this month,
  last 30 days or custom dates) and show pomodoros or hours.
  - Totals: pomodoros (and daily average), focus time, tasks done (on time / late),
    and how often you skipped the app's suggestion.
  - Effort **by category**, **coding vs non-coding** and **by priority**.
  - **Daily trend** with your daily goal as a dashed line. Hover a bar for details.
  - **Estimate vs actual** for finished tasks.
  - **Export sessions CSV** (every focus/break block in the period, with task
    details) and **Export tasks CSV** (all tasks with totals). Opens in Excel.
- **Deadlines tab**: open tasks grouped as Overdue / Today / This week / Later /
  No date, with ▶ to start one, plus a **7-day workload check**: pomodoros due
  each day vs. what your daily goal allows, flagging overloaded days.
- Category colours come from a colour-blind-checked palette; each category keeps
  its colour everywhere.

### Prioritization (Phase 3)

Every open task gets a **Focus Score** (see `pomodoro/priority.py`):

| Priority | Points | | Due date | Points |
|---|---|---|---|---|
| P1 Critical | 40 | | Overdue | 50 |
| P2 High | 25 | | Today | 40 |
| P3 Medium | 10 | | Tomorrow | 30 |
| P4 Low | 0 | | Within 3 days | 20 |
| | | | Within 7 days | 10 |

**+20 if at risk**: the pomodoros still needed (tasks lined up by due date,
earliest first) don't fit into your daily goal on the working days left.
Ties go to the earlier due date, then to the task with less work left.

- **Focus Next** panel on the Timer tab: your top 3 tasks with the reasons
  and a ▶ button, plus a one-line summary (overdue, due today, at risk, 🍅 needed).
- The task box is **pre-filled with your top task**; you can still pick another.
- **Low-priority warning**: starting a task while an urgent one (P1, overdue,
  due today or at risk) has a higher score asks *Switch* / *Continue anyway* / *Cancel*.
  "Continue anyway" is logged and not asked again for that pair that day.
- **After each break** the app asks whether to continue or switch, if
  something more urgent is waiting.
- **Daily summary** notification on the first launch of the day.
- The Tasks tab shows the **Score** and **⚠ at risk**, sorted like Focus Next.

Settings used: `daily_goal` (default 8) and `working_days` (default Mon-Fri).

### Tasks (Phase 2)

- **Tasks tab**: every task with its category, type (coding / non-coding),
  priority (P1 Critical to P4 Low), due date, 🍅 done vs. estimate, and status.
  Open tasks are sorted by Focus Score. Overdue dates show in red.
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
| `pomodoro/priority.py` | Focus Score, at-risk deadlines, warnings, daily summary - plain Python |
| `pomodoro/ui/focus_next.py` | The Focus Next panel |
| `pomodoro/reports.py` | Report numbers, deadline board, workload, CSV export - plain Python |
| `pomodoro/ui/reports_tab.py` | The Reports tab |
| `pomodoro/ui/deadlines_tab.py` | The Deadlines tab |
| `pomodoro/ui/charts.py` | Simple bar and column charts |
| `pomodoro/models.py` | Priorities, statuses, types, default categories, date labels |
| `pomodoro/ui/main_window.py` | The main window and Timer tab |
| `pomodoro/ui/tasks_tab.py` | The Tasks tab (list, filters, actions) |
| `pomodoro/ui/task_dialog.py` | Add / edit task form |
| `pomodoro/ui/tray.py` | System tray icon, menu and notifications |
| `pomodoro/ui/theme.py` | Colours, icon drawing, stylesheet |

## Roadmap

1. ~~Core timer~~ (done)
2. ~~Tasks: categories, coding/non-coding type, priority, due date, estimate, status~~ (done)
3. ~~Prioritization: Focus Score, "Focus Next" panel, low-priority warnings, at-risk deadlines~~ (done)
4. ~~Reports: effort by category, priority and type; deadline board; CSV export~~ (done)
5. Polish: settings screen, mini window, global hotkey, calendar, installer
