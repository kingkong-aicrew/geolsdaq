"""지수착시(Phase 4) 단위 테스트.

검증 (설계 B-3 시나리오):
- compute_breadth: 상승/하락/보합 집계 + 중앙값 검산 (up+down+flat=total)
- breadth_row: illusion_gap = index_change_pct - median_change_pct 검산
- fetch_index.rows_from_closes: 등락률 = 전일 대비, 첫 행 None
- build_headline: 가드레일("사라/추천/오를 것/매수/팔아라") 0건 (정규식 검출)
- IndexIllusionService: latest/series 조합, 빈 시계열, 미적재 503

pykrx 미의존(집계·변환은 순수 함수). 서비스는 IndexRepository mock.
"""
from __future__ import annotations

import re
from datetime import date

import pytest

from ..batch.compute_breadth import (
    Breadth,
    breadth_row,
    compute_breadth,
)
from ..batch.fetch_index import rows_from_closes
from ..repositories.index_repo import BreadthRow
from ..services.index_illusion import (
    BreadthUnavailableError,
    IndexIllusionService,
    build_headline,
)

# 가드레일 — 투자 권유 표현(이 단어가 headline 에 있으면 위반)
_GUARDRAIL = re.compile(r"(사라|사세요|추천|오를\s*것|매수|매도|팔아|담아)")


# ---------- compute_breadth (집계) ----------


def test_compute_breadth_basic():
    """상승 2 하락 2 보합 1 → 집계·중앙값 검산."""
    # 등락률: +3, +1, 0, -1, -2  → 중앙값 0
    b = compute_breadth([3.0, 1.0, 0.0, -1.0, -2.0])
    assert b.total_count == 5
    assert b.up_count == 2
    assert b.down_count == 2
    assert b.flat_count == 1
    assert b.up_count + b.down_count + b.flat_count == b.total_count
    assert b.up_ratio == round(2 / 5, 4)
    assert b.median_change_pct == 0.0


def test_compute_breadth_median_even():
    """짝수 표본 → 중앙값은 두 중앙값 평균."""
    b = compute_breadth([10.0, 2.0, -2.0, -10.0])  # 중앙 2개: 2, -2 → 0
    assert b.total_count == 4
    assert b.median_change_pct == 0.0
    b2 = compute_breadth([4.0, 2.0])  # (4+2)/2 = 3
    assert b2.median_change_pct == 3.0


def test_compute_breadth_empty():
    """빈 입력 → 0 분할 방어."""
    b = compute_breadth([])
    assert b.total_count == 0
    assert b.up_ratio == 0.0
    assert b.median_change_pct == 0.0


def test_breadth_row_illusion_gap():
    """illusion_gap = index_change_pct - median_change_pct 검산."""
    b = Breadth(
        total_count=100,
        up_count=34,
        down_count=60,
        flat_count=6,
        up_ratio=0.34,
        median_change_pct=-0.85,
    )
    row = breadth_row("KR_KOSPI", date(2026, 6, 18), 1.24, b)
    assert row["market"] == "KR_KOSPI"
    assert row["date"] == "2026-06-18"
    assert row["index_change_pct"] == 1.24
    assert row["total_count"] == 100
    # 1.24 - (-0.85) = 2.09
    assert row["illusion_gap"] == 2.09
    assert row["up_ratio"] == 0.34


# ---------- fetch_index (지수 시계열 변환) ----------


def test_rows_from_closes_change_pct():
    """등락률 = 전일 대비. 첫 행은 직전값 없어 None."""
    closes = [
        (date(2026, 6, 16), 2500.0),
        (date(2026, 6, 17), 2525.0),  # +1%
        (date(2026, 6, 18), 2500.0),  # 약 -0.99%
    ]
    rows = rows_from_closes("KOSPI", "코스피", closes)
    assert len(rows) == 3
    assert rows[0]["change_pct"] is None
    assert rows[1]["change_pct"] == 1.0
    assert rows[2]["change_pct"] == round((2500 - 2525) / 2525 * 100, 4)
    # 날짜 오름차순 보장
    assert [r["date"] for r in rows] == [
        "2026-06-16",
        "2026-06-17",
        "2026-06-18",
    ]


def test_rows_from_closes_unsorted_and_invalid():
    """입력이 뒤섞여 있어도 정렬 + close<=0 제거."""
    closes = [
        (date(2026, 6, 18), 2500.0),
        (date(2026, 6, 16), 2400.0),
        (date(2026, 6, 17), 0.0),  # 제거
    ]
    rows = rows_from_closes("KOSDAQ", "코스닥", closes)
    assert len(rows) == 2
    assert rows[0]["date"] == "2026-06-16"
    assert rows[1]["date"] == "2026-06-18"
    assert rows[0]["change_pct"] is None
    assert rows[0]["index_code"] == "KOSDAQ"


# ---------- build_headline (가드레일) ----------


def _row(
    *,
    market="KR_KOSPI",
    index_change_pct=1.24,
    total=120,
    up=41,
    down=73,
    flat=6,
    median=-0.85,
) -> BreadthRow:
    up_ratio = round(up / total, 4) if total else 0.0
    gap = round(index_change_pct - median, 4)
    return BreadthRow(
        market=market,
        date=date(2026, 6, 18),
        index_change_pct=index_change_pct,
        total_count=total,
        up_count=up,
        down_count=down,
        flat_count=flat,
        up_ratio=up_ratio,
        median_change_pct=median,
        illusion_gap=gap,
    )


def test_headline_strong_illusion_no_guardrail():
    """강한 착시(지수↑·대다수↓) → 강조 카피, 투자 권유 0."""
    h = build_headline(_row(index_change_pct=1.24, up=41, down=73, median=-0.85))
    assert "코스피" in h
    assert "+1.24%" in h
    assert not _GUARDRAIL.search(h), f"가드레일 위반: {h}"


def test_headline_all_tone_branches_guardrail():
    """4개 톤 분기 모두 가드레일 통과."""
    rows = [
        _row(index_change_pct=2.0, up=30, down=80, median=-1.0),    # 강
        _row(index_change_pct=0.8, up=55, down=60, median=0.1),     # 중
        _row(index_change_pct=-1.2, up=70, down=45, median=-0.3),   # 역착시
        _row(index_change_pct=0.1, up=60, down=55, median=0.05),    # 약
    ]
    for r in rows:
        h = build_headline(r)
        assert h, "headline 비어있음"
        assert not _GUARDRAIL.search(h), f"가드레일 위반: {h}"
        # 지수 등락률은 항상 노출(사실)
        assert "%" in h


def test_headline_no_division_by_zero():
    """total=0 (이론상) 이어도 죽지 않음."""
    h = build_headline(_row(total=0, up=0, down=0, flat=0, median=0.0))
    assert h
    assert not _GUARDRAIL.search(h)


# ---------- IndexIllusionService (조합) ----------


class _FakeRepo:
    def __init__(self, *, latest=None, on=None, series=None):
        self._latest = latest
        self._on = on
        self._series = series or []

    async def get_latest_breadth(self, market):
        return self._latest

    async def get_breadth_on(self, market, target):
        return self._on

    async def get_breadth_series(self, market, days):
        return self._series[:days]


@pytest.mark.asyncio
async def test_service_latest_ok():
    repo = _FakeRepo(latest=_row())
    svc = IndexIllusionService(repo)
    res = await svc.get_illusion(market="KR_KOSPI", date_str="latest")
    assert res.market == "KR_KOSPI"
    assert res.name == "코스피"
    assert res.date == date(2026, 6, 18)
    # illusion_gap 일관성: index - median
    assert abs(res.illusion_gap - (res.index_change_pct - res.median_change_pct)) < 0.01
    assert res.headline
    assert res.disclaimer


@pytest.mark.asyncio
async def test_service_latest_unavailable_503():
    repo = _FakeRepo(latest=None)
    svc = IndexIllusionService(repo)
    with pytest.raises(BreadthUnavailableError):
        await svc.get_illusion(market="KR_KOSPI", date_str="latest")


@pytest.mark.asyncio
async def test_service_bad_date_raises_valueerror():
    repo = _FakeRepo()
    svc = IndexIllusionService(repo)
    with pytest.raises(ValueError):
        await svc.get_illusion(market="KR_KOSPI", date_str="2026/06/18")


@pytest.mark.asyncio
async def test_service_specific_date():
    repo = _FakeRepo(on=_row(market="KR_KOSDAQ"))
    svc = IndexIllusionService(repo)
    res = await svc.get_illusion(market="KR_KOSDAQ", date_str="2026-06-18")
    assert res.market == "KR_KOSDAQ"
    assert res.name == "코스닥"


@pytest.mark.asyncio
async def test_service_series_ordering_and_limit():
    """series: 최대 days 개, 날짜 오름차순(repo 가 정렬해 반환)."""
    series = [
        _row(),
        _row(),
        _row(),
    ]
    repo = _FakeRepo(series=series)
    svc = IndexIllusionService(repo)
    res = await svc.get_series(market="KR_KOSPI", days=2)
    assert len(res.points) == 2
    assert res.name == "코스피"
    assert res.disclaimer


@pytest.mark.asyncio
async def test_service_series_empty():
    """집계 0건이어도 200(points=[])."""
    repo = _FakeRepo(series=[])
    svc = IndexIllusionService(repo)
    res = await svc.get_series(market="KR_KOSPI", days=20)
    assert res.points == []
    assert res.disclaimer
