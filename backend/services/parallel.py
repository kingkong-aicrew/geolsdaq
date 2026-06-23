"""평행우주 (종목대체형) — '만약 OO 샀다면'.

설계 원칙 (점진 확장, SOLID-O):
- 신규 계산 로직 0. 기존 `Calculator.calculate()`를 mine/alt 각 1회 호출.
- 이 서비스는 두 결과의 diff(차액·verdict)만 조합한다.
- 비교 기준: 주식 수 고정(qty 동일, 설계 Q1=A). "같은 돈이었다면"은 후속.

가드:
- mine/alt 중 종목 미존재 → TickerNotFoundError (calculator가 전파, 404)
- 가격/환율 부족 → PriceUnavailableError (calculator가 전파, 503)
"""
from __future__ import annotations

from ..config import get_settings
from ..models.schemas import (
    CalculateRequest,
    ParallelDiff,
    ParallelRequest,
    ParallelResponse,
)
from .calculator import Calculator

# verdict 판정 임계치 — 차액 절댓값이 이보다 작으면 tie.
# 부동소수 반올림 오차 흡수(원 단위) + "사실상 동일"을 tie 로 표현.
_TIE_EPSILON_KRW = 1.0


class ParallelService:
    def __init__(self, calculator: Calculator):
        self.calculator = calculator

    async def compare(self, req: ParallelRequest) -> ParallelResponse:
        # 1) 내 종목 — 기존 calculate 그대로 재사용
        mine = await self.calculator.calculate(
            CalculateRequest(
                ticker=req.ticker,
                qty=req.qty,
                buy_date=req.buy_date,
            )
        )
        # 2) 대체 종목 — 동일 qty/buy_date (주식 수 고정)
        alt = await self.calculator.calculate(
            CalculateRequest(
                ticker=req.alt_ticker,
                qty=req.qty,
                buy_date=req.buy_date,
            )
        )

        # 3) diff — 신규 계산 없음, 두 결과의 차이만
        amount_delta = round(alt.profit_amount_krw - mine.profit_amount_krw, 2)
        pct_delta = round(alt.profit_pct - mine.profit_pct, 4)

        if amount_delta > _TIE_EPSILON_KRW:
            verdict = "alt_better"
        elif amount_delta < -_TIE_EPSILON_KRW:
            verdict = "mine_better"
        else:
            verdict = "tie"

        s = get_settings()
        return ParallelResponse(
            mine=mine,
            alt=alt,
            diff=ParallelDiff(
                amount_delta_krw=amount_delta,
                pct_delta=pct_delta,
                verdict=verdict,
            ),
            disclaimer=s.disclaimer,
        )
