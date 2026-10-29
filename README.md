# Pomodoro Tracker

A Windows desktop pomodoro timer that tracks how many 25-minute focus blocks you
spend on each task, built with Python and PySide6 (Qt).

## Install it on your PC (or a friend's)

Needs Windows 10/11 and Python 3.10+ ([python.org](https://www.python.org/downloads/),
tick *Add python.exe to PATH*, or `winget install Python.Python.3.12`).

1. Get the code: **Code -> Download ZIP** on GitHub and unzip it (e.g. to
   `Documents\PomodoroTracker`), or `git clone` it.
2. In that folder, run:

   ```bash
   powershell -ExecutionPolicy Bypass -File setup.ps1
   ```

   It creates `.venv`, installs PySide6 and adds **Pomodoro Tracker** to the desktop and
   Start menu (add `-Startup` to start it when you sign in). Run it again after updating.

Each person's tasks stay on their own PC in `%APPDATA%\PomodoroTracker\pomodoro.db`;
nothing is shared or uploaded. **No Notion needed**: new users get the app without any
Notion buttons; anyone who wants it ticks *Use Notion* in Settings -> Notion.

### Share it

| Way | Good for | Notes |
|---|---|---|
| GitHub repo + `setup.ps1` | Anyone with Python | Works with Smart App Control on (uses signed Python). Repo is public (MIT licence). |
| Portable ZIP from `build.py` | People without Python | Unzip, run `PomodoroTracker.exe`. Unsigned: SmartScreen warns (*More info -> Run anyway*); blocked where Smart App Control is on. |
| Installer from `build.py` | Same as the ZIP | Adds shortcuts and an uninstaller. Same signing caveat. |

Attach the ZIP and installer to a **GitHub Release** so people download them from one
page. To remove the SmartScreen / Smart App Control problem the files have to be
code-signed (e.g. Azure Trusted Signing, a paid certificate).

## Run it from source

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

Run the tests:

```bash
.venv\Scripts\python -m unittest discover tests
```

## Build the Windows app and installer

```bash
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python build.py
```

- `dist\PomodoroTracker\PomodoroTracker.exe` - the app, runnable without Python.
- `installer_output\PomodoroTracker-<version>-portable.zip` - the same app zipped, to share.
- `installer_output\PomodoroTracker-Setup-<version>.exe` - the installer, built only if
  [Inno Setup 6](https://jrsoftware.org/isinfo.php) is installed
  (`winget install JRSoftware.InnoSetup`). It installs for your user only (no admin),
  adds Start menu and optional desktop shortcuts, can start the app when you sign in,
  and has an uninstaller. Your data in `%APPDATA%\PomodoroTracker` is kept on uninstall.

### If Windows Smart App Control blocks the installer

Smart App Control only runs signed or well-known programs, so it blocks this app's
unsigned installer and exe ("Error 4551: An Application Control policy has blocked
this file"). Run the app through the project's Python instead - `pythonw.exe` is signed
by the Python Software Foundation and PySide6 by The Qt Company:

```bash
powershell -ExecutionPolicy Bypass -File create_shortcuts.ps1
```

This adds **Pomodoro Tracker (Python)** to the desktop and Start menu (add `-Startup`
to also start it when you sign in, or `-Name "Pomodoro Tracker"` for another name).
The app then runs straight from this folder: to update, change the code and restart it.
Your data stays in `%APPDATA%\PomodoroTracker`, the same as the installed version.

## What works now

### Notion connection and sharing (v1.9)

- **Settings -> Notion** (optional): paste an internal integration secret, your Journal
  database link and a weekly-reviews page link, press **Test**. The secret is encrypted
  with Windows DPAPI (only your Windows account can read it).
- **Close the day -> Send to Notion Journal** puts today's numbers in today's Journal
  entry's *What happened?* (creates a *Daily* entry if there's none). Only the app's own
  "Pomodoro Tracker –" line is replaced; your writing is never touched.
- **Weekly review -> Send to Notion** creates the week's page under your weekly-reviews
  page. Without a connection the Copy buttons work as before.
- Sharing: `setup.ps1` (one-command install on another PC) and a portable ZIP from
  `build.py`.

### Growth: stretch zone, best hours, practice, Then vs Now (v1.8)

The execution side of a growth mindset, measured from your own pomodoros (reflection
stays in Notion):

- **Stretch rating** - finishing a task shows a one-click bar at the bottom:
  *😌 Comfort · 💪 Stretch · 😰 Panic* (or Skip).
- **🎯 Practice mode** on the Timer - a skill and one narrow target; afterwards rate the
  difficulty 1-5.
- **Best hours** - your peak and weakest hours from completed pomodoros and
  distractions. Focus Next adds points (Settings -> Focus Score -> *Fits the time of day*)
  to ⚡ Deep-work tasks in your peak hours and ☐ Plan/Close tasks in your weakest hour.
- **Reports -> Growth** - *Then vs Now* (last 30 days vs the 30 before, incl. 🍅 per task
  by category), best-hours chart, stretch mix with advice, practice per skill with the
  difficulty trend.

### Today, close the day, weekly review, in-app guide (v1.7)

Tabs are now **Timer · Today · To-Do · Goals · Reports**.

- **Today**: routines & habits for today (by cue time), today's planned focus tasks, a
  **capacity** bar (still to do vs. what your daily goal leaves) and goals at a glance.
  - **☀ Plan my day...** - tick a few focus tasks (best first); it warns when they won't
    fit. Planning doesn't change due dates.
  - **☾ Close the day...** - today's numbers, give reasons to open events, move
    unfinished planned tasks to tomorrow, **Plan tomorrow...**, **Copy for Notion
    Journal** (the numbers for "What happened?") and **Open Notion Journal**.
- **To-Do**: switch between **☰ List** and **▦ Table** (the old Tasks tab).
- **Reports**: **Effort** (all charts), **Deadlines** (board + 7-day workload) and
  **Weekly review** - Falconi's three-generation report (Planned -> Done & results ->
  Problems & next actions), **Copy for Notion** or **Save as...** Markdown.
- **? Help** (or **F1**, or the tray menu): a short guide to every feature -
  `pomodoro/USER_GUIDE.md`.

### Goals and the control panel (v1.6)

A new **Goals** tab (Falconi: control items with targets; Clear: systems over goals):

- **Control panel** - *your system* (lead measures): focus per working day vs your daily
  goal, habit consistency, routine done, distractions per pomodoro; and *results* (lag
  measures): finished on time, estimate accuracy, improvement share. Each tile shows
  **● On track / ▲ Behind / ■ Off track** (hover for how it's measured).
- **Goals**: *Weekly rhythm* ("Learning AI: at least 10 🍅 every week", judged against how
  far into the working week you are) or *Target by a date* ("Career: 40 🍅 by 30 Nov",
  with a forecast from your last two weeks' pace). Scope: all work, a project, a kind of
  work or a category. Right-click or double-click to edit.
- **Time split this week**: Routine / Habit / Improvement against your targets
  (**Change targets...**, must add up to 100%).
- **Compounding**: your running total of pomodoros, for all work or one scope.
- **Learned estimates**: the task form suggests *"Usually ~2 🍅 for Development (median
  of 4 finished tasks)"* with a **Use** button.

### Interruptions and misses (v1.5)

Falconi's anomaly handling: find out why focus time is lost, then fix the biggest cause.

- **Stopped a pomodoro early?** A small bar on the Timer asks *what got in the way?* -
  one click: *Interrupted, Meeting, Underestimated, Unclear, Low energy, Tech issue,
  Other* - or **Skip**. The lost minutes are recorded either way.
- **⚡ I got distracted** appears while focusing: one click logs a distraction; the
  timer keeps going and the button shows the count.
- **Missed recurring tasks** and **tasks finished after their due date** are logged
  automatically.
- **Reports -> Interruptions & misses**: a **Pareto chart** of causes, biggest first,
  with the *vital few* behind ~80% in red, plus minutes lost.
  - **Label N events...** gives reasons to anything still without one.
  - **Plan a countermeasure...** opens a new task for the top cause (e.g. a habit such
    as *Teams on Do Not Disturb during pomodoros*). Write-ups belong in Notion.
- The task form explains each **Kind of work** under the box.

### Habits: cues, stacking, streaks (v1.4)

Based on *Atomic Habits*. These options appear in the task form when **Repeat** is on:

- **Cue** - *at [time] [place]*, e.g. *08:30 at my desk*. With **Remind me**, a Windows
  notification appears at that time; click it to start a pomodoro.
- **Stack** - *After [another recurring task]*: when you finish that one, the app suggests
  this one next (notification + it's put in the Timer's task box).
- **2-minute version** - the smallest form of the habit. On a hard day right-click the
  task -> **Showed up**: the day counts (½) and your streak continues.
- The form spells it out: *"I will Read 1 pomodoro at 08:30 at my desk. On a hard day:
  Read one page."*
- **Recurring** list: a **day-by-day strip** per series (✓ done, ½ showed up, ✗ missed,
  ○ today, grey = coming days; hover for date and pomodoros) and **🔥 streak / best**.
- **Never miss twice**: if last time was missed, today's occurrence gets +30 Focus Score
  points (Settings -> Focus Score -> *Missed last time*), shows *"don't miss twice"* and
  counts as urgent.
- New series never mark days **before you created them** as missed.

### Recurring tasks, kind of work and checklists (v1.3)

- **Repeat** in the task form: *Daily* (every day or working days only), *Weekly* (pick the
  weekdays) or *Monthly* (day of month; 29-31 use the last day of short months). A start
  date and a **Repeat until** date are required; the form shows e.g. *"Every working day
  until 27 Dec - 44 times"*. Or open **To-Do -> Recurring**, type a name and press Enter.
- Each occurrence is a normal task, created **on its day** (at start-up, and at midnight if
  the app is running). **Tomorrow** and **This Week** show the rest as a grey *Coming up*
  preview.
- An occurrence still open when the next one appears is marked **Missed**; days skipped
  while the PC was off are recorded as missed too. Right-click -> *Recurring -> Skip this
  one* marks one missed on purpose.
- Editing an occurrence asks **Just this one** or **This and future ones**. Right-click a
  series in **Recurring** to edit, *Stop repeating* (history kept, can resume) or delete.
- **Recurring** list: each series with done / missed / of total, % done and the next date.
- **Kind of work** on every task: *Routine*, *Habit* or *Improvement* (recurring tasks
  default to Routine). Reports show **Kind of work** and a **Recurring tasks** table.
- **Checklist** (one step per line) on any task or series: ☑ 1/3 on the row, right-click
  -> *Checklist...* to tick steps; when all are ticked the app offers to mark it done.
- Upcoming occurrences **reserve time**: the at-risk check and the 7-day workload count
  them, so a big deadline next to a daily routine is flagged early.

### Energy slots and Notion links (v1.2.1)

- **Energy slot** on each task: *High energy (Deep work) · Post-learning clarity (Create) ·
  Moderate energy (Network) · Low energy (Plan/Close)*, shown in the To-Do rows, the
  Timer's task line and the Tasks table.
- **Notion link** on each task: paste a Notion page link in the task form; open it with
  **Open**, or right-click a To-Do row → **Open in Notion**. Background notes stay in Notion.
- The app is the single task list; Notion keeps knowledge and reflection.

### Your own categories and types (v1.2)

**⚙ Settings → Categories & Types** has two editable lists:

- **Categories** (the kind of work) and **Types** (a broader split, e.g. Coding,
  Non-coding, Research): **add**, **rename**, change **colour** (8 chart-safe colours or a
  custom one), **delete** and reorder with **↑ ↓**. Each row shows how many tasks use it.
- Renaming updates every task. Deleting asks where its tasks should go
  (for categories, "No category" is also allowed). You always keep at least one type.
- The first type in the list is the default for new tasks.
- Reports show **Effort by type** for all your types, in their colours.
- Older databases are upgraded automatically when the app starts.

### Projects and the To-Do view (v1.1)

- **Projects**: group tasks by what they're for (Work, Study, Finance…). Create one
  with the **+** next to PROJECTS in the To-Do sidebar, or pick **+ New project…** in any
  project drop-down. Right-click a project to rename it, change its colour, or delete it
  (its tasks are kept).
- **Every place you add a task asks for its project**: the To-Do quick-add bar, the
  Timer's task box and the task form. It starts on the project you're viewing, or the
  one you used last. Changing the project in the Timer moves the current task.
- The window sizes itself to fit your screen, and the Timer tab scrolls if needed.
- **To-Do tab**, in the style of Focus To-Do:
  - Sidebar with **Today** (due today or overdue), **Tomorrow**, **This Week**,
    **Planned** (any due date), **Completed** and **Tasks** (all open), then your
    projects - each with its task count and estimated time left.
  - Totals for the list: **Estimated Time** (pomodoros left x focus length),
    **Tasks to be Completed**, **Elapsed Time** today and **Completed Tasks** today.
  - **Quick add**: type a task, click the tomatoes to set the estimate, press Enter.
    It lands in the list you're viewing (due today in Today, in the project in a project).
  - Each task: ○ tick to complete, ▶ to start a pomodoro, ●○ pomodoros done vs.
    estimated, priority flag, project, and the due date (red when due or overdue).
    Double-click to edit; right-click to move to a project, set the due date, or delete.
  - Smart lists are grouped by project. Sort by Focus Score, due date, priority,
    name or newest. "Completed today" is shown at the bottom. Search finds any task.
- Projects also appear in the task form, the Tasks table (column and filter) and
  Reports (**Effort by project**).

### Settings and convenience (Phase 5)

- **⚙ Settings** (top-right, or the tray menu):
  - *Timer*: focus/break length, long break (length and how often), auto-start
    breaks / next pomodoro, sound. Changes apply from the next block.
  - *Goals*: daily pomodoro goal and working days (used for at-risk deadlines).
  - *Focus Score*: the points for each priority and due date, and the at-risk bonus,
    with *Reset to defaults*.
  - *Shortcut*: a system-wide Start / Pause shortcut (default **Ctrl+Alt+P**) that
    works from any app.
- **⧉ Mini timer**: a small always-on-top timer showing time left and the task,
  with Start/Pause and a button back to the main window. Drag it anywhere; it
  remembers where you put it and whether it was open.
- Opening the app a second time just brings the running window forward.

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
Settings are changed in the app (⚙ Settings) and stored in the same file.

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
| `pomodoro/recurrence.py` | Repeat rules: daily / weekly / monthly dates - plain Python |
| `pomodoro/lists.py` | What each To-Do list contains, its totals, sorting, grouping |
| `pomodoro/ui/todo_tab.py` | The To-Do tab (sidebar, totals, quick add, task rows) |
| `pomodoro/ui/history_strip.py` | Day-by-day strip for a recurring task |
| `pomodoro/goals.py` | Goals, control panel, time split, learned estimates - plain Python |
| `pomodoro/ui/goals_tab.py` | The Goals tab |
| `pomodoro/planning.py` | Day plan, capacity, day summary, weekly three-generation report |
| `pomodoro/ui/today_tab.py` | The Today tab, Plan my day, Close the day |
| `pomodoro/ui/review_tab.py` | Weekly review |
| `pomodoro/USER_GUIDE.md`, `pomodoro/ui/help_dialog.py` | The in-app guide |
| `pomodoro/growth.py` | Best hours, stretch mix, practice, Then vs Now - plain Python |
| `pomodoro/ui/growth_tab.py`, `pomodoro/ui/prompt_bar.py` | Growth report; one-click bottom bar |
| `pomodoro/ui/settings_dialog.py` | The Settings window |
| `pomodoro/notion.py`, `pomodoro/ui/notion_ui.py` | Optional Notion connection (Journal, weekly page) |
| `pomodoro/secret_store.py` | Encrypts the Notion secret (Windows DPAPI) |
| `setup.ps1`, `create_shortcuts.ps1` | Install on a PC from source; shortcuts |
| `pomodoro/ui/list_editor.py` | Editable lists for categories and types |
| `pomodoro/ui/mini_window.py` | The always-on-top mini timer |
| `pomodoro/hotkey.py` | System-wide keyboard shortcut (Windows) |
| `build.py`, `installer/PomodoroTracker.iss` | Build the .exe and the installer |
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
5. ~~Polish: settings screen, mini window, global hotkey, installer~~ (done)

Possible next steps: calendar view of due dates, editing past sessions, dark mode.

## License

[MIT](LICENSE) - free to use, change and share; keep the copyright notice.
