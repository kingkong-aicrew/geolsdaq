"""기간 계산 단위 테스트."""
from __future__ import annotations

from datetime import date

from ..services.period import current_month_window


def test_midmonth_returns_first_to_yesterday():
    s, e = current_month_window(today=date(2026, 5, 27))
    assert s == date(2026, 5, 1)
    assert e == date(2026, 5, 26)


def test_first_day_returns_previous_month():
    s, e = current_month_window(today=date(2026, 5, 1))
    assert s == date(2026, 4, 1)
    assert e == date(2026, 4, 30)


def test_first_day_of_january_returns_december():
    s, e = current_month_window(today=date(2026, 1, 1))
    assert s == date(2025, 12, 1)
    assert e == date(2025, 12, 31)


def test_last_day_of_month():
    s, e = current_month_window(today=date(2026, 5, 31))
    assert s == date(2026, 5, 1)
    assert e == date(2026, 5, 30)
