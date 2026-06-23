"""Pydantic 스키마 검증."""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from ..models.schemas import CalculateRequest


def test_qty_negative_rejected():
    with pytest.raises(ValidationError):
        CalculateRequest(ticker="000660", qty=0, buy_date=date(2024, 1, 1))


def test_qty_over_max_rejected():
    with pytest.raises(ValidationError):
        CalculateRequest(ticker="000660", qty=1_000_000, buy_date=date(2024, 1, 1))


def test_buy_date_in_future_rejected():
    with pytest.raises(ValidationError):
        CalculateRequest(ticker="000660", qty=1, buy_date=date(2099, 1, 1))


def test_buy_date_too_old_rejected():
    with pytest.raises(ValidationError):
        CalculateRequest(ticker="000660", qty=1, buy_date=date(1999, 12, 31))


def test_ticker_normalized():
    r = CalculateRequest(ticker="nvda", qty=1, buy_date=date(2024, 1, 1))
    assert r.ticker == "NVDA"
