"""feed(FeedService + PostsRepository keyset) 단위 테스트.

검증:
- 커서 encode/decode 라운드트립 + 손상 커서 → None(첫 페이지 폴백)
- latest 정렬: order=created_at.desc, 커서 = created_at.lt
- hot 정렬: order=fire_count.desc,created_at.desc, 복합 keyset or= 필터
- limit 만큼 차면 next_cursor 발급, 모자라면 None(마지막 페이지)
- 2페이지 연속성: 1페이지 next_cursor 로 2페이지 호출
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

from ..repositories.posts_repo import (
    PostsRepository,
    decode_cursor,
    encode_cursor,
)
from ..services.feed import FeedService


def _raw(id_: str, created_at: str, fire: int = 0) -> Dict[str, Any]:
    return {
        "id": id_,
        "created_at": created_at,
        "ticker": "000660",
        "name": "SK하이닉스",
        "qty": 10,
        "buy_date": "2024-01-01",
        "profit_amount": 100_000.0,
        "profit_pct": 5.0,
        "caption": None,
        "nickname": None,
        "fire_count": fire,
        "clap_count": 0,
        "cry_count": 0,
        "origin": "direct",
    }


def _repo_with_rows(rows: List[Dict[str, Any]]) -> PostsRepository:
    cli = AsyncMock()
    cli.select.return_value = rows
    write = AsyncMock()
    return PostsRepository(client=cli, write_client=write)


# ---------- 커서 인코딩 ----------


def test_cursor_roundtrip():
    payload = {"created_at": "2026-05-27T12:00:00+00:00", "id": "abc", "fire_count": 3}
    enc = encode_cursor(payload)
    assert decode_cursor(enc) == payload


def test_cursor_corrupt_returns_none():
    assert decode_cursor("!!!not-base64!!!") is None
    assert decode_cursor("YWJj") is None  # "abc" — dict 아님


# ---------- latest 정렬 ----------


@pytest.mark.asyncio
async def test_feed_latest_query_and_next_cursor():
    rows = [
        _raw("p1", "2026-05-27T12:00:03+00:00"),
        _raw("p2", "2026-05-27T12:00:02+00:00"),
    ]
    repo = _repo_with_rows(rows)
    svc = FeedService(repo)

    res = await svc.fetch(sort="latest", ticker=None, limit=2, cursor=None)

    # PostgREST 쿼리 파라미터 검증
    params = repo.cli.select.call_args.kwargs["params"]
    assert params["order"] == "created_at.desc"
    assert params["limit"] == "2"
    assert "or" not in params

    # limit 만큼 찼으니 next_cursor 발급
    assert res.next_cursor is not None
    cur = decode_cursor(res.next_cursor)
    assert cur["created_at"] == "2026-05-27T12:00:02+00:00"
    assert cur["id"] == "p2"
    assert res.posts[0].id == "p1"
    assert res.disclaimer


@pytest.mark.asyncio
async def test_feed_latest_last_page_no_cursor():
    """limit 보다 적게 오면 마지막 페이지 → next_cursor None."""
    repo = _repo_with_rows([_raw("p1", "2026-05-27T12:00:03+00:00")])
    svc = FeedService(repo)
    res = await svc.fetch(sort="latest", ticker=None, limit=20, cursor=None)
    assert res.next_cursor is None
    assert len(res.posts) == 1


@pytest.mark.asyncio
async def test_feed_latest_with_cursor_applies_keyset():
    repo = _repo_with_rows([])
    svc = FeedService(repo)
    cursor = encode_cursor({"created_at": "2026-05-27T12:00:02+00:00", "id": "p2"})
    await svc.fetch(sort="latest", ticker=None, limit=20, cursor=cursor)
    params = repo.cli.select.call_args.kwargs["params"]
    assert params["created_at"] == "lt.2026-05-27T12:00:02+00:00"


# ---------- hot 정렬 ----------


@pytest.mark.asyncio
async def test_feed_hot_order_and_cursor():
    rows = [
        _raw("p1", "2026-05-27T12:00:03+00:00", fire=10),
        _raw("p2", "2026-05-27T12:00:02+00:00", fire=5),
    ]
    repo = _repo_with_rows(rows)
    svc = FeedService(repo)
    res = await svc.fetch(sort="hot", ticker=None, limit=2, cursor=None)

    params = repo.cli.select.call_args.kwargs["params"]
    assert params["order"] == "fire_count.desc,created_at.desc"

    # hot next_cursor 에는 fire_count 포함
    cur = decode_cursor(res.next_cursor)
    assert cur["fire_count"] == 5
    assert cur["created_at"] == "2026-05-27T12:00:02+00:00"


@pytest.mark.asyncio
async def test_feed_hot_cursor_composite_keyset():
    """hot 2페이지: 복합 keyset or= (fire<f OR (fire=f AND created_at<c))."""
    repo = _repo_with_rows([])
    svc = FeedService(repo)
    cursor = encode_cursor(
        {"created_at": "2026-05-27T12:00:02+00:00", "id": "p2", "fire_count": 5}
    )
    await svc.fetch(sort="hot", ticker=None, limit=20, cursor=cursor)
    params = repo.cli.select.call_args.kwargs["params"]
    assert "or" in params
    assert "fire_count.lt.5" in params["or"]
    assert "fire_count.eq.5" in params["or"]
    assert "created_at.lt" in params["or"]


@pytest.mark.asyncio
async def test_feed_ticker_filter():
    repo = _repo_with_rows([])
    svc = FeedService(repo)
    await svc.fetch(sort="latest", ticker="000660", limit=20, cursor=None)
    params = repo.cli.select.call_args.kwargs["params"]
    assert params["ticker"] == "eq.000660"


@pytest.mark.asyncio
async def test_feed_two_page_continuity():
    """1페이지 next_cursor 로 2페이지를 이어서 호출 — 연속성."""
    page1 = [
        _raw("p1", "2026-05-27T12:00:03+00:00", fire=10),
        _raw("p2", "2026-05-27T12:00:02+00:00", fire=5),
    ]
    repo = _repo_with_rows(page1)
    svc = FeedService(repo)
    r1 = await svc.fetch(sort="hot", ticker=None, limit=2, cursor=None)
    assert r1.next_cursor

    # 2페이지: 다른 행 반환하도록 mock 갱신
    page2 = [_raw("p3", "2026-05-27T12:00:01+00:00", fire=3)]
    repo.cli.select.return_value = page2
    r2 = await svc.fetch(sort="hot", ticker=None, limit=2, cursor=r1.next_cursor)
    assert [p.id for p in r2.posts] == ["p3"]
    assert r2.next_cursor is None  # 마지막 페이지
