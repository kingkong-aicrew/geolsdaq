"""feed — 피드 조회 (latest/hot 정렬 + 종목 필터 + 커서 페이징).

설계:
- 정렬·필터·커서 조립은 리포지토리(keyset)에 위임. 이 서비스는 커서
  encode/decode 와 응답 조립만(SRP).
- latest: created_at desc / hot: fire_count desc, created_at desc.
"""
from __future__ import annotations

from typing import Optional

from ..config import get_settings
from ..models.schemas import FeedResponse, PostCard
from ..repositories.posts_repo import (
    PostsRepository,
    decode_cursor,
    encode_cursor,
)


class FeedService:
    def __init__(self, posts_repo: PostsRepository):
        self.repo = posts_repo

    async def fetch(
        self,
        *,
        sort: str,                  # "latest" | "hot"
        ticker: Optional[str],
        limit: int,
        cursor: Optional[str],
    ) -> FeedResponse:
        cursor_payload = decode_cursor(cursor) if cursor else None
        rows, next_cursor = await self.repo.feed(
            sort=sort,
            ticker=ticker,
            limit=limit,
            cursor=cursor_payload,
        )
        cards = [
            PostCard(
                id=r.id,
                created_at=r.created_at,
                ticker=r.ticker,
                name=r.name,
                qty=r.qty,
                buy_date=r.buy_date,
                profit_amount=r.profit_amount,
                profit_pct=r.profit_pct,
                caption=r.caption,
                nickname=r.nickname,
                fire_count=r.fire_count,
                clap_count=r.clap_count,
                cry_count=r.cry_count,
                origin=r.origin,  # type: ignore[arg-type]
            )
            for r in rows
        ]
        s = get_settings()
        return FeedResponse(
            sort=sort,  # type: ignore[arg-type]
            ticker=ticker,
            posts=cards,
            next_cursor=encode_cursor(next_cursor) if next_cursor else None,
            disclaimer=s.disclaimer,
        )
