"""두 번째 월급 — 설정 통합 (env > .env > 기본값).

원칙 (§3-5):
- 시크릿(SUPABASE_KEY, SUPABASE_SERVICE_KEY)은 환경변수만, 코드 ✕
- 기본값은 로컬 개발 용이성을 위한 비밀이 아닌 값만
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# .env 자동 로드 — 로컬에서 backend/.env 에 키를 한 번 저장하면 매 실행 자동 주입
# (수동 set-env 불필요·채팅 입력 불필요). cwd 무관하게 이 파일 기준 절대경로로 찾는다.
# Render/GitHub Actions 는 환경변수를 직접 주입 → .env 없음 → load_dotenv 가 조용히 무시
# (override=False 라 실제 환경변수가 .env 보다 우선). python-dotenv 미설치 환경도 방어.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


def _env(key: str, default: str = "") -> str:
    """환경변수 우선, 빈 문자열이면 default."""
    v = os.environ.get(key, "").strip()
    return v if v else default


def _env_list(key: str, default: List[str]) -> List[str]:
    raw = _env(key, "")
    if not raw:
        return default
    return [s.strip() for s in raw.split(",") if s.strip()]


@dataclass(frozen=True)
class Settings:
    # Supabase
    supabase_url: str = field(default_factory=lambda: _env("SUPABASE_URL"))
    supabase_anon_key: str = field(default_factory=lambda: _env("SUPABASE_ANON_KEY"))
    supabase_service_key: str = field(
        default_factory=lambda: _env("SUPABASE_SERVICE_KEY")
    )

    # CORS — 화이트리스트 (security-qa #4)
    cors_origins: List[str] = field(
        default_factory=lambda: _env_list(
            "CORS_ORIGINS",
            [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ],
        )
    )

    # Rate limit (security-qa #3) — IP 분당
    rate_calc_per_minute: int = field(
        default_factory=lambda: int(_env("RATE_CALC_PER_MINUTE", "30"))
    )
    rate_stash_per_minute: int = field(
        default_factory=lambda: int(_env("RATE_STASH_PER_MINUTE", "10"))
    )
    # 평행우주 — 2종목 조회로 calc 2배 부하 → 절반(20/m)
    rate_parallel_per_minute: int = field(
        default_factory=lambda: int(_env("RATE_PARALLEL_PER_MINUTE", "20"))
    )
    # 커뮤니티 (Phase B) — posts 는 stash 와 동급(텍스트 입력 스팸 방어), react 는 탭 빈도 고려
    rate_posts_per_minute: int = field(
        default_factory=lambda: int(_env("RATE_POSTS_PER_MINUTE", "10"))
    )
    rate_react_per_minute: int = field(
        default_factory=lambda: int(_env("RATE_REACT_PER_MINUTE", "30"))
    )
    # 지수착시 — EOD 라 같은 date 응답 불변(캐싱 강함). 가벼운 읽기 → default 와 동일
    rate_index_per_minute: int = field(
        default_factory=lambda: int(_env("RATE_INDEX_PER_MINUTE", "60"))
    )
    rate_default_per_minute: int = field(
        default_factory=lambda: int(_env("RATE_DEFAULT_PER_MINUTE", "60"))
    )

    # 지수착시 정책
    index_series_max_days: int = 60           # series days 상한
    index_cache_max_age: int = 3600           # Cache-Control max-age (EOD 불변)

    # 커뮤니티 정책
    max_caption_length: int = 60              # posts.caption CHECK 와 동일
    max_nickname_length: int = 12             # posts.nickname CHECK 와 동일
    feed_default_limit: int = 20
    feed_max_limit: int = 50

    # 도메인 정책
    period_kst_offset_hours: int = 9          # KST = UTC+9
    max_qty: int = 999_999                    # stash CHECK 와 동일
    min_buy_date: str = "2000-01-01"

    # OG 공개용 (백엔드 응답에 포함되어 프론트가 메타 태그에 박음)
    site_origin: str = field(
        default_factory=lambda: _env("SITE_ORIGIN", "http://localhost:3000")
    )

    # Twelve Data — US 주식·환율 EOD 배치 (cron 환경에서만 필요. yfinance 대체)
    twelvedata_api_key: str = field(
        default_factory=lambda: _env("TWELVEDATA_API_KEY")
    )

    # 면책 (모든 응답·OG·푸터 공통)
    disclaimer: str = "전일 종가 기준 · 투자 자문 아님"


_settings: Settings | None = None


def get_settings() -> Settings:
    """싱글톤 — env 변경은 서버 재시작 시에만 반영."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_for_tests() -> None:
    """테스트용 — 환경변수를 재로딩."""
    global _settings
    _settings = None
