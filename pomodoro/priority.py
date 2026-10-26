"""Decides what you should work on next.

Every open task gets a Focus Score:

    Focus Score = priority weight + urgency weight + risk bonus

  * priority weight - how important the task is (P1 Critical ... P4 Low)
  * urgency weight  - how close the due date is
  * risk bonus      - added when the work left can't fit before the due date

"At risk" works like a real calendar: tasks are lined up by due date
(earliest first), and for each due date we check whether all the pomodoros
still needed up to that date fit into your daily goal on the working days
left. Tasks without an estimate can't be checked, so they never count as at risk.

This module is plain Python (no Qt, no database) so it is easy to test.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from pomodoro.models import DEFAULT_PRIORITY, PRIORITIES, due_label

PRIORITY_WEIGHTS = {1: 40, 2: 25, 3: 10, 4: 0}
RISK_BONUS = 20


def urgency_weight(due: date | None, today: date) -> int:
    if due is None:
        return 0
    days = (due - today).days
    if days < 0:
        return 50     # overdue
    if days == 0:
        return 40     # due today
    if days == 1:
        return 30     # tomorrow
    if days <= 3:
        return 20
    if days <= 7:
        return 10
    return 0


@dataclass
class ScoredTask:
    task: dict
    score: int
    remaining: int | None          # pomodoros still to do (None = no estimate)
    at_risk: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def id(self) -> int:
        return self.task["id"]

    @property
    def title(self) -> str:
        return self.task["title"]

    @property
    def due(self) -> date | None:
        return _due_date(self.task)

    def is_urgent(self, today: date) -> bool:
        """Urgent enough to interrupt you about: overdue, due today, P1 or at risk."""
        due = self.due
        return (self.task["priority"] == 1 or self.at_risk
                or (due is not None and due <= today))

    def short_reason(self) -> str:
        """e.g. 'P1 Critical, due today, 3 🍅 left'."""
        return ", ".join(self.reasons)


def _due_date(task: dict) -> date | None:
    return date.fromisoformat(task["due_date"][:10]) if task.get("due_date") else None


def remaining_pomodoros(task: dict) -> int | None:
    if not task.get("estimate_pomodoros"):
        return None
    return max(task["estimate_pomodoros"] - task.get("pomodoros", 0), 0)


def capacity_until(due: date, today: date, daily_goal: int, done_today: int,
                   working_days: set[int]) -> int:
    """Pomodoros you can still do from now until the end of `due`.

    Today always counts (you're working now), with whatever is left of today's goal.
    Later days count only if they're working days (0 = Monday ... 6 = Sunday).
    """
    if due < today:
        return 0
    total = max(daily_goal - done_today, 0)
    day = today + timedelta(days=1)
    while day <= due:
        if day.weekday() in working_days:
            total += daily_goal
        day += timedelta(days=1)
    return total


def find_at_risk(tasks: list[dict], today: date, daily_goal: int, done_today: int,
                 working_days: set[int]) -> set[int]:
    """Ids of tasks (due today or later) whose deadline can't be met at your daily goal."""
    # Overdue work is still owed and should be done first, so it uses up capacity too.
    dated = sorted((t for t in tasks if _due_date(t)), key=_due_date)
    at_risk, needed = set(), 0
    for due in sorted({_due_date(t) for t in dated}):
        same_day = [t for t in dated if _due_date(t) == due]
        needed += sum(remaining_pomodoros(t) or 0 for t in same_day)
        if due < today:
            continue
        if needed > capacity_until(due, today, daily_goal, done_today, working_days):
            at_risk.update(t["id"] for t in same_day if remaining_pomodoros(t))
    return at_risk


def rank_tasks(tasks: list[dict], today: date | None = None, daily_goal: int = 8,
               done_today: int = 0, working_days: set[int] | None = None) -> list[ScoredTask]:
    """Score and sort tasks, best next task first. Done and On Hold tasks are left out.

    `tasks` are dicts as returned by Database.list_tasks (with a 'pomodoros' total).
    """
    today = today or date.today()
    working_days = {0, 1, 2, 3, 4} if working_days is None else working_days
    open_tasks = [t for t in tasks if t["status"] not in ("done", "on_hold")]
    risky = find_at_risk(open_tasks, today, daily_goal, done_today, working_days)

    scored = []
    for task in open_tasks:
        due = _due_date(task)
        at_risk = task["id"] in risky
        remaining = remaining_pomodoros(task)
        score = (PRIORITY_WEIGHTS[task["priority"]] + urgency_weight(due, today)
                 + (RISK_BONUS if at_risk else 0))

        reasons = [PRIORITIES[task["priority"]]]
        if due is not None:
            label = due_label(task["due_date"], today)
            reasons.append(label.lower() if label.startswith("Overdue")
                           else "due " + (label.lower() if label in ("Today", "Tomorrow")
                                          else label))
        if remaining is not None:
            reasons.append(f"{remaining} 🍅 left")
        if at_risk:
            reasons.append("at risk")
        scored.append(ScoredTask(task, score, remaining, at_risk, reasons))

    scored.sort(key=lambda s: (
        -s.score,
        s.due or date.max,                                   # earlier deadline first
        s.remaining if s.remaining is not None else 10**6,   # then quicker to finish
        s.id,
    ))
    return scored


def should_warn(chosen_id: int | None, ranked: list[ScoredTask], today: date | None = None
                ) -> ScoredTask | None:
    """The task to warn about if you're starting something less important, else None.

    Warns only when the top task is urgent and scores higher than the chosen one.
    chosen_id is None for a brand-new task, which will get the default priority.
    """
    today = today or date.today()
    if not ranked or ranked[0].id == chosen_id:
        return None
    top = ranked[0]
    chosen = next((s for s in ranked if s.id == chosen_id), None)
    chosen_score = chosen.score if chosen else PRIORITY_WEIGHTS[DEFAULT_PRIORITY]
    if top.is_urgent(today) and top.score > chosen_score:
        return top
    return None


def day_summary(ranked: list[ScoredTask], today: date, daily_goal: int, done_today: int) -> str:
    """One line, e.g. '2 overdue · 3 due today · 1 at risk · 9 🍅 needed today, 6 left in goal'."""
    overdue = [s for s in ranked if s.due and s.due < today]
    due_today = [s for s in ranked if s.due == today]
    at_risk = [s for s in ranked if s.at_risk]
    parts = []
    if overdue:
        parts.append(f"{len(overdue)} overdue")
    if due_today:
        parts.append(f"{len(due_today)} due today")
    if at_risk:
        parts.append(f"{len(at_risk)} at risk")
    needed = sum(s.remaining or 0 for s in overdue + due_today)
    if needed:
        left = max(daily_goal - done_today, 0)
        parts.append(f"{needed} 🍅 needed today, {left} left in your goal")
    return "  ·  ".join(parts) if parts else "Nothing urgent today. 👍"
