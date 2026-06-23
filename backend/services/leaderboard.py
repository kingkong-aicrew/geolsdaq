"""leaderboard — stash 행을 sort/ticker 로 필터.

scope (사용자 조정 #2):
- ticker 쿼리 파라미터로 종목별 랭킹 가능
"""
from __future__ import annotations

from typing import Optional

from ..config import get_settings
from ..models.schemas import LeaderboardEntry, LeaderboardResponse
from ..repositories.stash import StashRepository


class Leaderboard:
    def __init__(self, stash: StashRepository):
        self.stash = stash

    async def fetch(
        self,
        *,
        sort: str = "amount",     # "amount" | "pct"
        period: str = "month",
        ticker: Optional[str] = None,
        limit: int = 50,
    ) -> LeaderboardResponse:
        if sort not in ("amount", "pct"):
            raise ValueError("sort 는 amount 또는 pct")
        if period not in ("month",):
            raise ValueError("period 는 month 만 지원 (Phase A)")

        ticker_upper = ticker.strip().upper() if ticker else None

        rows = await self.stash.leaderboard(
            sort=sort, ticker=ticker_upper, limit=limit
        )

        entries = [
            LeaderboardEntry(
                id=r.id,
                created_at=r.created_at,
                ticker=r.ticker,
                name=r.name,
                qty=r.qty,
                buy_date=r.buy_date,
                profit_amount=r.profit_amount,
                profit_pct=r.profit_pct,
            )
            for r in rows
        ]

        s = get_settings()
        return LeaderboardResponse(
            sort=sort,
            period=period,
            ticker=ticker_upper,
            entries=entries,
            disclaimer=s.disclaimer,
        )
