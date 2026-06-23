"""reactions(ReactionService + PostsRepository.react RPC) 단위 테스트.

검증:
- react → react_to_post RPC 호출, 갱신된 카운트 반환
- 같은 visitor 가 type 변경 → RPC UPSERT 위임(서비스는 type 그대로 전달)
- 포스트 미존재 → PostNotFoundError(404 정규화) + RPC 미호출
- my_reaction 반환 = 요청 type
- PostsRepository.react: rpc 응답(fire/clap/cry) 파싱
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from ..models.schemas import ReactRequest
from ..repositories.posts_repo import PostRow, PostsRepository
from ..services.posts import PostNotFoundError
from ..services.reactions import ReactionService


def _post_row() -> PostRow:
    return PostRow(
        id="11111111-1111-1111-1111-111111111111",
        created_at=datetime(2026, 5, 27, 12, tzinfo=timezone.utc),
        ticker="000660",
        name="SK하이닉스",
        qty=10,
        buy_date=date(2024, 1, 1),
        profit_amount=100_000.0,
        profit_pct=5.0,
        caption=None,
        nickname=None,
        fire_count=0,
        clap_count=0,
        cry_count=0,
        origin="direct",
    )


# ---------- ReactionService ----------


@pytest.mark.asyncio
async def test_react_fire_increments():
    repo = AsyncMock()
    repo.get.return_value = _post_row()
    repo.react.return_value = {"fire": 1, "clap": 0, "cry": 0}

    svc = ReactionService(repo)
    res = await svc.react(
        "11111111-1111-1111-1111-111111111111",
        ReactRequest(type="fire", visitor_id="visitor-1"),
    )
    assert res.fire_count == 1
    assert res.my_reaction == "fire"
    repo.react.assert_awaited_once_with(
        post_id="11111111-1111-1111-1111-111111111111",
        visitor_id="visitor-1",
        type_="fire",
    )


@pytest.mark.asyncio
async def test_react_change_type_same_visitor():
    """같은 visitor 가 fire→clap: RPC UPSERT 로 합계 불변(fire 0, clap 1)."""
    repo = AsyncMock()
    repo.get.return_value = _post_row()
    repo.react.return_value = {"fire": 0, "clap": 1, "cry": 0}

    svc = ReactionService(repo)
    res = await svc.react(
        "11111111-1111-1111-1111-111111111111",
        ReactRequest(type="clap", visitor_id="visitor-1"),
    )
    assert res.fire_count == 0
    assert res.clap_count == 1
    assert res.my_reaction == "clap"


@pytest.mark.asyncio
async def test_react_post_not_found_skips_rpc():
    repo = AsyncMock()
    repo.get.return_value = None
    svc = ReactionService(repo)
    with pytest.raises(PostNotFoundError):
        await svc.react("zzz", ReactRequest(type="fire", visitor_id="visitor-1"))
    repo.react.assert_not_called()


@pytest.mark.asyncio
async def test_react_cry_type():
    repo = AsyncMock()
    repo.get.return_value = _post_row()
    repo.react.return_value = {"fire": 0, "clap": 0, "cry": 7}
    svc = ReactionService(repo)
    res = await svc.react(
        "11111111-1111-1111-1111-111111111111",
        ReactRequest(type="cry", visitor_id="visitor-2"),
    )
    assert res.cry_count == 7
    assert res.my_reaction == "cry"


# ---------- PostsRepository.react (RPC 파싱) ----------


@pytest.mark.asyncio
async def test_repo_react_parses_rpc_response():
    write = AsyncMock()
    write.rpc.return_value = [{"fire": 3, "clap": 1, "cry": 0}]
    cli = AsyncMock()
    repo = PostsRepository(client=cli, write_client=write)

    counts = await repo.react(
        post_id="11111111-1111-1111-1111-111111111111",
        visitor_id="v1",
        type_="fire",
    )
    assert counts == {"fire": 3, "clap": 1, "cry": 0}
    # RPC 파라미터 검증
    write.rpc.assert_awaited_once_with(
        "react_to_post",
        {
            "p_post_id": "11111111-1111-1111-1111-111111111111",
            "p_visitor": "v1",
            "p_type": "fire",
        },
    )


@pytest.mark.asyncio
async def test_repo_react_empty_response_raises():
    write = AsyncMock()
    write.rpc.return_value = []
    repo = PostsRepository(client=AsyncMock(), write_client=write)
    with pytest.raises(RuntimeError):
        await repo.react(post_id="x", visitor_id="v1", type_="fire")


# ---------- ReactRequest 검증 (Pydantic) ----------


def test_react_request_invalid_type():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        ReactRequest(type="love", visitor_id="visitor-1")  # type: ignore[arg-type]


def test_react_request_short_visitor():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        ReactRequest(type="fire", visitor_id="x")  # min_length=8
