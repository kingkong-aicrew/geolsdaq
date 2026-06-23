"""평행우주(ParallelService) 단위 테스트 — Supabase mock.

검증:
- mine/alt 각각 calculate 재사용 (신규 계산 로직 없음 — diff만 조합)
- verdict 정합 (amount_delta 부호 ↔ alt_better/mine_better/tie)
- 종목 미존재(alt) → TickerNotFoundError 전파
- 가격 부족 → PriceUnavailableError 전파
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from unittest.mock import AsyncMock

import pytest

from ..models.schemas import ParallelRequest
from ..repositories.prices import PriceRow
from ..services.calculator import (
    Calculator,
    PriceUnavailableError,
    TickerNotFoundError,
)
from ..services.parallel import ParallelService


def _row(ticker: str, name: str, d: date, close: float) -> PriceRow:
    return PriceRow(ticker, name, "KR", d, close)


def _two_ticker_repo(
    *,
    mine_meta: Optional[dict],
    alt_meta: Optional[dict],
    mine_start: Optional[PriceRow],
    mine_end: Optional[PriceRow],
    alt_start: Optional[PriceRow],
    alt_end: Optional[PriceRow],
):
    """calculate 가 mine→alt 순으로 호출됨.

    각 calculate 는 get_ticker_meta 1회 + get_close_on_or_before 2회(start,end).
    → meta side_effect = [mine, alt], close side_effect = [mine_start, mine_end, alt_start, alt_end]
    """
    repo = AsyncMock()
    repo.get_ticker_meta.side_effect = [mine_meta, alt_meta]
    repo.get_close_on_or_before.side_effect = [
        mine_start,
        mine_end,
        alt_start,
        alt_end,
    ]
    repo.get_fx_on_or_before.return_value = None
    return repo


@pytest.mark.asyncio
async def test_alt_better(monkeypatch):
    """대체 종목(삼성전자)이 내 종목(SK하이닉스)보다 더 벌면 alt_better."""
    from ..services import period as period_mod

    monkeypatch.setattr(period_mod, "kst_today", lambda: date(2026, 5, 27))

    # mine: 200,000 → 210,000 (10주 = +100,000)
    # alt:   80,000 →  90,000 (10주 = +100,000... 더 벌게 하려면 alt 더 큰 상승)
    # alt:   80,000 → 100,000 (10주 = +200,000) → alt_better
    repo = _two_ticker_repo(
        mine_meta={"ticker": "000660", "name": "SK하이닉스", "market": "KR"},
        alt_meta={"ticker": "005930", "name": "삼성전자", "market": "KR"},
        mine_start=_row("000660", "SK하이닉스", date(2026, 5, 1), 200_000),
        mine_end=_row("000660", "SK하이닉스", date(2026, 5, 26), 210_000),
        alt_start=_row("005930", "삼성전자", date(2026, 5, 1), 80_000),
        alt_end=_row("005930", "삼성전자", date(2026, 5, 26), 100_000),
    )
    svc = ParallelService(Calculator(repo))
    req = ParallelRequest(
        ticker="000660", qty=10, buy_date=date(2024, 1, 1), alt_ticker="005930"
    )
    res = await svc.compare(req)

    assert res.mine.profit_amount_krw == 100_000.0
    assert res.alt.profit_amount_krw == 200_000.0
    assert res.diff.amount_delta_krw == 100_000.0  # alt - mine
    assert res.diff.verdict == "alt_better"
    assert res.diff.amount_delta_krw > 0  # 부호 ↔ verdict 정합
    assert res.disclaimer


@pytest.mark.asyncio
async def test_mine_better(monkeypatch):
    """내 종목이 더 벌면 mine_better, amount_delta 음수."""
    from ..services import period as period_mod

    monkeypatch.setattr(period_mod, "kst_today", lambda: date(2026, 5, 27))

    # mine: +200,000 / alt: +100,000 → mine_better
    repo = _two_ticker_repo(
        mine_meta={"ticker": "000660", "name": "SK하이닉스", "market": "KR"},
        alt_meta={"ticker": "005930", "name": "삼성전자", "market": "KR"},
        mine_start=_row("000660", "SK하이닉스", date(2026, 5, 1), 80_000),
        mine_end=_row("000660", "SK하이닉스", date(2026, 5, 26), 100_000),
        alt_start=_row("005930", "삼성전자", date(2026, 5, 1), 80_000),
        alt_end=_row("005930", "삼성전자", date(2026, 5, 26), 90_000),
    )
    svc = ParallelService(Calculator(repo))
    req = ParallelRequest(
        ticker="000660", qty=10, buy_date=date(2024, 1, 1), alt_ticker="005930"
    )
    res = await svc.compare(req)

    assert res.mine.profit_amount_krw == 200_000.0
    assert res.alt.profit_amount_krw == 100_000.0
    assert res.diff.amount_delta_krw == -100_000.0
    assert res.diff.verdict == "mine_better"
    assert res.diff.amount_delta_krw < 0


@pytest.mark.asyncio
async def test_tie(monkeypatch):
    """수익액이 같으면 tie, amount_delta 0."""
    from ..services import period as period_mod

    monkeypatch.setattr(period_mod, "kst_today", lambda: date(2026, 5, 27))

    repo = _two_ticker_repo(
        mine_meta={"ticker": "000660", "name": "SK하이닉스", "market": "KR"},
        alt_meta={"ticker": "005930", "name": "삼성전자", "market": "KR"},
        mine_start=_row("000660", "SK하이닉스", date(2026, 5, 1), 200_000),
        mine_end=_row("000660", "SK하이닉스", date(2026, 5, 26), 210_000),
        alt_start=_row("005930", "삼성전자", date(2026, 5, 1), 50_000),
        alt_end=_row("005930", "삼성전자", date(2026, 5, 26), 60_000),
    )
    # mine: (210k-200k)*10 = 100,000 / alt: (60k-50k)*10 = 100,000 → tie
    svc = ParallelService(Calculator(repo))
    req = ParallelRequest(
        ticker="000660", qty=10, buy_date=date(2024, 1, 1), alt_ticker="005930"
    )
    res = await svc.compare(req)

    # verdict 는 금액 차(amount_delta) 기준 → 금액 같으면 tie.
    assert res.diff.amount_delta_krw == 0.0
    assert res.diff.verdict == "tie"
    # 금액은 같아도 수익률은 다를 수 있다: mine 200k→210k(+5%), alt 50k→60k(+20%)
    # → pct_delta = 20 - 5 = 15 (별개 지표라 0 이 아님이 정상)
    assert abs(res.mine.profit_pct - 5.0) < 0.01
    assert abs(res.alt.profit_pct - 20.0) < 0.01
    assert abs(res.diff.pct_delta - 15.0) < 0.01


@pytest.mark.asyncio
async def test_alt_ticker_not_found(monkeypatch):
    """대체 종목 미존재 → calculate 가 TickerNotFoundError 전파."""
    from ..services import period as period_mod

    monkeypatch.setattr(period_mod, "kst_today", lambda: date(2026, 5, 27))

    # mine 정상, alt meta=None
    repo = _two_ticker_repo(
        mine_meta={"ticker": "000660", "name": "SK하이닉스", "market": "KR"},
        alt_meta=None,
        mine_start=_row("000660", "SK하이닉스", date(2026, 5, 1), 200_000),
        mine_end=_row("000660", "SK하이닉스", date(2026, 5, 26), 210_000),
        alt_start=None,
        alt_end=None,
    )
    svc = ParallelService(Calculator(repo))
    req = ParallelRequest(
        ticker="000660", qty=10, buy_date=date(2024, 1, 1), alt_ticker="ZZZZ"
    )
    with pytest.raises(TickerNotFoundError):
        await svc.compare(req)


@pytest.mark.asyncio
async def test_mine_price_unavailable(monkeypatch):
    """내 종목 가격 부족 → PriceUnavailableError 전파."""
    from ..services import period as period_mod

    monkeypatch.setattr(period_mod, "kst_today", lambda: date(2026, 5, 27))

    repo = _two_ticker_repo(
        mine_meta={"ticker": "000660", "name": "SK하이닉스", "market": "KR"},
        alt_meta={"ticker": "005930", "name": "삼성전자", "market": "KR"},
        mine_start=None,  # 가격 없음
        mine_end=None,
        alt_start=None,
        alt_end=None,
    )
    svc = ParallelService(Calculator(repo))
    req = ParallelRequest(
        ticker="000660", qty=10, buy_date=date(2024, 1, 1), alt_ticker="005930"
    )
    with pytest.raises(PriceUnavailableError):
        await svc.compare(req)


@pytest.mark.asyncio
async def test_pct_delta_sign(monkeypatch):
    """pct_delta = alt.profit_pct - mine.profit_pct 검산."""
    from ..services import period as period_mod

    monkeypatch.setattr(period_mod, "kst_today", lambda: date(2026, 5, 27))

    # mine: 100,000→110,000 = +10% / alt: 100,000→105,000 = +5%
    repo = _two_ticker_repo(
        mine_meta={"ticker": "000660", "name": "SK하이닉스", "market": "KR"},
        alt_meta={"ticker": "005930", "name": "삼성전자", "market": "KR"},
        mine_start=_row("000660", "SK하이닉스", date(2026, 5, 1), 100_000),
        mine_end=_row("000660", "SK하이닉스", date(2026, 5, 26), 110_000),
        alt_start=_row("005930", "삼성전자", date(2026, 5, 1), 100_000),
        alt_end=_row("005930", "삼성전자", date(2026, 5, 26), 105_000),
    )
    svc = ParallelService(Calculator(repo))
    req = ParallelRequest(
        ticker="000660", qty=10, buy_date=date(2024, 1, 1), alt_ticker="005930"
    )
    res = await svc.compare(req)
    # mine +10%, alt +5% → pct_delta = 5 - 10 = -5
    assert abs(res.mine.profit_pct - 10.0) < 0.01
    assert abs(res.alt.profit_pct - 5.0) < 0.01
    assert abs(res.diff.pct_delta - (-5.0)) < 0.01
    assert res.diff.verdict == "mine_better"
