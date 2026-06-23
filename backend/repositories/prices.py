"""prices / fx 조회.

규칙:
- 종가는 KRW 환산값으로 외부에 노출. 환산은 서비스 계층에서 처리.
- 휴장일 대응: 요청한 date 이전의 가장 가까운 거래일 종가 사용.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from .supabase_client import SupabaseRest


@dataclass
class PriceRow:
    ticker: str
    name: str
    market: str           # "KR" | "US"
    date: date
    close: float          # 원시 통화 (KR=KRW, US=USD)


@dataclass
class FxRow:
    date: date
    usd_krw: float


class PriceRepository:
    """Supabase prices/fx 테이블 조회."""

    def __init__(self, client: Optional[SupabaseRest] = None):
        self.cli = client or SupabaseRest(use_service_role=False)

    async def get_close_on_or_before(
        self, ticker: str, target_date: date
    ) -> Optional[PriceRow]:
        """target_date 포함 그 이전 가장 가까운 거래일 종가.

        휴장일(주말·공휴일)이면 자동으로 가장 가까운 평일 종가를 반환.
        """
        rows = await self.cli.select(
            "prices",
            params={
                "ticker": f"eq.{ticker}",
                "date": f"lte.{target_date.isoformat()}",
                "order": "date.desc",
                "limit": "1",
                "select": "ticker,name,market,date,close",
            },
        )
        if not rows:
            return None
        r = rows[0]
        return PriceRow(
            ticker=r["ticker"],
            name=r["name"],
            market=r["market"],
            date=date.fromisoformat(r["date"]),
            close=float(r["close"]),
        )

    async def get_fx_on_or_before(self, target_date: date) -> Optional[FxRow]:
        rows = await self.cli.select(
            "fx",
            params={
                "date": f"lte.{target_date.isoformat()}",
                "order": "date.desc",
                "limit": "1",
                "select": "date,usd_krw",
            },
        )
        if not rows:
            return None
        r = rows[0]
        return FxRow(
            date=date.fromisoformat(r["date"]),
            usd_krw=float(r["usd_krw"]),
        )

    async def get_ticker_meta(self, ticker: str) -> Optional[dict]:
        """가장 최근 prices 행에서 name/market 추출."""
        rows = await self.cli.select(
            "prices",
            params={
                "ticker": f"eq.{ticker}",
                "order": "date.desc",
                "limit": "1",
                "select": "ticker,name,market",
            },
        )
        if not rows:
            return None
        return rows[0]
