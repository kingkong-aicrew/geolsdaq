"""FastAPI 엔트리 — 라우팅·미들웨어·DI 조립만.

가드 (security-qa public 6항목):
- API 키: env 만 (config.py 통과)
- 인증: 본 백엔드는 외부 유료 API 직호출 ✕ (Supabase 만) → 인증 게이트 불요
- Rate limit: slowapi (calc 30/m, stash 10/m)
- CORS: env 화이트리스트
- RLS: schema.sql 에서 처리 (코드 책임 ✕)
- 비용 한도: Supabase 무료 티어 + README 알람 가이드
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from .config import get_settings
from .models.schemas import (
    CalculateRequest,
    CalculateResponse,
    FeedResponse,
    IndexIllusionResponse,
    IndexSeriesResponse,
    LeaderboardResponse,
    ParallelRequest,
    ParallelResponse,
    PostCreate,
    PostCreateResponse,
    PostDetailResponse,
    ReactRequest,
    ReactResponse,
    ShareResponse,
    StashRequest,
    StashResponse,
)
from .repositories.index_repo import IndexRepository
from .repositories.posts_repo import PostsRepository
from .repositories.prices import PriceRepository
from .repositories.stash import StashRepository
from .repositories.supabase_client import ConfigError
from .services.calculator import (
    Calculator,
    PriceUnavailableError,
    TickerNotFoundError,
)
from .services.feed import FeedService
from .services.index_illusion import (
    BreadthUnavailableError,
    IndexIllusionService,
)
from .services.leaderboard import Leaderboard
from .services.parallel import ParallelService
from .services.posts import (
    CaptionRejectedError,
    PostNotFoundError,
    PostService,
)
from .services.reactions import ReactionService
from .services.stash import StashService


log = logging.getLogger("껄스닥")
log.setLevel(logging.INFO)


# ---------- 의존성 주입 (§3-4) ----------


def get_price_repo() -> PriceRepository:
    return PriceRepository()


def get_stash_repo() -> StashRepository:
    return StashRepository()


def get_calculator(
    prices: PriceRepository = Depends(get_price_repo),
) -> Calculator:
    return Calculator(prices)


def get_leaderboard_service(
    stash_repo: StashRepository = Depends(get_stash_repo),
) -> Leaderboard:
    return Leaderboard(stash_repo)


def get_stash_service(
    calc: Calculator = Depends(get_calculator),
    stash_repo: StashRepository = Depends(get_stash_repo),
) -> StashService:
    return StashService(calc, stash_repo)


def get_parallel_service(
    calc: Calculator = Depends(get_calculator),
) -> ParallelService:
    return ParallelService(calc)


def get_posts_repo() -> PostsRepository:
    return PostsRepository()


def get_post_service(
    calc: Calculator = Depends(get_calculator),
    posts_repo: PostsRepository = Depends(get_posts_repo),
) -> PostService:
    return PostService(calc, posts_repo)


def get_feed_service(
    posts_repo: PostsRepository = Depends(get_posts_repo),
) -> FeedService:
    return FeedService(posts_repo)


def get_reaction_service(
    posts_repo: PostsRepository = Depends(get_posts_repo),
) -> ReactionService:
    return ReactionService(posts_repo)


def get_index_repo() -> IndexRepository:
    return IndexRepository()


def get_index_illusion_service(
    repo: IndexRepository = Depends(get_index_repo),
) -> IndexIllusionService:
    return IndexIllusionService(repo)


# ---------- startup fail-fast (점검 ①) ----------


def _missing_settings() -> list[str]:
    """필수 환경변수 중 비어 있는 키 목록 (DB 라우트가 503 반환)."""
    s = get_settings()
    return [
        k
        for k, v in {
            "SUPABASE_URL": s.supabase_url,
            "SUPABASE_ANON_KEY": s.supabase_anon_key,
        }.items()
        if not v
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """배포 환경 오설정을 startup 시점에 즉시 발견.

    서버는 뜨되(헬스체크·디버깅 가능), env 누락 시 /health 가 'degraded' 를
    노출해 배포 직후 진단을 돕는다. DB 라우트(/calculate 등)는 ConfigError →
    503 으로 정규화되어 raw 500 traceback 노출 ✕.
    """
    missing = _missing_settings()
    app.state.degraded = missing
    if missing:
        log.error("필수 환경변수 누락: %s — DB 라우트가 503 을 반환합니다.", missing)
    yield


# ---------- 앱 조립 ----------


settings = get_settings()
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="껄스닥",
    description="EOD 기준 이번 달 수익 계산 + 평행우주 + 익명 자랑대회. 투자 자문 아님.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — 화이트리스트 (security-qa #4)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,           # cookie 사용 ✕ (익명) — credentials 차단
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    max_age=600,
)

# Rate limit — slowapi
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------- 예외 핸들러 ----------


@app.exception_handler(TickerNotFoundError)
async def _ticker_404(_: Request, exc: TickerNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(PriceUnavailableError)
async def _price_503(_: Request, exc: PriceUnavailableError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(ConfigError)
async def _config_503(_: Request, exc: ConfigError):
    """필수 환경변수 누락(점검 ①) → 503 한국어. raw 500 traceback 노출 ✕.

    httpx.HTTPError 핸들러는 '연결 후 HTTP 오류'만 잡으므로 DI 단계에서 터지는
    설정 누락을 못 잡는다. ConfigError 전용 핸들러로 좁게 정규화.
    """
    log.error("config error: %s", exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "서비스 설정이 일시적으로 불완전합니다. 잠시 후 다시 시도해 주세요."
        },
    )


@app.exception_handler(CaptionRejectedError)
async def _caption_400(_: Request, exc: CaptionRejectedError):
    """캡션 검증 실패(길이·URL·@) → 400 한국어 (Phase B)."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(PostNotFoundError)
async def _post_404(_: Request, exc: PostNotFoundError):
    """피드 글 미존재(조회·반응) → 404 한국어 (Phase B)."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(BreadthUnavailableError)
async def _breadth_503(_: Request, exc: BreadthUnavailableError):
    """지수착시 집계 미적재(배치 미실행·휴장) → 503 한국어 (Phase 4)."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(httpx.HTTPError)
async def _httpx_503(_: Request, exc: httpx.HTTPError):
    """Supabase REST 호출 실패(연결·타임아웃·HTTP 오류) → 503 + 한국어 메시지.

    P1-1: raw httpx 예외가 500으로 노출되던 결함 fix.
    내부 detail은 로그로만 남기고 사용자에게는 안내 문구만.
    """
    log.warning("supabase http error: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "시세 서비스가 일시 불안정합니다. 잠시 후 다시 시도해 주세요."},
    )


# ---------- 라우트 ----------


@app.get("/health")
async def health(request: Request):
    """헬스체크. env 누락 시 degraded + missing 노출(200 유지, 배포 검증용)."""
    # lifespan 미실행(일부 테스트 경로) 대비 — state 없으면 즉시 계산.
    missing = getattr(request.app.state, "degraded", None)
    if missing is None:
        missing = _missing_settings()
    if missing:
        return {
            "status": "degraded",
            "service": "껄스닥",
            "version": app.version,
            "missing": missing,
        }
    return {"status": "ok", "service": "껄스닥", "version": app.version}


@app.post("/calculate", response_model=CalculateResponse)
@limiter.limit(f"{settings.rate_calc_per_minute}/minute")
async def calculate(
    request: Request,
    body: CalculateRequest,
    calc: Calculator = Depends(get_calculator),
) -> CalculateResponse:
    """이번 달 수익 계산. 사용자 입력 검증 후 EOD 종가로 산출."""
    return await calc.calculate(body)


@app.post("/parallel", response_model=ParallelResponse)
@limiter.limit(f"{settings.rate_parallel_per_minute}/minute")
async def parallel(
    request: Request,
    body: ParallelRequest,
    svc: ParallelService = Depends(get_parallel_service),
) -> ParallelResponse:
    """평행우주(종목대체형) — '만약 OO 샀다면' 비교.

    내부에서 Calculator.calculate 를 mine/alt 각 1회 호출(신규 계산 0).
    종목 미존재 → 404, 가격/환율 부족 → 503 (전역 예외 핸들러가 처리).
    """
    return await svc.compare(body)


@app.get("/leaderboard", response_model=LeaderboardResponse)
@limiter.limit(f"{settings.rate_default_per_minute}/minute")
async def leaderboard(
    request: Request,
    sort: str = "amount",
    period: str = "month",
    ticker: Optional[str] = None,
    limit: int = 50,
    svc: Leaderboard = Depends(get_leaderboard_service),
) -> LeaderboardResponse:
    """랭킹 — 종목 필터 가능 (사용자 조정 #2)."""
    if limit < 1 or limit > 100:
        raise HTTPException(400, "limit 은 1~100")
    if sort not in ("amount", "pct"):
        raise HTTPException(400, "sort 는 amount 또는 pct")
    if period != "month":
        raise HTTPException(400, "period 는 month 만 지원")
    try:
        return await svc.fetch(sort=sort, period=period, ticker=ticker, limit=limit)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/stash", response_model=StashResponse)
@limiter.limit(f"{settings.rate_stash_per_minute}/minute")
async def stash(
    request: Request,
    body: StashRequest,
    svc: StashService = Depends(get_stash_service),
) -> StashResponse:
    """익명 자랑 등재. 캡션·닉네임 ✕ (Phase A)."""
    client_ip = request.client.host if request.client else "0.0.0.0"
    return await svc.submit(body, client_ip=client_ip)


@app.get("/share/{stash_id}", response_model=ShareResponse)
@limiter.limit(f"{settings.rate_default_per_minute}/minute")
async def share(
    request: Request,
    stash_id: str,
    stash_repo: StashRepository = Depends(get_stash_repo),
) -> ShareResponse:
    """공유 카드 — OG 메타 + 결과 스냅샷."""
    row = await stash_repo.get(stash_id)
    if not row:
        raise HTTPException(404, f"등재된 결과를 찾을 수 없습니다: {stash_id}")
    s = get_settings()
    og_url = f"{s.site_origin.rstrip('/')}/api/og/{stash_id}"
    return ShareResponse(
        id=row.id,
        created_at=row.created_at,
        ticker=row.ticker,
        name=row.name,
        qty=row.qty,
        buy_date=row.buy_date,
        profit_amount=row.profit_amount,
        profit_pct=row.profit_pct,
        period_start=row.period_start,
        period_end=row.period_end,
        og_image_url=og_url,
        disclaimer=s.disclaimer,
    )


# ---------- 커뮤니티 (Phase B — posts / feed / react) ----------
# ⚠️ 댓글 엔드포인트 없음 (스펙 금지): /posts/{id}/comments ✕, @멘션 ✕, 스레드 ✕.


@app.post("/posts", response_model=PostCreateResponse)
@limiter.limit(f"{settings.rate_posts_per_minute}/minute")
async def create_post(
    request: Request,
    body: PostCreate,
    svc: PostService = Depends(get_post_service),
) -> PostCreateResponse:
    """피드 등재 — 서버 재계산 + caption URL/@ 필터 + ip_hash.

    caption 61자/URL/@ → 400 한글, 종목 미존재 → 404, 가격 부족 → 503
    (전역 예외 핸들러가 처리).
    """
    client_ip = request.client.host if request.client else "0.0.0.0"
    return await svc.create(body, client_ip=client_ip)


@app.get("/feed", response_model=FeedResponse)
@limiter.limit(f"{settings.rate_default_per_minute}/minute")
async def feed(
    request: Request,
    sort: str = "latest",
    ticker: Optional[str] = None,
    limit: int = 20,
    cursor: Optional[str] = None,
    svc: FeedService = Depends(get_feed_service),
) -> FeedResponse:
    """피드 — latest(최신) | hot(🔥 많은 순), 종목 필터, 커서 페이징."""
    if sort not in ("latest", "hot"):
        raise HTTPException(400, "sort 는 latest 또는 hot")
    s = get_settings()
    if limit < 1 or limit > s.feed_max_limit:
        raise HTTPException(400, f"limit 은 1~{s.feed_max_limit}")
    norm_ticker = ticker.strip().upper() if ticker else None
    return await svc.fetch(
        sort=sort, ticker=norm_ticker, limit=limit, cursor=cursor
    )


@app.post("/posts/{post_id}/react", response_model=ReactResponse)
@limiter.limit(f"{settings.rate_react_per_minute}/minute")
async def react(
    request: Request,
    post_id: str,
    body: ReactRequest,
    svc: ReactionService = Depends(get_reaction_service),
) -> ReactResponse:
    """반응(🔥fire 👏clap 😭cry) — 1인 1포스트 1반응(탭하면 변경).

    내부: react_to_post RPC(트랜잭션 upsert + 카운트 재집계).
    글 미존재 → 404, type 불일치/visitor_id 누락 → 422(Pydantic).
    """
    return await svc.react(post_id, body)


@app.get("/posts/{post_id}", response_model=PostDetailResponse)
@limiter.limit(f"{settings.rate_default_per_minute}/minute")
async def get_post(
    request: Request,
    post_id: str,
    visitor_id: Optional[str] = None,
    svc: PostService = Depends(get_post_service),
) -> PostDetailResponse:
    """단건 카드 + (visitor_id 제공 시)내 반응. 미존재 → 404."""
    return await svc.get_detail(post_id, visitor_id=visitor_id)


# ---------- 지수착시 (Phase 4 — /index/illusion) ----------
# "코스피는 올랐는데 내 종목만 녹았다" 괴리 폭로. EOD 라 같은 date 응답은
# 불변 → Cache-Control 강함(프론트 SWR 와 결합). headline 은 백엔드가
# 데이터로 생성(가드레일 통과 — 투자 권유 표현 0).


@app.get("/index/illusion", response_model=IndexIllusionResponse)
@limiter.limit(f"{settings.rate_index_per_minute}/minute")
async def index_illusion(
    request: Request,
    response: Response,
    market: str = "KR_KOSPI",
    date: str = "latest",
    svc: IndexIllusionService = Depends(get_index_illusion_service),
) -> IndexIllusionResponse:
    """지수 등락 vs 종목 등락 분포의 괴리 1건.

    market: KR_KOSPI | KR_KOSDAQ. date: latest | YYYY-MM-DD.
    집계 미적재 → 503(BreadthUnavailableError), 잘못된 date → 400.
    """
    if market not in ("KR_KOSPI", "KR_KOSDAQ"):
        raise HTTPException(400, "market 은 KR_KOSPI 또는 KR_KOSDAQ")
    try:
        result = await svc.get_illusion(market=market, date_str=date)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # EOD 불변 — 1시간 캐시(프론트 SWR + CDN). latest 도 당일 동안 거의 불변.
    response.headers["Cache-Control"] = (
        f"public, max-age={settings.index_cache_max_age}"
    )
    return result


@app.get("/index/illusion/series", response_model=IndexSeriesResponse)
@limiter.limit(f"{settings.rate_index_per_minute}/minute")
async def index_illusion_series(
    request: Request,
    response: Response,
    market: str = "KR_KOSPI",
    days: int = 20,
    svc: IndexIllusionService = Depends(get_index_illusion_service),
) -> IndexSeriesResponse:
    """최근 N일 illusion_gap 추이(스파크라인). days 1~60."""
    if market not in ("KR_KOSPI", "KR_KOSDAQ"):
        raise HTTPException(400, "market 은 KR_KOSPI 또는 KR_KOSDAQ")
    if days < 1 or days > settings.index_series_max_days:
        raise HTTPException(400, f"days 는 1~{settings.index_series_max_days}")
    result = await svc.get_series(market=market, days=days)
    response.headers["Cache-Control"] = (
        f"public, max-age={settings.index_cache_max_age}"
    )
    return result
