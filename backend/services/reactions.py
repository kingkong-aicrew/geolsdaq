"""reactions — 반응(🔥fire 👏clap 😭cry) 등록.

설계:
- 원자적 upsert + 카운트 재집계는 react_to_post RPC(트랜잭션)에 위임.
  서비스는 포스트 존재 확인(404 정규화) + 응답 조립만.
- 포스트 미존재를 RPC 에러 메시지 파싱으로 잡으면 취약 → 사전 get() 으로 확인.
  (RPC 에도 NOT EXISTS 가드가 있어 race 시 2차 방어)
- 1인 1포스트 1반응: reactions PK(post_id, visitor_id) + RPC UPSERT 가 보장.
"""
from __future__ import annotations

from ..models.schemas import ReactRequest, ReactResponse
from ..repositories.posts_repo import PostsRepository
from .posts import PostNotFoundError


class ReactionService:
    def __init__(self, posts_repo: PostsRepository):
        self.repo = posts_repo

    async def react(self, post_id: str, req: ReactRequest) -> ReactResponse:
        # 사전 존재 확인 — 404 를 안정적으로 정규화(RPC 에러 파싱 회피)
        existing = await self.repo.get(post_id)
        if not existing:
            raise PostNotFoundError(
                f"반응할 글을 찾을 수 없습니다: {post_id}"
            )

        counts = await self.repo.react(
            post_id=post_id,
            visitor_id=req.visitor_id,
            type_=req.type,
        )
        return ReactResponse(
            post_id=post_id,
            fire_count=counts["fire"],
            clap_count=counts["clap"],
            cry_count=counts["cry"],
            my_reaction=req.type,
        )
