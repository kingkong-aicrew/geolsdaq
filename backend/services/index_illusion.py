"""지수착시 — "지수는 올랐는데 내 종목만 녹았다" 괴리 폭로.

설계 B (서버가 진실):
- index_breadth(배치 사전 계산)를 조회해 응답 조립.
- headline 은 데이터 기반 동적 카피를 **백엔드가 규칙으로** 생성(LLM ✕,
  프론트 하드코딩 ✕). illusion_gap 구간별 톤(강/중/약)으로 분기.
- 가드레일: "사라/추천/오를 것/매수/팔아라" 등 투자 권유 표현 0건
  (사실 서술만). build_headline 은 순수 함수 → 테스트로 가드레일 검증.

엔드포인트:
- GET /index/illusion?market=&date=latest|YYYY-MM-DD → IndexIllusionResponse
- GET /index/illusion/series?market=&days=N → IndexSeriesResponse
"""
from __future__ import annotations

from datetime import date as date_cls
from typing import Optional

from ..config import get_settings
from ..models.schemas import (
    IndexIllusionResponse,
    IndexSeriesPoint,
    IndexSeriesResponse,
)
from ..repositories.index_repo import BreadthRow, IndexRepository

# market → 표시명 (응답 name)
_MARKET_NAME = {
    "KR_KOSPI": "코스피",
    "KR_KOSDAQ": "코스닥",
}


class BreadthUnavailableError(Exception):
    """집계 데이터 없음 — main.py 에서 503 한글로 정규화.

    배치(compute_breadth)가 아직 1회도 안 돌았거나 해당 일자가 휴장이면 발생.
    """


def _ratio_to_tenths(ratio: float) -> int:
    """비율(0~1) → '10개 중 N개' 의 N(0~10). 반올림."""
    n = round(ratio * 10)
    return max(0, min(10, n))


def build_headline(b: BreadthRow) -> str:
    """등락 분포 → 가드레일 통과 동적 카피(사실 서술만, 투자 권유 ✕).

    톤 분기(illusion_gap = 지수등락 - 중앙값):
    - 강(gap >= 1.5, 지수↑·종목 다수↓): "지수만 웃었다" 류 강조
    - 중(0.5 <= gap < 1.5): 괴리 환기
    - 약(gap < 0.5): 지수와 체감 대체로 일치
    숫자(지수 등락률·하락종목 비율)는 항상 사실 그대로 노출.
    """
    name = _MARKET_NAME.get(b.market, b.market)
    idx = b.index_change_pct
    down_tenths = _ratio_to_tenths(b.down_count / b.total_count) if b.total_count else 0
    idx_str = f"{idx:+.2f}%"

    # 지수가 올랐는데 절반 이상 하락 → 전형적 착시
    index_up = idx > 0
    most_down = b.total_count > 0 and b.down_count > b.up_count

    if b.illusion_gap >= 1.5 and index_up and most_down:
        return f"{name}는 {idx_str}인데, 종목 10개 중 {down_tenths}개는 빨간불"
    if b.illusion_gap >= 0.5 and index_up:
        return f"{name}는 {idx_str}, 그런데 오른 종목은 절반이 안 돼요"
    if not index_up and b.illusion_gap <= -0.5:
        # 지수는 빠졌는데 개별은 덜 빠짐(역착시)
        return f"{name}는 {idx_str}, 그래도 버틴 종목이 더 많았어요"
    # 약한 괴리 — 사실만
    return f"{name} {idx_str} · 오른 종목 {_ratio_to_tenths(b.up_ratio)} / 내린 종목 {down_tenths} (10개 중)"


class IndexIllusionService:
    def __init__(self, repo: IndexRepository):
        self.repo = repo

    async def get_illusion(
        self, *, market: str, date_str: str
    ) -> IndexIllusionResponse:
        """latest(기본) 또는 특정 일자의 지수착시 1건."""
        if date_str == "latest":
            row = await self.repo.get_latest_breadth(market)
        else:
            try:
                d = date_cls.fromisoformat(date_str)
            except ValueError as e:
                raise ValueError("date 는 'latest' 또는 YYYY-MM-DD 형식이어야 해요") from e
            row = await self.repo.get_breadth_on(market, d)

        if row is None:
            raise BreadthUnavailableError(
                "아직 집계된 시장 데이터가 없어요. 잠시 후 다시 시도해 주세요."
            )

        s = get_settings()
        return IndexIllusionResponse(
            market=row.market,  # type: ignore[arg-type]
            name=_MARKET_NAME.get(row.market, row.market),
            date=row.date,
            index_change_pct=row.index_change_pct,
            total_count=row.total_count,
            up_count=row.up_count,
            down_count=row.down_count,
            flat_count=row.flat_count,
            up_ratio=row.up_ratio,
            median_change_pct=row.median_change_pct,
            illusion_gap=row.illusion_gap,
            headline=build_headline(row),
            disclaimer=s.disclaimer,
        )

    async def get_series(
        self, *, market: str, days: int
    ) -> IndexSeriesResponse:
        """최근 N일 illusion_gap 추이(스파크라인). 빈 시계열도 200(points=[])."""
        rows = await self.repo.get_breadth_series(market, days)
        points = [
            IndexSeriesPoint(
                date=r.date,
                index_change_pct=r.index_change_pct,
                up_ratio=r.up_ratio,
                illusion_gap=r.illusion_gap,
            )
            for r in rows
        ]
        s = get_settings()
        return IndexSeriesResponse(
            market=market,  # type: ignore[arg-type]
            name=_MARKET_NAME.get(market, market),
            points=points,
            disclaimer=s.disclaimer,
        )
