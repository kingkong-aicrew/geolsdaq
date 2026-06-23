"""index_prices / index_breadth 조회 (지수착시 엔진).

규칙 (prices.py 패턴 답습):
- anon SELECT 만(RLS 읽기 전용). 적재는 배치(service_role).
- 최신 집계일(latest)은 market 의 max(date) 행 1건.
- series 는 최근 N일을 날짜 오름차순으로(스파크라인용).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from .supabase_client import SupabaseRest

_BREADTH_SELECT = (
    "market,date,index_change_pct,total_count,up_count,down_count,"
    "flat_count,up_ratio,median_change_pct,illusion_gap"
)


@dataclass
class BreadthRow:
    market: str
    date: date
    index_change_pct: float
    total_count: int
    up_count: int
    down_count: int
    flat_count: int
    up_ratio: float
    median_change_pct: float
    illusion_gap: float


def _parse(r: dict) -> BreadthRow:
    return BreadthRow(
        market=r["market"],
        date=date.fromisoformat(r["date"]),
        index_change_pct=float(r["index_change_pct"]),
        total_count=int(r["total_count"]),
        up_count=int(r["up_count"]),
        down_count=int(r["down_count"]),
        flat_count=int(r["flat_count"]),
        up_ratio=float(r["up_ratio"]),
        median_change_pct=float(r["median_change_pct"]),
        illusion_gap=float(r["illusion_gap"]),
    )


class IndexRepository:
    """index_breadth 조회 — 최신/특정일/시계열."""

    def __init__(self, client: Optional[SupabaseRest] = None):
        self.cli = client or SupabaseRest(use_service_role=False)

    async def get_latest_breadth(self, market: str) -> Optional[BreadthRow]:
        """가장 최근 집계일 1건."""
        rows = await self.cli.select(
            "index_breadth",
            params={
                "market": f"eq.{market}",
                "order": "date.desc",
                "limit": "1",
                "select": _BREADTH_SELECT,
            },
        )
        return _parse(rows[0]) if rows else None

    async def get_breadth_on(
        self, market: str, target: date
    ) -> Optional[BreadthRow]:
        """특정일 1건(정확히 그 날짜. 휴장일이면 없음 → None)."""
        rows = await self.cli.select(
            "index_breadth",
            params={
                "market": f"eq.{market}",
                "date": f"eq.{target.isoformat()}",
                "limit": "1",
                "select": _BREADTH_SELECT,
            },
        )
        return _parse(rows[0]) if rows else None

    async def get_breadth_series(
        self, market: str, days: int
    ) -> List[BreadthRow]:
        """최근 N일 시계열(날짜 오름차순). 스파크라인용.

        DB 에서 date.desc 로 N개 받고 파이썬에서 뒤집어 오름차순화
        (PostgREST 는 limit 와 desc 조합이 최신 N개를 보장).
        """
        rows = await self.cli.select(
            "index_breadth",
            params={
                "market": f"eq.{market}",
                "order": "date.desc",
                "limit": str(days),
                "select": _BREADTH_SELECT,
            },
        )
        parsed = [_parse(r) for r in rows]
        parsed.sort(key=lambda b: b.date)  # 오름차순
        return parsed
