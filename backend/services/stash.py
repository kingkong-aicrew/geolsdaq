"""stash — 익명 자랑 등재.

scope (사용자 조정 #1):
- 캡션·닉네임 없음 (Phase B)
- 서버가 다시 계산하여 검증 후 insert (위·변조 차단)
- IP 분당 10건 (slowapi 에서 처리; 여기서는 ip_hash 만 기록)
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict

from ..models.schemas import CalculateRequest, StashRequest, StashResponse
from ..config import get_settings
from ..repositories.stash import StashRepository
from .calculator import Calculator


def _hash_ip(ip: str) -> str:
    """IP 평문 저장 ✕ — 해시만 저장."""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32]


class StashService:
    def __init__(self, calc: Calculator, stash_repo: StashRepository):
        self.calc = calc
        self.repo = stash_repo

    async def submit(self, req: StashRequest, *, client_ip: str) -> StashResponse:
        # 서버 측 재계산
        calc_req = CalculateRequest(
            ticker=req.ticker, qty=req.qty, buy_date=req.buy_date
        )
        result = await self.calc.calculate(calc_req)

        payload: Dict[str, Any] = {
            "ticker": result.ticker,
            "name": result.name,
            "qty": result.qty,
            "buy_date": result.buy_date.isoformat(),
            "profit_amount": result.profit_amount_krw,
            "profit_pct": result.profit_pct,
            "period_start": result.period_start.isoformat(),
            "period_end": result.period_end.isoformat(),
            "calc_snapshot": {
                "price_period_start": result.price_period_start,
                "price_period_end": result.price_period_end,
                "market": result.market,
            },
            "ip_hash": _hash_ip(client_ip),
        }

        row = await self.repo.insert(payload)
        s = get_settings()
        return StashResponse(
            id=row.id,
            profit_amount=row.profit_amount,
            profit_pct=row.profit_pct,
            disclaimer=s.disclaimer,
        )
