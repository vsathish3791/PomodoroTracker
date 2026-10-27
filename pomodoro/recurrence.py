"""Date rules for recurring tasks (plain Python, no database or UI).

A series repeats daily, weekly or monthly from its start date until its end date:
  * daily   - every day, or only on your working days
  * weekly  - on chosen weekdays (0 = Monday ... 6 = Sunday)
  * monthly - on a day of the month; 29-31 fall back to the month's last day
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

FREQUENCIES = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class Schedule:
    frequency: str                      # 'daily' | 'weekly' | 'monthly'
    start: date
    end: date
    workdays_only: bool = True          # daily only
    weekdays: list[int] = field(default_factory=list)   # weekly only
    month_day: int | None = None        # monthly only (defaults to the start's day)

    def __post_init__(self):
        if self.frequency not in FREQUENCIES:
            raise ValueError(f"Frequency must be one of {list(FREQUENCIES)}")
        if self.end < self.start:
            raise ValueError("The end date must be on or after the start date")
        if self.frequency == "weekly" and not self.weekdays:
            self.weekdays = [self.start.weekday()]
        if self.frequency == "monthly" and not self.month_day:
            self.month_day = self.start.day

    def matches(self, day: date, working_days: set[int]) -> bool:
        """Is there an occurrence on this day?"""
        if not self.start <= day <= self.end:
            return False
        if self.frequency == "daily":
            return not self.workdays_only or day.weekday() in working_days
        if self.frequency == "weekly":
            return day.weekday() in self.weekdays
        last = calendar.monthrange(day.year, day.month)[1]
        return day.day == min(self.month_day, last)

    def dates(self, first: date, last: date, working_days: set[int]) -> list[date]:
        """All occurrence dates between first and last (inclusive)."""
        first, last = max(first, self.start), min(last, self.end)
        days, day = [], first
        while day <= last:
            if self.matches(day, working_days):
                days.append(day)
            day += timedelta(days=1)
        return days

    def count(self, working_days: set[int]) -> int:
        return len(self.dates(self.start, self.end, working_days))

    def next_date(self, after: date, working_days: set[int]) -> date | None:
        """The first occurrence strictly after `after`, if any."""
        day = max(after + timedelta(days=1), self.start)
        while day <= self.end:
            if self.matches(day, working_days):
                return day
            day += timedelta(days=1)
        return None

    def describe(self) -> str:
        """e.g. 'Every working day until 15 Nov', 'Weekly on Mon, Thu until 31 Dec 2026'."""
        until = f"until {short_date(self.end)}"
        if self.frequency == "daily":
            what = "Every working day" if self.workdays_only else "Every day"
        elif self.frequency == "weekly":
            what = "Weekly on " + ", ".join(DAY_NAMES[d] for d in sorted(self.weekdays))
        else:
            suffix = "last day" if self.month_day >= 31 else ordinal(self.month_day)
            what = f"Monthly on the {suffix}"
        return f"{what} {until}"


def short_date(day: date, today: date | None = None) -> str:
    today = today or date.today()
    return day.strftime("%d %b") if day.year == today.year else day.strftime("%d %b %Y")


def ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def schedule_from_row(row: dict) -> Schedule:
    """Build a Schedule from a `recurrences` database row."""
    weekdays = [int(d) for d in (row.get("weekdays") or "").split(",") if d.strip()]
    return Schedule(row["frequency"], date.fromisoformat(row["start_date"]),
                    date.fromisoformat(row["end_date"]), bool(row.get("workdays_only", 1)),
                    weekdays, row.get("month_day"))
