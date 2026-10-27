"""The execution side of growth, measured from your own pomodoros (reflection lives in Notion).

  * Best hours   - when you finish the most pomodoros with the fewest distractions
  * Stretch mix  - how finished tasks felt: comfort / stretch / panic
  * Practice     - deliberate-practice pomodoros per skill, and how hard they felt
  * Then vs Now  - the last 30 days against the 30 before: evidence that you grow
"""

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pomodoro.database import Database
from pomodoro.models import STRETCH

MIN_FOR_BEST_HOURS = 15      # pomodoros needed before best hours are meaningful


# ---------- best hours ----------

@dataclass
class HourStats:
    hour: int
    started: int          # focus blocks logged (full or partial)
    completed: int
    distractions: int

    @property
    def rate(self) -> float:
        return self.completed / self.started if self.started else 0.0

    @property
    def score(self) -> float:
        """Many finished pomodoros, few abandoned ones, few distractions."""
        return self.completed * self.rate - 0.5 * self.distractions


@dataclass
class BestHours:
    hours: list[HourStats]
    peak: list[int]       # e.g. [9, 10]  -> "9–11"
    low: list[int]
    total: int            # completed pomodoros analysed

    @property
    def enough_data(self) -> bool:
        return self.total >= MIN_FOR_BEST_HOURS and bool(self.peak)


def hour_label(hours: list[int]) -> str:
    return f"{hours[0]}–{hours[-1] + 1}" if hours else "–"


def best_hours(db: Database, today: date | None = None, days: int = 60) -> BestHours:
    today = today or date.today()
    since = (today - timedelta(days=days - 1)).isoformat()
    stats: dict[int, HourStats] = {}
    for start, completed in db.conn.execute(
            "SELECT start_time, completed FROM sessions WHERE kind = 'focus' AND start_time >= ?",
            (since,)):
        hour = int(start[11:13])
        entry = stats.setdefault(hour, HourStats(hour, 0, 0, 0))
        entry.started += 1
        entry.completed += completed
    for (happened,) in db.conn.execute(
            "SELECT happened_at FROM anomalies WHERE kind = 'distraction' AND happened_at >= ?",
            (since,)):
        hour = int(happened[11:13])
        stats.setdefault(hour, HourStats(hour, 0, 0, 0)).distractions += 1
    hours = [stats[h] for h in sorted(stats)]
    total = sum(h.completed for h in hours)

    # Peak: the best two neighbouring hours. Low: the weakest hour with real use.
    peak, best = [], None
    for h in hours:
        nxt = stats.get(h.hour + 1)
        score = h.score + (nxt.score if nxt else 0)
        if h.started >= 2 and (best is None or score > best):
            best, peak = score, [h.hour] + ([h.hour + 1] if nxt and nxt.started else [])
    used = [h for h in hours if h.started >= 2 and h.hour not in peak]
    low = [min(used, key=lambda h: (h.rate, -h.distractions, h.completed)).hour] if used else []
    return BestHours(hours, peak, low, total)


def energy_now(db: Database, now: datetime | None = None) -> str | None:
    """'deep' during your peak hours, 'plan' during your weakest hour, else None."""
    now = now or datetime.now()
    hours = best_hours(db, now.date())
    if not hours.enough_data:
        return None
    if now.hour in hours.peak:
        return "deep"
    if now.hour in hours.low:
        return "plan"
    return None


# ---------- stretch mix ----------

def stretch_mix(db: Database, start: date, end: date) -> tuple[dict[str, int], int, str]:
    """(count per rating, unrated finished tasks, advice) for tasks finished in the period."""
    rows = db.conn.execute(
        "SELECT stretch FROM tasks WHERE status = 'done' AND substr(completed_at, 1, 10) >= ? "
        "AND substr(completed_at, 1, 10) <= ?", (start.isoformat(), end.isoformat())).fetchall()
    counts = {key: sum(1 for r in rows if r[0] == key) for key in STRETCH}
    unrated = sum(1 for r in rows if r[0] is None)
    rated = sum(counts.values())
    if rated < 3:
        advice = "Rate a few finished tasks to see your mix (aim for about 30% stretch)."
    elif counts["panic"] / rated > 0.2:
        advice = "Lots of panic: break big tasks into smaller steps, or ask for help earlier."
    elif counts["stretch"] / rated < 0.2:
        advice = "Mostly comfort: take on something a little harder - that's where you grow."
    else:
        advice = "Good balance - you're working at the edge of your ability."
    return counts, unrated, advice


# ---------- practice ----------

@dataclass
class PracticeRow:
    skill: str
    sessions: int
    minutes: float
    first_difficulty: float | None    # average of the earlier half
    recent_difficulty: float | None   # average of the later half
    last_target: str | None


def practice_summary(db: Database, start: date, end: date) -> list[PracticeRow]:
    rows = db.conn.execute(
        "SELECT practice_skill, practice_target, duration_min, difficulty FROM sessions "
        "WHERE practice_skill IS NOT NULL AND substr(start_time, 1, 10) >= ? "
        "AND substr(start_time, 1, 10) <= ? ORDER BY start_time",
        (start.isoformat(), end.isoformat())).fetchall()
    by_skill: dict[str, list] = {}
    for row in rows:
        by_skill.setdefault(row[0], []).append(row)
    result = []
    for skill, items in sorted(by_skill.items(), key=lambda kv: -len(kv[1])):
        rated = [r[3] for r in items if r[3]]
        half = len(rated) // 2
        first = statistics.mean(rated[:half]) if half else None
        recent = statistics.mean(rated[half:]) if rated else None
        result.append(PracticeRow(skill, len(items), sum(r[2] for r in items), first, recent,
                                  items[-1][1]))
    return result


# ---------- then vs now ----------

@dataclass
class Comparison:
    name: str
    then: str
    now: str
    better: bool | None      # True = improved, False = got worse, None = no verdict


def _window_stats(db: Database, start: date, end: date) -> dict:
    a, b = start.isoformat(), end.isoformat()
    working = db.get_working_days()
    days = sum(1 for n in range((end - start).days + 1)
               if (start + timedelta(days=n)).weekday() in working) or 1
    sessions = db.conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(completed), 0) FROM sessions WHERE kind = 'focus' "
        "AND substr(start_time, 1, 10) BETWEEN ? AND ?", (a, b)).fetchone()
    distractions = db.conn.execute(
        "SELECT COUNT(*) FROM anomalies WHERE kind = 'distraction' "
        "AND substr(happened_at, 1, 10) BETWEEN ? AND ?", (a, b)).fetchone()[0]
    finished = [t for t in db.list_tasks("done")
                if a <= (t["completed_at"] or "")[:10] <= b and not t["recurrence_id"]]
    estimated = [t for t in finished if t["estimate_pomodoros"]]
    dated = [t for t in finished if t["due_date"]]
    habits = db.conn.execute(
        "SELECT SUM(status = 'done'), SUM(status IN ('done', 'missed')) FROM tasks "
        "WHERE nature = 'habit' AND recurrence_id IS NOT NULL "
        "AND occurrence_date BETWEEN ? AND ?", (a, b)).fetchone()
    per_category: dict[str, list[int]] = {}
    for task in finished:
        if task["category"] and task["pomodoros"] > 0:
            per_category.setdefault(task["category"], []).append(task["pomodoros"])
    return {
        "per_day": sessions[1] / days,
        "completion": sessions[1] / sessions[0] if sessions[0] else None,
        "distraction": distractions / sessions[1] if sessions[1] else None,
        "accuracy": (sum(1 for t in estimated
                         if abs(t["pomodoros"] - t["estimate_pomodoros"])
                         <= max(1, 0.25 * t["estimate_pomodoros"])) / len(estimated)
                     if estimated else None),
        "on_time": (sum(1 for t in dated if t["completed_at"][:10] <= t["due_date"][:10])
                    / len(dated) if dated else None),
        "habits": (habits[0] or 0) / habits[1] if habits[1] else None,
        "per_category": per_category,
    }


def then_vs_now(db: Database, today: date | None = None, days: int = 30) -> list[Comparison]:
    today = today or date.today()
    now = _window_stats(db, today - timedelta(days=days - 1), today)
    then = _window_stats(db, today - timedelta(days=2 * days - 1), today - timedelta(days=days))

    def pct(value):
        return "–" if value is None else f"{value:.0%}"

    def verdict(old, new, higher_is_better=True):
        if old is None or new is None or abs(new - old) < 1e-9:
            return None
        return (new > old) == higher_is_better

    rows = [
        Comparison("Pomodoros per working day", f"{then['per_day']:.1f}", f"{now['per_day']:.1f}",
                   verdict(then["per_day"], now["per_day"]) if then["per_day"] else None),
        Comparison("Pomodoros finished (not abandoned)", pct(then["completion"]),
                   pct(now["completion"]), verdict(then["completion"], now["completion"])),
        Comparison("Distractions per pomodoro",
                   "–" if then["distraction"] is None else f"{then['distraction']:.1f}",
                   "–" if now["distraction"] is None else f"{now['distraction']:.1f}",
                   verdict(then["distraction"], now["distraction"], higher_is_better=False)),
        Comparison("Estimate accuracy", pct(then["accuracy"]), pct(now["accuracy"]),
                   verdict(then["accuracy"], now["accuracy"])),
        Comparison("Finished on time", pct(then["on_time"]), pct(now["on_time"]),
                   verdict(then["on_time"], now["on_time"])),
        Comparison("Habit consistency", pct(then["habits"]), pct(now["habits"]),
                   verdict(then["habits"], now["habits"])),
    ]
    for category in sorted(set(then["per_category"]) & set(now["per_category"])):
        old = statistics.median(then["per_category"][category])
        new = statistics.median(now["per_category"][category])
        rows.append(Comparison(f"🍅 per {category} task (median)", f"{old:g}", f"{new:g}",
                               verdict(old, new, higher_is_better=False)))
    return rows
