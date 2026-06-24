"""'그때 샀다면 지금' 보유 수익 계산.

scope:
- buy_date 종가 = price_start (그때 산 가격. 휴장일이면 직전 거래일)
- 최신 거래일 종가 = price_end (지금 가격)
- (price_end - price_start) × 수량 = profit_amount_krw
- ((end - start) / start) × 100 = profit_pct (보유 수익률)

가드:
- buy_date 가 상장 전 등으로 데이터 없음 → 503 (정직하게 "그 시점 데이터 없음")
- 휴장일이면 그 이전 가장 가까운 거래일 종가
- 종목 없음 → 404
- 가격 없음 → 503
- period_end 는 항상 '실제 데이터가 있는 최신 거래일' = 라벨과 가격일 불일치 없음
"""
from __future__ import annotations

from datetime import date

from ..models.schemas import CalculateRequest, CalculateResponse
from ..repositories.prices import PriceRepository, PriceRow
from ..config import get_settings
from . import period


class TickerNotFoundError(Exception):
    pass


class PriceUnavailableError(Exception):
    pass


class Calculator:
    def __init__(self, prices: PriceRepository):
        self.prices = prices

    async def _krw_close(self, row: PriceRow, ref_date: date) -> float:
        """USD 종목은 ref_date 환율로 KRW 환산. KR 종목은 그대로."""
        if row.market == "KR":
            return float(row.close)
        fx = await self.prices.get_fx_on_or_before(ref_date)
        if not fx:
            raise PriceUnavailableError(
                f"환율 데이터가 없습니다 ({ref_date}). 배치 cron 확인 필요."
            )
        return float(row.close) * fx.usd_krw

    async def calculate(self, req: CalculateRequest) -> CalculateResponse:
        meta = await self.prices.get_ticker_meta(req.ticker)
        if not meta:
            raise TickerNotFoundError(
                f"종목 '{req.ticker}'을(를) 찾을 수 없습니다."
            )

        # "그때(buy_date) 샀다면 지금(최신 거래일)" 보유 수익.
        # price_start = buy_date(또는 직전 거래일) 종가, price_end = 최신 거래일 종가.
        today = period.kst_today()
        start_row = await self.prices.get_close_on_or_before(req.ticker, req.buy_date)
        end_row = await self.prices.get_close_on_or_before(req.ticker, today)

        if not start_row:
            # buy_date 이전 거래일 종가가 테이블에 없음 = 상장 전이거나 데이터 부족
            raise PriceUnavailableError(
                f"{req.buy_date} 시점 가격이 없습니다 (상장 전이거나 데이터 부족)."
            )
        if not end_row:
            raise PriceUnavailableError(
                "최신 가격 데이터가 없습니다. 배치 cron 확인 필요."
            )

        krw_start = await self._krw_close(start_row, start_row.date)
        krw_end = await self._krw_close(end_row, end_row.date)

        profit_amount = (krw_end - krw_start) * req.qty
        profit_pct = ((krw_end - krw_start) / krw_start) * 100 if krw_start else 0.0

        s = get_settings()
        return CalculateResponse(
            ticker=req.ticker,
            name=meta["name"],
            market=meta["market"],
            qty=req.qty,
            buy_date=req.buy_date,
            # period_start = 실제 매수 반영일(buy_date 또는 직전 거래일)
            # period_end = 실제 최신 거래일(지금) → 라벨과 가격일이 항상 일치
            period_start=start_row.date,
            period_end=end_row.date,
            price_period_start=round(krw_start, 2),
            price_period_end=round(krw_end, 2),
            profit_amount_krw=round(profit_amount, 2),
            profit_pct=round(profit_pct, 4),
            disclaimer=s.disclaimer,
        )
