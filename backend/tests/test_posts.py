"""posts(PostService) 단위 테스트 — caption 필터·재계산·insert.

검증:
- caption trim 후 60자까지 OK, 61자 → CaptionRejectedError
- caption 에 URL(http/www/도메인)·@멘션 → CaptionRejectedError
- 정상 등재: 서버 재계산값으로 insert(위·변조 차단), 카운트 0
- 빈/공백 caption·nickname → None 정규화
- 단건 조회 미존재 → PostNotFoundError
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from ..models.schemas import CalculateResponse, PostCreate
from ..repositories.posts_repo import PostRow
from ..services.posts import (
    CaptionRejectedError,
    PostNotFoundError,
    PostService,
    _clean_caption,
    _clean_nickname,
)


def _calc_response() -> CalculateResponse:
    return CalculateResponse(
        ticker="000660",
        name="SK하이닉스",
        market="KR",
        qty=10,
        buy_date=date(2024, 1, 1),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 26),
        price_period_start=200_000.0,
        price_period_end=210_000.0,
        profit_amount_krw=100_000.0,
        profit_pct=5.0,
        disclaimer="전일 종가 기준 · 투자 자문 아님",
    )


def _post_row(caption=None, nickname=None) -> PostRow:
    return PostRow(
        id="11111111-1111-1111-1111-111111111111",
        created_at=datetime(2026, 5, 27, 12, tzinfo=timezone.utc),
        ticker="000660",
        name="SK하이닉스",
        qty=10,
        buy_date=date(2024, 1, 1),
        profit_amount=100_000.0,
        profit_pct=5.0,
        caption=caption,
        nickname=nickname,
        fire_count=0,
        clap_count=0,
        cry_count=0,
        origin="direct",
    )


# ---------- caption / nickname 순수 함수 ----------


def test_caption_60_ok():
    s = "가" * 60
    assert _clean_caption(s) == s


def test_caption_61_rejected():
    with pytest.raises(CaptionRejectedError) as ei:
        _clean_caption("가" * 61)
    assert "60자" in str(ei.value)


def test_caption_trim_then_length():
    """앞뒤 공백은 trim 후 길이 판정 — 공백 포함 62지만 trim 후 60 → OK."""
    assert _clean_caption("  " + "나" * 60 + "  ") == "나" * 60


@pytest.mark.parametrize(
    "bad",
    [
        "여기 좋아요 http://spam.com",
        "https://x.io 대박",
        "www.naver.com 가보세요",
        "수익 인증 spam.shop 임",
        "내 텔레 @hacker 로 와요",
        "@everyone 모여라",
    ],
)
def test_caption_url_or_mention_rejected(bad):
    with pytest.raises(CaptionRejectedError) as ei:
        _clean_caption(bad)
    assert "링크" in str(ei.value)


@pytest.mark.parametrize(
    "ok",
    [
        "이번 달 두 번째 월급 실화냐",
        "삼성전자 살걸 ㅠㅠ",
        "이메일 같은 건 없고 그냥 자랑",  # @ 없음
    ],
)
def test_caption_normal_ok(ok):
    assert _clean_caption(ok) == ok


def test_caption_empty_to_none():
    assert _clean_caption("") is None
    assert _clean_caption("   ") is None
    assert _clean_caption(None) is None


def test_nickname_trim_and_clip():
    assert _clean_nickname("  닉  ") == "닉"
    assert _clean_nickname("") is None
    assert _clean_nickname(None) is None
    # 12자 초과는 잘라냄(Pydantic 1차 방어 후 2차)
    assert _clean_nickname("가" * 20) == "가" * 12


# ---------- PostService.create ----------


@pytest.mark.asyncio
async def test_create_uses_server_recalc_and_zero_counts():
    """등재값은 서버 재계산 결과 + 카운트 0(위·변조·조작 차단)."""
    calc = AsyncMock()
    calc.calculate.return_value = _calc_response()
    repo = AsyncMock()
    repo.insert.return_value = _post_row(caption="자랑합니다", nickname="개미")

    svc = PostService(calc, repo)
    req = PostCreate(
        ticker="000660",
        qty=10,
        buy_date=date(2024, 1, 1),
        caption="자랑합니다",
        nickname="개미",
    )
    res = await svc.create(req, client_ip="1.2.3.4")

    # insert payload 검증 — 카운트 0 + ip_hash(평문 아님) + 재계산값
    payload = repo.insert.call_args.args[0]
    assert payload["fire_count"] == 0
    assert payload["clap_count"] == 0
    assert payload["cry_count"] == 0
    assert payload["profit_amount"] == 100_000.0
    assert payload["ip_hash"] and payload["ip_hash"] != "1.2.3.4"
    assert payload["caption"] == "자랑합니다"
    assert payload["origin"] == "direct"

    assert res.fire_count == 0
    assert res.disclaimer


@pytest.mark.asyncio
async def test_create_rejects_url_caption_before_calc():
    """URL 캡션은 계산·insert 전에 차단(낭비 방지)."""
    calc = AsyncMock()
    repo = AsyncMock()
    svc = PostService(calc, repo)
    req = PostCreate(
        ticker="000660",
        qty=10,
        buy_date=date(2024, 1, 1),
        caption="http://spam.com 와요",
    )
    with pytest.raises(CaptionRejectedError):
        await svc.create(req, client_ip="1.2.3.4")
    calc.calculate.assert_not_called()
    repo.insert.assert_not_called()


@pytest.mark.asyncio
async def test_create_parallel_origin():
    """origin=parallel 도 그대로 기록(평행우주 결과 등재)."""
    calc = AsyncMock()
    calc.calculate.return_value = _calc_response()
    repo = AsyncMock()
    repo.insert.return_value = _post_row()
    repo.insert.return_value.origin = "parallel"

    svc = PostService(calc, repo)
    req = PostCreate(
        ticker="000660", qty=10, buy_date=date(2024, 1, 1), origin="parallel"
    )
    res = await svc.create(req, client_ip="1.2.3.4")
    payload = repo.insert.call_args.args[0]
    assert payload["origin"] == "parallel"
    assert res.origin == "parallel"


@pytest.mark.asyncio
async def test_get_detail_not_found():
    calc = AsyncMock()
    repo = AsyncMock()
    repo.get.return_value = None
    svc = PostService(calc, repo)
    with pytest.raises(PostNotFoundError):
        await svc.get_detail("zzz")


@pytest.mark.asyncio
async def test_get_detail_with_my_reaction():
    calc = AsyncMock()
    repo = AsyncMock()
    repo.get.return_value = _post_row(caption="hi")
    repo.my_reaction.return_value = "fire"
    svc = PostService(calc, repo)
    res = await svc.get_detail("11111111-1111-1111-1111-111111111111", visitor_id="v1")
    assert res.my_reaction == "fire"
    assert res.caption == "hi"
    assert res.disclaimer
