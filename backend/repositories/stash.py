"""stash 테이블 CRUD."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from .supabase_client import SupabaseRest


@dataclass
class StashRow:
    id: str
    created_at: datetime
    ticker: str
    name: str
    qty: int
    buy_date: date
    profit_amount: float
    profit_pct: float
    period_start: date
    period_end: date
    calc_snapshot: Dict[str, Any]


def _parse_row(r: Dict[str, Any]) -> StashRow:
    return StashRow(
        id=r["id"],
        created_at=datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")),
        ticker=r["ticker"],
        name=r["name"],
        qty=int(r["qty"]),
        buy_date=date.fromisoformat(r["buy_date"]),
        profit_amount=float(r["profit_amount"]),
        profit_pct=float(r["profit_pct"]),
        period_start=date.fromisoformat(r["period_start"]),
        period_end=date.fromisoformat(r["period_end"]),
        calc_snapshot=r.get("calc_snapshot") or {},
    )


class StashRepository:
    """Phase A 는 anon insert 허용. 서버 측 검증 후 호출."""

    def __init__(self, client: Optional[SupabaseRest] = None, *, use_service_role: bool = False):
        # 본 사이클에서는 anon 으로도 INSERT 가능 (RLS WITH CHECK 통과)
        self.cli = client or SupabaseRest(use_service_role=use_service_role)

    async def insert(self, payload: Dict[str, Any]) -> StashRow:
        rows = await self.cli.insert("stash", [payload])
        if not rows:
            raise RuntimeError("stash insert 실패 (응답 비어있음)")
        return _parse_row(rows[0])

    async def get(self, stash_id: str) -> Optional[StashRow]:
        rows = await self.cli.select(
            "stash",
            params={"id": f"eq.{stash_id}", "limit": "1"},
        )
        if not rows:
            return None
        return _parse_row(rows[0])

    async def leaderboard(
        self,
        *,
        sort: str,                  # "amount" | "pct"
        ticker: Optional[str],
        limit: int = 50,
    ) -> List[StashRow]:
        order_col = "profit_amount.desc" if sort == "amount" else "profit_pct.desc"
        params = {
            "order": order_col,
            "limit": str(limit),
            "select": "id,created_at,ticker,name,qty,buy_date,profit_amount,profit_pct,period_start,period_end,calc_snapshot",
        }
        if ticker:
            params["ticker"] = f"eq.{ticker}"
        rows = await self.cli.select("stash", params=params)
        return [_parse_row(r) for r in rows]
