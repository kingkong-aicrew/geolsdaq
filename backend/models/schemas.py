"""Pydantic 입/출력 스키마.

검증 위치:
- 가격 음수, 수량 0 등 비정상값 → 400 (Pydantic 자동)
- 종목 존재 여부 → 서비스 단에서 확인
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


SortKey = Literal["amount", "pct"]
PeriodKey = Literal["month"]
MarketKey = Literal["KR", "US"]


# ---------- /calculate ----------


class CalculateRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    qty: int = Field(..., ge=1, le=999_999)
    buy_date: date

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, v: str) -> str:
        # KR=6자리 숫자, US=알파벳 — 둘 다 대문자/그대로 유지
        return v.strip().upper()

    @field_validator("buy_date")
    @classmethod
    def _buy_date_range(cls, v: date) -> date:
        if v < date(2000, 1, 1):
            raise ValueError("buy_date 는 2000-01-01 이후여야 합니다")
        if v > date.today():
            raise ValueError("buy_date 는 오늘 이전이어야 합니다")
        return v


class CalculateResponse(BaseModel):
    ticker: str
    name: str
    market: MarketKey
    qty: int
    buy_date: date

    # "이번 달" KST 1일 00:00 ~ 어제 EOD
    period_start: date
    period_end: date

    # 가격 (KRW)
    price_period_start: float
    price_period_end: float

    # 결과
    profit_amount_krw: float
    profit_pct: float            # ((end - start) / start * 100), 종목 자체 수익률

    disclaimer: str


# ---------- /parallel (평행우주 — 종목대체형) ----------


class ParallelRequest(BaseModel):
    """'만약 OO 샀다면' — 내 종목(ticker) vs 대체 종목(alt_ticker).

    비교 기준: 주식 수 고정(qty 동일, 설계 Q1=A). 같은 주식 수로
    내가 산 종목과 대체 종목의 이번 달 수익을 나란히 재계산한다.
    """

    ticker: str = Field(..., min_length=1, max_length=12)
    qty: int = Field(..., ge=1, le=999_999)
    buy_date: date
    alt_ticker: str = Field(..., min_length=1, max_length=12)

    @field_validator("ticker", "alt_ticker")
    @classmethod
    def _normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("buy_date")
    @classmethod
    def _buy_date_range(cls, v: date) -> date:
        if v < date(2000, 1, 1):
            raise ValueError("buy_date 는 2000-01-01 이후여야 합니다")
        if v > date.today():
            raise ValueError("buy_date 는 오늘 이전이어야 합니다")
        return v


Verdict = Literal["alt_better", "mine_better", "tie"]


class ParallelDiff(BaseModel):
    """대체 종목이 내 종목보다 얼마나 더(덜) 벌었는지."""

    amount_delta_krw: float       # alt.profit - mine.profit (양수=대체가 더 벌었음)
    pct_delta: float              # alt.profit_pct - mine.profit_pct
    verdict: Verdict              # alt_better | mine_better | tie


class ParallelResponse(BaseModel):
    """평행우주 결과 — mine/alt 동일 구조 + diff.

    mine/alt 모두 CalculateResponse 골격(개별 disclaimer 제거). 최상위
    disclaimer 1개만 노출.
    """

    mine: CalculateResponse
    alt: CalculateResponse
    diff: ParallelDiff
    disclaimer: str


# ---------- /leaderboard ----------


class LeaderboardEntry(BaseModel):
    id: str
    created_at: datetime
    ticker: str
    name: str
    qty: int
    buy_date: date
    profit_amount: float
    profit_pct: float


class LeaderboardResponse(BaseModel):
    sort: SortKey
    period: PeriodKey
    ticker: Optional[str] = None
    entries: list[LeaderboardEntry]
    disclaimer: str


# ---------- /stash ----------


class StashRequest(BaseModel):
    """클라이언트가 /calculate 결과를 그대로 등재.

    서버는 다시 계산하여 검증 (위·변조 차단).
    """

    ticker: str = Field(..., min_length=1, max_length=12)
    qty: int = Field(..., ge=1, le=999_999)
    buy_date: date

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()


class StashResponse(BaseModel):
    id: str
    profit_amount: float
    profit_pct: float
    disclaimer: str


# ---------- /share/{id} ----------


class ShareResponse(BaseModel):
    id: str
    created_at: datetime
    ticker: str
    name: str
    qty: int
    buy_date: date
    profit_amount: float
    profit_pct: float
    period_start: date
    period_end: date
    og_image_url: str
    disclaimer: str


# ---------- 커뮤니티 (Phase B — posts / feed / reactions) ----------

# 한 줄 자랑(캡션)에서 차단할 패턴:
#   - URL: http(s):// 또는 www. 또는 점 도메인 (스팸 링크 차단)
#   - 멘션: @id (멘션·스레드 유도 차단 — 스펙: @멘션 ✕)
# 서비스 계층(PostService)에서 이 정규식으로 400 처리. 여기엔 정의만 둔다.
_URL_PATTERN = re.compile(
    r"(https?://|www\.|[\w-]+\.(com|net|org|kr|io|co|gg|me|ly|info|biz|xyz|shop|store)\b)",
    re.IGNORECASE,
)
_MENTION_PATTERN = re.compile(r"@\w")

ReactionType = Literal["fire", "clap", "cry"]
FeedSort = Literal["latest", "hot"]
PostOrigin = Literal["direct", "parallel"]


class PostCreate(BaseModel):
    """피드 등재 요청. 서버가 재계산하여 검증(위·변조 차단) 후 insert.

    caption/nickname 길이는 1차로 Pydantic 이 막고(422), 서비스 계층이 trim 후
    URL/@ 필터로 한 번 더 검사한다(400 한글). 이중 검증 의도적.
    """

    ticker: str = Field(..., min_length=1, max_length=12)
    qty: int = Field(..., ge=1, le=999_999)
    buy_date: date
    caption: Optional[str] = Field(default=None, max_length=60)
    nickname: Optional[str] = Field(default=None, max_length=12)
    origin: PostOrigin = "direct"

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("buy_date")
    @classmethod
    def _buy_date_range(cls, v: date) -> date:
        if v < date(2000, 1, 1):
            raise ValueError("buy_date 는 2000-01-01 이후여야 합니다")
        if v > date.today():
            raise ValueError("buy_date 는 오늘 이전이어야 합니다")
        return v


class PostCard(BaseModel):
    """피드 카드 + 단건 조회 공통 표시 모델."""

    id: str
    created_at: datetime
    ticker: str
    name: str
    qty: int
    buy_date: date
    profit_amount: float
    profit_pct: float
    caption: Optional[str] = None
    nickname: Optional[str] = None
    fire_count: int
    clap_count: int
    cry_count: int
    origin: PostOrigin


class PostCreateResponse(BaseModel):
    """등재 직후 응답 — 새 카드 + 면책."""

    id: str
    created_at: datetime
    ticker: str
    name: str
    profit_amount: float
    profit_pct: float
    caption: Optional[str] = None
    nickname: Optional[str] = None
    fire_count: int = 0
    clap_count: int = 0
    cry_count: int = 0
    origin: PostOrigin
    disclaimer: str


class PostDetailResponse(PostCard):
    """단건 조회 — 카드 + (옵션)내 반응 + 면책."""

    my_reaction: Optional[ReactionType] = None
    disclaimer: str


class FeedResponse(BaseModel):
    sort: FeedSort
    ticker: Optional[str] = None
    posts: list[PostCard]
    next_cursor: Optional[str] = None
    disclaimer: str


class ReactRequest(BaseModel):
    type: ReactionType
    visitor_id: str = Field(..., min_length=8, max_length=64)


class ReactResponse(BaseModel):
    post_id: str
    fire_count: int
    clap_count: int
    cry_count: int
    my_reaction: ReactionType


# ---------- 지수착시 (Phase 4 — /index/illusion) ----------

IndexMarketKey = Literal["KR_KOSPI", "KR_KOSDAQ"]


class IndexIllusionResponse(BaseModel):
    """지수 등락 vs 개별종목 등락 분포의 괴리(착시).

    headline 은 백엔드가 데이터로 생성한 가드레일 통과 카피(사실 서술만).
    total_count 를 항상 노출해 "모수 N개 중" 으로 정직하게(외삽 ✕).
    """

    market: IndexMarketKey
    name: str                          # '코스피' | '코스닥'
    date: date
    index_change_pct: float            # 지수 등락률(%)
    total_count: int                   # 집계 모수
    up_count: int
    down_count: int
    flat_count: int
    up_ratio: float                    # up / total (0~1)
    median_change_pct: float           # 개별종목 등락률 중앙값
    illusion_gap: float                # index_change_pct - median_change_pct (착시 강도)
    headline: str                      # 데이터 기반 동적 카피(가드레일 통과)
    disclaimer: str


class IndexSeriesPoint(BaseModel):
    date: date
    index_change_pct: float
    up_ratio: float
    illusion_gap: float


class IndexSeriesResponse(BaseModel):
    """최근 N일 illusion_gap 추이(스파크라인용)."""

    market: IndexMarketKey
    name: str
    points: list[IndexSeriesPoint]     # 날짜 오름차순
    disclaimer: str
