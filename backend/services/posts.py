"""posts — 피드 등재.

scope (Phase B):
- 서버가 다시 계산하여 검증 후 insert (위·변조 차단 — stash 골격 재사용).
- caption(≤60)·nickname(≤12) 허용. caption 은 URL/@ 필터(스팸·멘션 차단).
- IP 분당 제한은 slowapi(main.py). 여기서는 ip_hash 만 기록.

가드:
- caption trim 후 60 초과 → CaptionRejectedError(400 한글)
- caption 에 URL/@ → CaptionRejectedError(400 한글)
- 종목 미존재 → TickerNotFoundError(404, calculator 전파)
- 가격 부족 → PriceUnavailableError(503, calculator 전파)
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

from ..config import get_settings
from ..models.schemas import (
    CalculateRequest,
    PostCreate,
    PostCreateResponse,
    PostDetailResponse,
    _MENTION_PATTERN,
    _URL_PATTERN,
)
from ..repositories.posts_repo import PostsRepository
from .calculator import Calculator


class CaptionRejectedError(Exception):
    """캡션 검증 실패 — main.py 에서 400 한글로 정규화."""


class PostNotFoundError(Exception):
    """조회/반응 대상 포스트 미존재 — main.py 에서 404 한글로 정규화."""


def _hash_ip(ip: str) -> str:
    """IP 평문 저장 ✕ — 해시만 (stash 와 동일 규칙)."""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32]


def _clean_caption(raw: Optional[str]) -> Optional[str]:
    """캡션 정규화 + 검증. None/빈 문자열 → None.

    trim 후 길이·URL·@멘션 검사. 위반 시 CaptionRejectedError(한글).
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if len(s) > get_settings().max_caption_length:
        raise CaptionRejectedError("한 줄 자랑은 60자까지예요")
    if _URL_PATTERN.search(s):
        raise CaptionRejectedError("링크·멘션은 넣을 수 없어요")
    if _MENTION_PATTERN.search(s):
        raise CaptionRejectedError("링크·멘션은 넣을 수 없어요")
    return s


def _clean_nickname(raw: Optional[str]) -> Optional[str]:
    """닉네임 정규화. trim 후 빈 문자열 → None, 12자 초과 → 잘라냄(Pydantic 1차 방어 후)."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    return s[: get_settings().max_nickname_length]


class PostService:
    def __init__(self, calc: Calculator, posts_repo: PostsRepository):
        self.calc = calc
        self.repo = posts_repo

    async def create(self, req: PostCreate, *, client_ip: str) -> PostCreateResponse:
        # 1) 캡션·닉네임 검증(서버측 — Pydantic 길이 1차 통과 후 URL/@ 2차)
        caption = _clean_caption(req.caption)
        nickname = _clean_nickname(req.nickname)

        # 2) 서버 재계산 (위·변조 차단 — stash 와 동일)
        result = await self.calc.calculate(
            CalculateRequest(ticker=req.ticker, qty=req.qty, buy_date=req.buy_date)
        )

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
            "caption": caption,
            "nickname": nickname,
            "origin": req.origin,
            # 카운트는 생성 시 0 (RLS WITH CHECK 가 강제 — DEFAULT 0 명시 불필요하나
            # 명시적으로 0 을 보내 RLS 통과를 보장).
            "fire_count": 0,
            "clap_count": 0,
            "cry_count": 0,
            "ip_hash": _hash_ip(client_ip),
        }

        row = await self.repo.insert(payload)
        s = get_settings()
        return PostCreateResponse(
            id=row.id,
            created_at=row.created_at,
            ticker=row.ticker,
            name=row.name,
            profit_amount=row.profit_amount,
            profit_pct=row.profit_pct,
            caption=row.caption,
            nickname=row.nickname,
            fire_count=row.fire_count,
            clap_count=row.clap_count,
            cry_count=row.cry_count,
            origin=row.origin,  # type: ignore[arg-type]
            disclaimer=s.disclaimer,
        )

    async def get_detail(
        self, post_id: str, *, visitor_id: Optional[str] = None
    ) -> PostDetailResponse:
        """단건 카드 + (visitor_id 제공 시)내 반응 + 면책."""
        row = await self.repo.get(post_id)
        if not row:
            raise PostNotFoundError(f"글을 찾을 수 없습니다: {post_id}")
        my_reaction = None
        if visitor_id:
            my_reaction = await self.repo.my_reaction(
                post_id=post_id, visitor_id=visitor_id
            )
        s = get_settings()
        return PostDetailResponse(
            id=row.id,
            created_at=row.created_at,
            ticker=row.ticker,
            name=row.name,
            qty=row.qty,
            buy_date=row.buy_date,
            profit_amount=row.profit_amount,
            profit_pct=row.profit_pct,
            caption=row.caption,
            nickname=row.nickname,
            fire_count=row.fire_count,
            clap_count=row.clap_count,
            cry_count=row.cry_count,
            origin=row.origin,  # type: ignore[arg-type]
            my_reaction=my_reaction,  # type: ignore[arg-type]
            disclaimer=s.disclaimer,
        )
