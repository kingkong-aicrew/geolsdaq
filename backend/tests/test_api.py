"""FastAPI 통합 테스트 — TestClient + 의존성 오버라이드."""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

# 테스트용 env (config.py 가 읽음)
os.environ["SUPABASE_URL"] = "http://test.local"
os.environ["SUPABASE_ANON_KEY"] = "test-anon-key"
os.environ["SUPABASE_SERVICE_KEY"] = "test-service-key"

from ..config import reset_settings_for_tests
from ..main import (
    app,
    get_calculator,
    get_feed_service,
    get_index_illusion_service,
    get_leaderboard_service,
    get_parallel_service,
    get_post_service,
    get_price_repo,
    get_reaction_service,
    get_stash_repo,
    get_stash_service,
)
from ..models.schemas import (
    CalculateResponse,
    FeedResponse,
    IndexIllusionResponse,
    IndexSeriesPoint,
    IndexSeriesResponse,
    LeaderboardEntry,
    LeaderboardResponse,
    ParallelDiff,
    ParallelResponse,
    PostCard,
    PostCreateResponse,
    PostDetailResponse,
    ReactResponse,
    StashResponse,
)
from ..repositories.stash import StashRow
from ..services.calculator import TickerNotFoundError
from ..services.index_illusion import BreadthUnavailableError
from ..services.posts import CaptionRejectedError, PostNotFoundError

reset_settings_for_tests()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _override_deps():
    """모든 외부 의존성 mock."""
    fake_calc = AsyncMock()
    fake_calc.calculate.return_value = CalculateResponse(
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
    fake_lead = AsyncMock()
    fake_lead.fetch.return_value = LeaderboardResponse(
        sort="amount",
        period="month",
        ticker=None,
        entries=[
            LeaderboardEntry(
                id="11111111-1111-1111-1111-111111111111",
                created_at=datetime.now(timezone.utc),
                ticker="000660",
                name="SK하이닉스",
                qty=10,
                buy_date=date(2024, 1, 1),
                profit_amount=100_000.0,
                profit_pct=5.0,
            )
        ],
        disclaimer="전일 종가 기준 · 투자 자문 아님",
    )
    fake_stash_svc = AsyncMock()
    fake_stash_svc.submit.return_value = StashResponse(
        id="11111111-1111-1111-1111-111111111111",
        profit_amount=100_000.0,
        profit_pct=5.0,
        disclaimer="전일 종가 기준 · 투자 자문 아님",
    )
    fake_parallel_svc = AsyncMock()
    _mine = CalculateResponse(
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
    _alt = CalculateResponse(
        ticker="005930",
        name="삼성전자",
        market="KR",
        qty=10,
        buy_date=date(2024, 1, 1),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 26),
        price_period_start=80_000.0,
        price_period_end=100_000.0,
        profit_amount_krw=200_000.0,
        profit_pct=25.0,
        disclaimer="전일 종가 기준 · 투자 자문 아님",
    )
    fake_parallel_svc.compare.return_value = ParallelResponse(
        mine=_mine,
        alt=_alt,
        diff=ParallelDiff(
            amount_delta_krw=100_000.0, pct_delta=20.0, verdict="alt_better"
        ),
        disclaimer="전일 종가 기준 · 투자 자문 아님",
    )

    # ---- Phase B 커뮤니티 mock ----
    fake_post_svc = AsyncMock()
    fake_post_svc.create.return_value = PostCreateResponse(
        id="22222222-2222-2222-2222-222222222222",
        created_at=datetime(2026, 5, 27, 12, tzinfo=timezone.utc),
        ticker="000660",
        name="SK하이닉스",
        profit_amount=100_000.0,
        profit_pct=5.0,
        caption="이번 달 두 번째 월급",
        nickname="개미",
        fire_count=0,
        clap_count=0,
        cry_count=0,
        origin="direct",
        disclaimer="전일 종가 기준 · 투자 자문 아님",
    )
    fake_post_svc.get_detail.return_value = PostDetailResponse(
        id="22222222-2222-2222-2222-222222222222",
        created_at=datetime(2026, 5, 27, 12, tzinfo=timezone.utc),
        ticker="000660",
        name="SK하이닉스",
        qty=10,
        buy_date=date(2024, 1, 1),
        profit_amount=100_000.0,
        profit_pct=5.0,
        caption="이번 달 두 번째 월급",
        nickname="개미",
        fire_count=3,
        clap_count=1,
        cry_count=0,
        origin="direct",
        my_reaction="fire",
        disclaimer="전일 종가 기준 · 투자 자문 아님",
    )

    fake_feed_svc = AsyncMock()
    fake_feed_svc.fetch.return_value = FeedResponse(
        sort="hot",
        ticker=None,
        posts=[
            PostCard(
                id="22222222-2222-2222-2222-222222222222",
                created_at=datetime(2026, 5, 27, 12, tzinfo=timezone.utc),
                ticker="000660",
                name="SK하이닉스",
                qty=10,
                buy_date=date(2024, 1, 1),
                profit_amount=100_000.0,
                profit_pct=5.0,
                caption="자랑",
                nickname=None,
                fire_count=5,
                clap_count=0,
                cry_count=0,
                origin="direct",
            )
        ],
        next_cursor="eyJjcmVhdGVkX2F0IjoiMjAyNi0wNS0yN1QxMjowMDowMCJ9",
        disclaimer="전일 종가 기준 · 투자 자문 아님",
    )

    fake_reaction_svc = AsyncMock()
    fake_reaction_svc.react.return_value = ReactResponse(
        post_id="22222222-2222-2222-2222-222222222222",
        fire_count=1,
        clap_count=0,
        cry_count=0,
        my_reaction="fire",
    )

    # ---- Phase 4 지수착시 mock ----
    fake_index_svc = AsyncMock()
    fake_index_svc.get_illusion.return_value = IndexIllusionResponse(
        market="KR_KOSPI",
        name="코스피",
        date=date(2026, 6, 18),
        index_change_pct=1.24,
        total_count=120,
        up_count=41,
        down_count=73,
        flat_count=6,
        up_ratio=0.3417,
        median_change_pct=-0.85,
        illusion_gap=2.09,
        headline="코스피는 +1.24%인데, 종목 10개 중 6개는 빨간불",
        disclaimer="전일 종가 기준 · 투자 자문 아님",
    )
    fake_index_svc.get_series.return_value = IndexSeriesResponse(
        market="KR_KOSPI",
        name="코스피",
        points=[
            IndexSeriesPoint(
                date=date(2026, 6, 17),
                index_change_pct=0.5,
                up_ratio=0.45,
                illusion_gap=0.9,
            ),
            IndexSeriesPoint(
                date=date(2026, 6, 18),
                index_change_pct=1.24,
                up_ratio=0.3417,
                illusion_gap=2.09,
            ),
        ],
        disclaimer="전일 종가 기준 · 투자 자문 아님",
    )

    fake_stash_repo = AsyncMock()
    fake_stash_repo.get.return_value = StashRow(
        id="11111111-1111-1111-1111-111111111111",
        created_at=datetime(2026, 5, 27, 12, tzinfo=timezone.utc),
        ticker="000660",
        name="SK하이닉스",
        qty=10,
        buy_date=date(2024, 1, 1),
        profit_amount=100_000.0,
        profit_pct=5.0,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 26),
        calc_snapshot={"price_period_start": 200_000, "price_period_end": 210_000, "market": "KR"},
    )

    app.dependency_overrides[get_calculator] = lambda: fake_calc
    app.dependency_overrides[get_leaderboard_service] = lambda: fake_lead
    app.dependency_overrides[get_stash_service] = lambda: fake_stash_svc
    app.dependency_overrides[get_stash_repo] = lambda: fake_stash_repo
    app.dependency_overrides[get_parallel_service] = lambda: fake_parallel_svc
    app.dependency_overrides[get_post_service] = lambda: fake_post_svc
    app.dependency_overrides[get_feed_service] = lambda: fake_feed_svc
    app.dependency_overrides[get_reaction_service] = lambda: fake_reaction_svc
    app.dependency_overrides[get_index_illusion_service] = lambda: fake_index_svc
    app.dependency_overrides[get_price_repo] = lambda: AsyncMock()
    yield
    app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_calculate_ok(client):
    r = client.post(
        "/calculate",
        json={"ticker": "000660", "qty": 10, "buy_date": "2024-01-01"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["profit_amount_krw"] == 100_000.0
    assert body["disclaimer"] == "전일 종가 기준 · 투자 자문 아님"


def test_calculate_validation_error(client):
    r = client.post(
        "/calculate",
        json={"ticker": "000660", "qty": 0, "buy_date": "2024-01-01"},
    )
    assert r.status_code == 422


def test_leaderboard_default(client):
    r = client.get("/leaderboard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sort"] == "amount"
    assert body["period"] == "month"
    assert len(body["entries"]) == 1


def test_leaderboard_ticker_filter(client):
    r = client.get("/leaderboard?ticker=000660&sort=amount")
    assert r.status_code == 200


def test_leaderboard_invalid_sort_returns_400(client):
    r = client.get("/leaderboard?sort=xxx")
    assert r.status_code == 400


def test_stash_ok(client):
    r = client.post(
        "/stash",
        json={"ticker": "000660", "qty": 10, "buy_date": "2024-01-01"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "id" in body
    assert body["disclaimer"]


def test_parallel_ok(client):
    r = client.post(
        "/parallel",
        json={
            "ticker": "000660",
            "qty": 10,
            "buy_date": "2024-01-01",
            "alt_ticker": "005930",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mine"]["ticker"] == "000660"
    assert body["alt"]["ticker"] == "005930"
    assert body["diff"]["verdict"] == "alt_better"
    # verdict ↔ amount_delta 부호 정합
    assert body["diff"]["amount_delta_krw"] > 0
    assert body["disclaimer"]


def test_parallel_validation_error(client):
    """alt_ticker 누락 → 422 (Pydantic)."""
    r = client.post(
        "/parallel",
        json={"ticker": "000660", "qty": 10, "buy_date": "2024-01-01"},
    )
    assert r.status_code == 422


def test_parallel_alt_not_found_404(client, _override_deps):
    """대체 종목 미존재 → calculate 가 TickerNotFoundError → 404 한글."""
    failing = AsyncMock()
    failing.compare.side_effect = TickerNotFoundError(
        "종목 'ZZZZ'을(를) 찾을 수 없습니다."
    )
    app.dependency_overrides[get_parallel_service] = lambda: failing
    r = client.post(
        "/parallel",
        json={
            "ticker": "000660",
            "qty": 10,
            "buy_date": "2024-01-01",
            "alt_ticker": "ZZZZ",
        },
    )
    assert r.status_code == 404, r.text
    assert "찾을 수 없" in r.json()["detail"]


def test_share_ok(client):
    r = client.get("/share/11111111-1111-1111-1111-111111111111")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ticker"] == "000660"
    assert body["og_image_url"].endswith("/api/og/11111111-1111-1111-1111-111111111111")


def test_share_not_found(client, _override_deps):
    fake_repo = AsyncMock()
    fake_repo.get.return_value = None
    app.dependency_overrides[get_stash_repo] = lambda: fake_repo
    r = client.get("/share/zzz")
    assert r.status_code == 404


def test_http_error_handler_returns_503(client, _override_deps):
    """P1-1: 어떤 라우트에서든 raw httpx 예외가 떠도 503 + 한국어 메시지로 정규화."""
    import httpx

    failing = AsyncMock()
    failing.calculate.side_effect = httpx.ConnectError("supabase down")
    app.dependency_overrides[get_calculator] = lambda: failing
    r = client.post(
        "/calculate",
        json={"ticker": "000660", "qty": 10, "buy_date": "2024-01-01"},
    )
    assert r.status_code == 503, r.text
    body = r.json()
    assert "시세 서비스" in body["detail"]
    assert "다시 시도" in body["detail"]


# ---------- Phase B 커뮤니티 라우트 ----------


def test_create_post_ok(client):
    r = client.post(
        "/posts",
        json={
            "ticker": "000660",
            "qty": 10,
            "buy_date": "2024-01-01",
            "caption": "이번 달 두 번째 월급",
            "nickname": "개미",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"]
    assert body["fire_count"] == 0 and body["clap_count"] == 0
    assert body["caption"] == "이번 달 두 번째 월급"
    assert body["disclaimer"]


def test_create_post_caption_too_long_422(client):
    """61자 → Pydantic max_length 위반(422). 서비스 도달 전 차단."""
    r = client.post(
        "/posts",
        json={"ticker": "000660", "qty": 10, "buy_date": "2024-01-01", "caption": "가" * 61},
    )
    assert r.status_code == 422, r.text


def test_create_post_caption_url_rejected_400(client, _override_deps):
    """URL 캡션 → 서비스 CaptionRejectedError → 400 한글."""
    failing = AsyncMock()
    failing.create.side_effect = CaptionRejectedError("링크·멘션은 넣을 수 없어요")
    app.dependency_overrides[get_post_service] = lambda: failing
    r = client.post(
        "/posts",
        json={
            "ticker": "000660",
            "qty": 10,
            "buy_date": "2024-01-01",
            "caption": "http://spam.com 와요",
        },
    )
    assert r.status_code == 400, r.text
    assert "링크" in r.json()["detail"]


def test_feed_hot(client):
    r = client.get("/feed?sort=hot&limit=20")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sort"] == "hot"
    assert len(body["posts"]) == 1
    assert body["posts"][0]["fire_count"] == 5
    assert body["next_cursor"]
    assert body["disclaimer"]


def test_feed_invalid_sort_400(client):
    r = client.get("/feed?sort=xxx")
    assert r.status_code == 400


def test_feed_invalid_limit_400(client):
    r = client.get("/feed?limit=999")
    assert r.status_code == 400


def test_react_ok(client):
    r = client.post(
        "/posts/22222222-2222-2222-2222-222222222222/react",
        json={"type": "fire", "visitor_id": "visitor-abc-123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fire_count"] == 1
    assert body["my_reaction"] == "fire"


def test_react_invalid_type_422(client):
    r = client.post(
        "/posts/22222222-2222-2222-2222-222222222222/react",
        json={"type": "love", "visitor_id": "visitor-abc-123"},
    )
    assert r.status_code == 422


def test_react_post_not_found_404(client, _override_deps):
    failing = AsyncMock()
    failing.react.side_effect = PostNotFoundError("반응할 글을 찾을 수 없습니다: zzz")
    app.dependency_overrides[get_reaction_service] = lambda: failing
    r = client.post(
        "/posts/zzz/react",
        json={"type": "fire", "visitor_id": "visitor-abc-123"},
    )
    assert r.status_code == 404, r.text
    assert "찾을 수 없" in r.json()["detail"]


def test_get_post_ok(client):
    r = client.get("/posts/22222222-2222-2222-2222-222222222222?visitor_id=visitor-abc-123")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ticker"] == "000660"
    assert body["my_reaction"] == "fire"
    assert body["fire_count"] == 3


def test_get_post_not_found_404(client, _override_deps):
    failing = AsyncMock()
    failing.get_detail.side_effect = PostNotFoundError("글을 찾을 수 없습니다: zzz")
    app.dependency_overrides[get_post_service] = lambda: failing
    r = client.get("/posts/zzz")
    assert r.status_code == 404, r.text


# ---------- Phase 4 지수착시 라우트 ----------


def test_index_illusion_ok(client):
    r = client.get("/index/illusion?market=KR_KOSPI&date=latest")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["market"] == "KR_KOSPI"
    assert body["name"] == "코스피"
    assert body["index_change_pct"] == 1.24
    assert body["total_count"] == 120
    # illusion_gap = index - median 검산
    assert abs(body["illusion_gap"] - (body["index_change_pct"] - body["median_change_pct"])) < 0.01
    assert body["headline"]
    assert body["disclaimer"]
    # EOD 불변 → Cache-Control max-age>0
    cc = r.headers.get("cache-control", "")
    assert "max-age=" in cc
    assert int(cc.split("max-age=")[1].split(",")[0]) > 0


def test_index_illusion_headline_no_guardrail(client):
    """headline 에 투자 권유 표현 0건."""
    import re

    r = client.get("/index/illusion")
    assert r.status_code == 200
    h = r.json()["headline"]
    assert not re.search(r"(사라|추천|오를\s*것|매수|매도|팔아)", h), h


def test_index_illusion_invalid_market_400(client):
    r = client.get("/index/illusion?market=US_DOW")
    assert r.status_code == 400, r.text


def test_index_illusion_unavailable_503(client, _override_deps):
    """집계 미적재 → BreadthUnavailableError → 503 한글."""
    failing = AsyncMock()
    failing.get_illusion.side_effect = BreadthUnavailableError(
        "아직 집계된 시장 데이터가 없어요. 잠시 후 다시 시도해 주세요."
    )
    app.dependency_overrides[get_index_illusion_service] = lambda: failing
    r = client.get("/index/illusion?market=KR_KOSPI&date=latest")
    assert r.status_code == 503, r.text
    assert "집계" in r.json()["detail"]


def test_index_illusion_bad_date_400(client, _override_deps):
    """잘못된 date 형식 → ValueError → 400."""
    failing = AsyncMock()
    failing.get_illusion.side_effect = ValueError(
        "date 는 'latest' 또는 YYYY-MM-DD 형식이어야 해요"
    )
    app.dependency_overrides[get_index_illusion_service] = lambda: failing
    r = client.get("/index/illusion?date=2026/06/18")
    assert r.status_code == 400, r.text


def test_index_series_ok(client):
    r = client.get("/index/illusion/series?market=KR_KOSPI&days=20")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["market"] == "KR_KOSPI"
    assert len(body["points"]) == 2
    # 날짜 오름차순
    assert body["points"][0]["date"] <= body["points"][1]["date"]
    assert body["disclaimer"]
    assert "max-age=" in r.headers.get("cache-control", "")


def test_index_series_invalid_days_400(client):
    r = client.get("/index/illusion/series?days=999")
    assert r.status_code == 400, r.text


def test_index_series_zero_days_400(client):
    r = client.get("/index/illusion/series?days=0")
    assert r.status_code == 400, r.text


def test_comments_endpoint_absent(client):
    """스펙 금지: 댓글 엔드포인트 부재 확인 (404/405)."""
    r = client.post(
        "/posts/22222222-2222-2222-2222-222222222222/comments",
        json={"text": "hi"},
    )
    assert r.status_code in (404, 405), r.text
