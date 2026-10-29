# Pomodoro Tracker – quick guide

Plan your day, focus in 25-minute **pomodoros**, and see where your effort goes.
The app is for **planning and execution**; keep notes, learnings and reflections in your
journal. Everything works on its own – **Notion is optional** (⚙ Settings → Notion).

## The tabs

| Tab | What it's for |
|---|---|
| **Timer** | Pick a task (and its project), press **Start**. 25 min focus → 5 min break. |
| **Today** | Your day on one page: routines & habits, today's focus tasks, capacity, goals. |
| **To-Do** | All tasks. **☰ List** (Today, Tomorrow, This Week, Planned, Recurring, Completed, projects) or **▦ Table**. |
| **Goals** | Control panel, goals, time split and your running total. |
| **Reports** | **Effort** charts, **Deadlines** board, **Weekly review** and **Growth**. |

Top right: **⧉ Mini timer** (small always-on-top window), **⚙ Settings**, **? Help**.

## A typical day

1. **Morning – Today → ☀ Plan my day…** Tick the few tasks you'll focus on. The app shows
   whether they fit your daily goal after routines and habits.
2. **Work – Timer.** Start a pomodoro on the suggested task. **Focus Next** shows, in
   this order: your *Today's focus*, daily tasks, weekly/monthly tasks whose day is today,
   one-off tasks due today, then overdue one-off tasks. The project box next to the task
   filters the task list (it never moves a task – do that in To-Do). Stopped early? Pick a reason in one click. Distracted? Click
   **⚡ I got distracted** – the timer keeps going.
3. **Evening – Today → ☾ Close the day…** See today's numbers, move unfinished tasks to
   tomorrow, plan tomorrow, and **Copy day log** – the day's facts for your journal
   (tasks done and worked on, focus, interruptions, and an **Energy signal**: High,
   Steady, Low or Rest day). With Notion on: **Send day log** puts them in your Notion
   Day Log, where your Notion AI journaling assistant helps you write the entry.
4. **Weekly – Reports → Weekly review.** Planned → Done & results → Problems & next
   actions. **Copy** or **Save as…** (with Notion on: **Send to Notion**).

## Tasks

- **Add**: type in **To-Do**'s quick-add bar (pick a project and an estimate with the
  tomatoes) and press Enter, or double-click any task to open the full form.
- **Fields**: project, **kind of work** (Routine – keeps things running; Habit – small
  repeated action for your growth; Improvement – one-off work that moves things forward),
  category, type, priority, energy slot, due date, estimate (🍅), checklist, notes,
  Notion link. The form suggests an estimate from similar finished tasks.
- **Right-click** a task: start, mark done, move to a project, set the due date, open in
  Notion, checklist, delete.
- **Focus Score** ranks tasks by priority, due date and risk; the app warns if you start
  something less important while an urgent task is waiting.

## Recurring tasks and habits

- In the task form set **Repeat** to Daily / Weekly / Monthly and a **Repeat until** date.
  Each day's occurrence appears on its day; one left open when the next appears becomes
  **Missed**.
- For habits add a **Cue** (time + place, with a reminder), **Stack** it after another
  habit, and give a **2-minute version** – on hard days right-click → **Showed up** keeps
  your streak.
- **To-Do → Recurring** shows each series with a day-by-day strip (✓ done, ½ showed up,
  ✗ missed) and your 🔥 streak. Missed last time? It's boosted: *never miss twice*.

## Goals and reports

- **Goals tab**: *Weekly rhythm* goals (e.g. Learning AI ≥ 10 🍅 a week) and *Target by a
  date* goals (with a forecast); control panel tiles show ● On track / ▲ Behind /
  ■ Off track; set your Routine / Habit / Improvement **time split**.
- **Reports → Effort**: by category, project, kind, priority, daily trend, recurring
  tasks, estimate vs actual, and **Interruptions & misses** (a Pareto of causes – fix the
  red ones first). Export CSV.
- **Reports → Deadlines**: tasks by due date and a 7-day workload check.

## Growth

- **Rate finished tasks** – a bar at the bottom asks *😌 Comfort · 💪 Stretch · 😰 Panic*
  (one click, or Skip). Aim for about 30% stretch.
- **🎯 Practice** (on the Timer) – name a skill and one narrow target; after the pomodoro,
  rate how hard it was (1–5). Falling difficulty means you're improving.
- **Reports → Growth** – *Then vs Now* (last 30 days vs the 30 before), your **best
  hours** (Focus Next then favours ⚡ Deep-work tasks in your peak hours), your stretch
  mix, and practice per skill.

## Settings and shortcuts

- **⚙ Settings**: timer lengths, daily goal, working days, categories & types, Focus Score
  points, and the global **Start/Pause shortcut** (default **Ctrl+Alt+P**, works from any
  app).
- **⚙ Settings -> Notion** (optional, off for new users): tick **Use Notion**, then connect
  once so the Send buttons work; **Create…** makes your Day Log database next to your
  Journal. Energy signal limits are in **⚙ Settings -> Goals**. Create an
  internal integration at notion.so/profile/integrations, paste its secret, add the
  integration to your Journal database and weekly-reviews page (••• -> Connections),
  paste their links and press **Test**. The app only sends numbers; it never changes
  what you wrote.
- Closing the window keeps the app running in the tray (right-click the tomato to quit).
- Your data is stored in `%APPDATA%\PomodoroTracker\pomodoro.db` – on your PC only.
