"""기간 계산 — '이번 달' = KST 당월 1일 00:00 ~ 어제 EOD.

scope (사용자 조정 #3):
- period_start = 당월 1일 (KST)
- period_end = 어제 (KST) — 어제 EOD 종가까지 반영
- 단 어제가 당월 1일 이전(=오늘이 1일)이면 period_start = 전월 1일, end = 전월 말일
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Tuple

from ..config import get_settings


def _kst_now() -> datetime:
    s = get_settings()
    return datetime.now(timezone.utc) + timedelta(hours=s.period_kst_offset_hours)


def kst_today() -> date:
    return _kst_now().date()


def current_month_window(today: date | None = None) -> Tuple[date, date]:
    """이번 달 (KST 기준) 시작일과 종료일을 반환.

    - 오늘이 2일 이상 → (당월 1일, 어제)
    - 오늘이 1일 → 직전 달 전체 (1일 ~ 말일)
    """
    t = today or kst_today()
    if t.day == 1:
        # 어제가 전월 말일
        end = t - timedelta(days=1)
        start = end.replace(day=1)
        return start, end
    return t.replace(day=1), t - timedelta(days=1)
