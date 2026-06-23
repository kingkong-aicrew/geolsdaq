"""calculator 단위 테스트 — Supabase mock."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional
from unittest.mock import AsyncMock

import pytest

from ..models.schemas import CalculateRequest
from ..repositories.prices import FxRow, PriceRow
from ..services.calculator import (
    Calculator,
    PriceUnavailableError,
    TickerNotFoundError,
)


def _mock_repo(
    *,
    meta: Optional[dict],
    start_row: Optional[PriceRow],
    end_row: Optional[PriceRow],
    fx: Optional[FxRow] = None,
):
    repo = AsyncMock()
    repo.get_ticker_meta.return_value = meta
    repo.get_close_on_or_before.side_effect = [start_row, end_row]
    repo.get_fx_on_or_before.return_value = fx
    return repo


@pytest.mark.asyncio
async def test_kr_basic(monkeypatch):
    """SK하이닉스 10주, 당월 5% 상승."""
    from ..services import period as period_mod

    monkeypatch.setattr(period_mod, "kst_today", lambda: date(2026, 5, 27))

    repo = _mock_repo(
        meta={"ticker": "000660", "name": "SK하이닉스", "market": "KR"},
        start_row=PriceRow("000660", "SK하이닉스", "KR", date(2026, 4, 30), 200_000),
        end_row=PriceRow("000660", "SK하이닉스", "KR", date(2026, 5, 26), 210_000),
    )
    calc = Calculator(repo)
    req = CalculateRequest(ticker="000660", qty=10, buy_date=date(2024, 1, 1))
    res = await calc.calculate(req)
    assert res.market == "KR"
    assert res.qty == 10
    assert res.profit_amount_krw == 100_000.0
    assert abs(res.profit_pct - 5.0) < 0.01


@pytest.mark.asyncio
async def test_us_with_fx(monkeypatch):
    """NVDA 5주, 환율 환산 검증."""
    from ..services import period as period_mod

    monkeypatch.setattr(period_mod, "kst_today", lambda: date(2026, 5, 27))

    repo = _mock_repo(
        meta={"ticker": "NVDA", "name": "엔비디아", "market": "US"},
        start_row=PriceRow("NVDA", "엔비디아", "US", date(2026, 4, 30), 100.0),
        end_row=PriceRow("NVDA", "엔비디아", "US", date(2026, 5, 26), 110.0),
        fx=FxRow(date(2026, 5, 26), 1_300.0),
    )
    calc = Calculator(repo)
    req = CalculateRequest(ticker="NVDA", qty=5, buy_date=date(2024, 1, 1))
    res = await calc.calculate(req)
    # 시작가 환산: 100 USD * 1300 KRW = 130,000 KRW
    # 종료가 환산: 110 USD * 1300 KRW = 143,000 KRW
    # diff per share: 13,000 → 5주 = 65,000
    assert res.market == "US"
    assert res.profit_amount_krw == 65_000.0


@pytest.mark.asyncio
async def test_ticker_not_found(monkeypatch):
    from ..services import period as period_mod
    monkeypatch.setattr(period_mod, "kst_today", lambda: date(2026, 5, 27))

    repo = _mock_repo(meta=None, start_row=None, end_row=None)
    calc = Calculator(repo)
    req = CalculateRequest(ticker="UNKNOWN", qty=1, buy_date=date(2024, 1, 1))
    with pytest.raises(TickerNotFoundError):
        await calc.calculate(req)


@pytest.mark.asyncio
async def test_buy_date_after_period_start_uses_buy_date(monkeypatch):
    """당월 중도 매수 — buy_date 종가 사용."""
    from ..services import period as period_mod

    monkeypatch.setattr(period_mod, "kst_today", lambda: date(2026, 5, 27))

    # buy_date = 5월 15일 (당월 1일 5/1 보다 늦음) → buy_date 가 start ref
    repo = _mock_repo(
        meta={"ticker": "005930", "name": "삼성전자", "market": "KR"},
        start_row=PriceRow("005930", "삼성전자", "KR", date(2026, 5, 15), 80_000),
        end_row=PriceRow("005930", "삼성전자", "KR", date(2026, 5, 26), 84_000),
    )
    calc = Calculator(repo)
    req = CalculateRequest(ticker="005930", qty=10, buy_date=date(2026, 5, 15))
    res = await calc.calculate(req)
    assert res.profit_amount_krw == 40_000.0


@pytest.mark.asyncio
async def test_us_missing_fx_raises(monkeypatch):
    from ..services import period as period_mod
    monkeypatch.setattr(period_mod, "kst_today", lambda: date(2026, 5, 27))

    repo = _mock_repo(
        meta={"ticker": "AAPL", "name": "애플", "market": "US"},
        start_row=PriceRow("AAPL", "애플", "US", date(2026, 4, 30), 200.0),
        end_row=PriceRow("AAPL", "애플", "US", date(2026, 5, 26), 210.0),
        fx=None,
    )
    calc = Calculator(repo)
    req = CalculateRequest(ticker="AAPL", qty=1, buy_date=date(2024, 1, 1))
    with pytest.raises(PriceUnavailableError):
        await calc.calculate(req)
