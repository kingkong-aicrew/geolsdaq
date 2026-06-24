"""일자별 전종목 등락 집계 → Supabase index_breadth upsert.

설계 A-4 (착시 핵심):
- 등락률 분포에서 상승/하락/보합 종목 수 + 중앙값을 집계.
- 지수 등락률은 index_prices(fetch_index 가 적재)에서 같은 날짜로 조회.
- illusion_gap = index_change_pct - median_change_pct (착시 강도).

데이터소스 전환(2026-06):
- pykrx get_market_ohlcv_by_date(전종목)가 pykrx 1.0.45 내부 astype(np.int32)
  에서 'ValueError: invalid literal' 로 죽어(broad except 가 삼켜 매일 skip) →
  **prices 테이블(SupabaseRest) 기반**으로 우회.
- 특정일 전종목 등락률 = (당일 종가 − 직전 거래일 종가)/직전 거래일 종가 ×100.
- 코스피/코스닥 분류: prices 에 거래소 컬럼이 없으므로(market='KR'만) FDR
  StockListing('KRX') 의 Code→Market 맵으로 우리 KR 종목을 분류(1회 캐시).
  ⚠️ 한계: 집계 모수는 prices 에 적재된 큐레이션 종목(약 75 코스피 / 21 코스닥)
  으로, 시장 전종목(코스피 946·코스닥 1772)이 아니다. total_count 를 항상 같이
  저장해 "모수 N개 중" 으로 정직하게 노출(외삽 금지 정신).

집계 로직(compute_breadth)은 DataFrame 비의존 — 등락률 list 를 받는
순수 함수로 분리 → 외부 라이브러리 없이 단위 테스트 가능(SRP).

실행:
    python -m backend.batch.compute_breadth [--date YYYY-MM-DD] [--days 1]

기본: 오늘 1일분. --days N 이면 최근 N일을 각각 집계(백필).

GitHub Actions:
    .github/workflows/compute-breadth.yml — KST 18:00 (종가 확정 후) 평일
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Set, Tuple

from ..repositories.supabase_client import SupabaseRest

# 집계 대상 시장 → (FDR StockListing Market 분류값, index_prices.index_code).
# breadth.market : (exchange, index_code). exchange 는 KOSPI/KOSDAQ 으로 분류하되
# 'KOSDAQ GLOBAL' 도 KOSDAQ 으로 합산(아래 _classify 참조).
MARKETS: Dict[str, Tuple[str, str]] = {
    "KR_KOSPI": ("KOSPI", "KOSPI"),
    "KR_KOSDAQ": ("KOSDAQ", "KOSDAQ"),
}


@dataclass
class Breadth:
    """등락 분포 집계 결과 (지수 등락률 결합 전)."""

    total_count: int
    up_count: int
    down_count: int
    flat_count: int
    up_ratio: float
    median_change_pct: float


def compute_breadth(change_pcts: Sequence[float]) -> Breadth:
    """개별종목 등락률(%) 시퀀스 → 상승/하락/보합 집계 + 중앙값.

    - 상승: change > 0, 하락: change < 0, 보합: change == 0.
    - up_ratio = up / total (total=0 이면 0.0).
    - median: 표본 중앙값(짝수면 두 중앙값 평균). total=0 이면 0.0.
    pykrx DataFrame 비의존 — 테스트 가능한 순수 함수.
    """
    vals = [float(c) for c in change_pcts]
    total = len(vals)
    up = sum(1 for c in vals if c > 0)
    down = sum(1 for c in vals if c < 0)
    flat = total - up - down  # change == 0 (NaN 은 호출측에서 사전 제거)
    up_ratio = round(up / total, 4) if total else 0.0
    median = round(statistics.median(vals), 4) if total else 0.0
    return Breadth(
        total_count=total,
        up_count=up,
        down_count=down,
        flat_count=flat,
        up_ratio=up_ratio,
        median_change_pct=median,
    )


def breadth_row(
    market: str,
    d: date,
    index_change_pct: float,
    breadth: Breadth,
) -> dict:
    """집계 결과 + 지수 등락률 → index_breadth upsert payload (순수)."""
    illusion_gap = round(float(index_change_pct) - breadth.median_change_pct, 4)
    return {
        "market": market,
        "date": d.isoformat(),
        "index_change_pct": round(float(index_change_pct), 4),
        "total_count": breadth.total_count,
        "up_count": breadth.up_count,
        "down_count": breadth.down_count,
        "flat_count": breadth.flat_count,
        "up_ratio": breadth.up_ratio,
        "median_change_pct": breadth.median_change_pct,
        "illusion_gap": illusion_gap,
    }


def _classify(market_value: Optional[str]) -> Optional[str]:
    """FDR StockListing Market 값 → 'KOSPI' | 'KOSDAQ' | None.

    'KOSDAQ', 'KOSDAQ GLOBAL' 은 모두 KOSDAQ 으로 합산. KONEX·미상은 None(제외).
    """
    if not market_value:
        return None
    if market_value == "KOSPI":
        return "KOSPI"
    if market_value.startswith("KOSDAQ"):
        return "KOSDAQ"
    return None


def load_exchange_map() -> Dict[str, str]:
    """우리 KR 종목 코드 → 거래소('KOSPI'/'KOSDAQ') 맵.

    FDR StockListing('KRX')(거래소 전체)에서 Code→Market 을 받아 tickers.py 의
    KR 큐레이션 종목만 분류. import·네트워크 호출은 함수 안(테스트가 FDR 없이 동작).
    분류 불가(상폐·KONEX·미상) 종목은 맵에서 제외 → 자연히 집계 모수에서 빠진다.
    """
    import FinanceDataReader as fdr  # noqa: PLC0415 (cron 환경에서만 필요)

    from .tickers import KR_TICKERS

    listing = fdr.StockListing("KRX")
    raw = listing.set_index("Code")["Market"].to_dict()
    out: Dict[str, str] = {}
    for code in KR_TICKERS:
        ex = _classify(raw.get(code))
        if ex:
            out[code] = ex
    return out


async def _fetch_change_pcts(
    cli: SupabaseRest, tickers: Set[str], d: date
) -> List[float]:
    """prices 테이블 기반 특정일 전(큐레이션)종목 등락률(%).

    종목별: (당일 종가 − 직전 거래일 종가)/직전 거래일 종가 ×100.
    - d 당일에 종가가 없으면(그 종목 미거래/누락) 제외.
    - d 직전 거래일 종가가 없으면(상장 첫날 등) 제외(보합 오분류 방지).
    조회 최소화: tickers 를 한 번에 in.(...) 으로 [d-14, d] 구간을 받아
    종목별로 당일·직전 종가를 파이썬에서 추린다(거래일 간격·연휴 대비 14일).
    """
    if not tickers:
        return []
    win_start = (d - timedelta(days=14)).isoformat()
    di = d.isoformat()
    ticker_csv = ",".join(sorted(tickers))
    # date 범위는 list 값으로 → httpx 가 date=gte.X&date=lte.Y 로 인코딩(PostgREST AND).
    rows = await cli.select(
        "prices",
        params={
            "market": "eq.KR",
            "ticker": f"in.({ticker_csv})",
            "date": [f"gte.{win_start}", f"lte.{di}"],  # type: ignore[dict-item]
            "select": "ticker,date,close",
            "order": "ticker.asc,date.asc",
            "limit": "100000",
        },
    )
    by_ticker: Dict[str, List[Tuple[date, float]]] = {}
    for r in rows:
        rd = date.fromisoformat(r["date"])
        try:
            c = float(r["close"])
        except (TypeError, ValueError):
            continue
        if c <= 0:
            continue
        by_ticker.setdefault(r["ticker"], []).append((rd, c))

    out: List[float] = []
    for series in by_ticker.values():
        series.sort(key=lambda t: t[0])
        # 당일(d) 종가와 그 직전 거래일 종가
        day_close: Optional[float] = None
        prev_close: Optional[float] = None
        for rd, c in series:
            if rd == d:
                day_close = c
            elif rd < d:
                prev_close = c  # 오름차순이라 마지막 < d 가 직전 거래일
        if day_close is None or prev_close is None or prev_close <= 0:
            continue
        out.append(round((day_close - prev_close) / prev_close * 100, 4))
    return out


async def _index_change_pct(
    cli: SupabaseRest, index_code: str, d: date
) -> Optional[float]:
    """index_prices 에서 해당일 지수 등락률 조회(없으면 None → 그날 집계 skip)."""
    rows = await cli.select(
        "index_prices",
        params={
            "index_code": f"eq.{index_code}",
            "date": f"eq.{d.isoformat()}",
            "limit": "1",
            "select": "change_pct",
        },
    )
    if not rows:
        return None
    v = rows[0].get("change_pct")
    return float(v) if v is not None else None


async def compute_for_date(
    cli: SupabaseRest, d: date, exchange_map: Dict[str, str]
) -> int:
    """하루치 — 모든 시장 집계 후 upsert. 반환: upsert 한 행 수.

    exchange_map: 종목코드 → 'KOSPI'/'KOSDAQ' (load_exchange_map() 결과, 1회 캐시).
    """
    n = 0
    for breadth_market, (exchange, index_code) in MARKETS.items():
        idx_change = await _index_change_pct(cli, index_code, d)
        if idx_change is None:
            print(
                f"  - {breadth_market} {d}: 지수 등락률 없음(index_prices 미적재) → skip"
            )
            continue
        tickers = {c for c, ex in exchange_map.items() if ex == exchange}
        change_pcts = await _fetch_change_pcts(cli, tickers, d)
        if not change_pcts:
            print(f"  - {breadth_market} {d}: 전종목 등락률 없음(휴장?) → skip")
            continue
        b = compute_breadth(change_pcts)
        row = breadth_row(breadth_market, d, idx_change, b)
        await cli.upsert("index_breadth", [row], on_conflict="market,date")
        n += 1
        print(
            f"  {breadth_market:<10} {d}  지수 {idx_change:+.2f}% / "
            f"상승 {b.up_count} 하락 {b.down_count} 보합 {b.flat_count} "
            f"(모수 {b.total_count}, 중앙값 {b.median_change_pct:+.2f}%, "
            f"착시 {row['illusion_gap']:+.2f})"
        )
    return n


async def main(target: Optional[date], days: int) -> None:
    cli = SupabaseRest(use_service_role=True)
    if target is not None:
        dates = [target]
    else:
        today = date.today()
        dates = [today - timedelta(days=i) for i in range(days)]
    # 거래소 분류 맵은 날짜 무관 → 1회만 조회(FDR StockListing 1콜).
    exchange_map = load_exchange_map()
    kospi_n = sum(1 for v in exchange_map.values() if v == "KOSPI")
    kosdaq_n = sum(1 for v in exchange_map.values() if v == "KOSDAQ")
    print(f"거래소 분류: 코스피 {kospi_n} · 코스닥 {kosdaq_n} (큐레이션 모수)")
    total = 0
    for d in sorted(dates):
        total += await compute_for_date(cli, d, exchange_map)
    print(f"\n완료: 총 {total} 시장·일 집계 upsert (index_breadth)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=str, default=None, help="YYYY-MM-DD (단일 일자)")
    ap.add_argument("--days", type=int, default=1, help="최근 N일 백필(--date 미지정 시)")
    args = ap.parse_args()
    tgt = date.fromisoformat(args.date) if args.date else None
    asyncio.run(main(tgt, args.days))
