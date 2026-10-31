from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

ONE_DAY = timedelta(days=1)
MAX_DAYS = 365


def month_end(day: date) -> date:
    return (day.replace(day=1) + timedelta(days=32)).replace(day=1) - ONE_DAY


def max_window_end(day: date) -> date:
    return day + timedelta(days=MAX_DAYS - 1)


@dataclass(frozen=True)
class Period:
    since: date
    until: date

    @property
    def is_single_day(self) -> bool:
        return self.since == self.until

    def halves(self) -> tuple[Period, Period]:
        middle = self.since + (self.until - self.since) // 2
        return Period(self.since, middle), Period(middle + ONE_DAY, self.until)

    def monthly(self) -> list[Period]:
        return self._split(month_end)

    def yearly(self) -> list[Period]:
        return self._split(max_window_end)

    def contains(self, day: date) -> bool:
        return self.since <= day <= self.until

    def _split(self, window_end: Callable[[date], date]) -> list[Period]:
        windows = []
        start = self.since
        while start <= self.until:
            end = min(window_end(start), self.until)
            windows.append(Period(start, end))
            start = end + ONE_DAY
        return windows
