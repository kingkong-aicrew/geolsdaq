"""이번 달 수익 계산.

scope:
- period_start (KST 당월 1일) 직전 거래일 종가 = price_start
- period_end (KST 어제) 종가 = price_end
- 두 종가 차이 × 수량 = profit_amount_krw
- ((end - start) / start) * 100 = profit_pct (종목 자체 수익률)

가드:
- buy_date 가 period_start 이후면 → price_start = buy_date 종가로 대체
  (당월 중도 매수자도 자기 매수 시점부터의 이번 달 수익을 본다)
- 휴장일이면 그 이전 가장 가까운 거래일 종가
- 종목 없음 → 404
- 가격 없음 → 503
"""
from __future__ import annotations

from datetime import date

from ..models.schemas import CalculateRequest, CalculateResponse
from ..repositories.prices import PriceRepository, PriceRow
from ..config import get_settings
from .period import current_month_window


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

        period_start, period_end = current_month_window()

        # period_start 가격 (또는 buy_date 가격, 더 늦은 쪽)
        price_start_ref = max(period_start, req.buy_date)
        # 첫 시점 종가는 'price_start_ref 직전 거래일' 종가가 정의에 맞음.
        # 단순화: price_start_ref 당일 또는 이전 가장 가까운 종가 사용.
        start_row = await self.prices.get_close_on_or_before(req.ticker, price_start_ref)
        end_row = await self.prices.get_close_on_or_before(req.ticker, period_end)

        if not start_row or not end_row:
            raise PriceUnavailableError(
                f"가격 데이터가 부족합니다 (start={start_row}, end={end_row}). 배치 확인."
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
            period_start=period_start,
            period_end=period_end,
            price_period_start=round(krw_start, 2),
            price_period_end=round(krw_end, 2),
            profit_amount_krw=round(profit_amount, 2),
            profit_pct=round(profit_pct, 4),
            disclaimer=s.disclaimer,
        )
