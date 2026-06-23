"""일자별 전종목 등락 집계 → Supabase index_breadth upsert.

설계 A-4 (착시 핵심):
- pykrx get_market_ohlcv_by_date(date, market="KOSPI"/"KOSDAQ") 는 특정일 전종목을
  1콜로 가져온다(일자 스냅샷, 등락률 컬럼 포함). 종목별 루프·sleep 불필요.
- 등락률 분포에서 상승/하락/보합 종목 수 + 중앙값을 집계.
- 지수 등락률은 index_prices(fetch_index 가 적재)에서 같은 날짜로 조회.
- illusion_gap = index_change_pct - median_change_pct (착시 강도).

집계 로직(compute_breadth)은 pykrx DataFrame 이 아닌 등락률 list 를 받는
순수 함수로 분리 → pykrx 없이 단위 테스트 가능(SRP).

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
from typing import Dict, List, Optional, Sequence, Tuple

from ..repositories.supabase_client import SupabaseRest

# 집계 대상 시장 → (pykrx market 인자, index_prices.index_code, breadth.market)
MARKETS: Dict[str, Tuple[str, str]] = {
    # breadth.market : (pykrx market, index_code)
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


def _fetch_change_pcts(pykrx_market: str, d: date) -> List[float]:
    """pykrx 전종목 등락률(%) — 특정일 1콜. NaN/결측 제거.

    import 는 함수 안(테스트가 pykrx 없이 동작). 신규 상장 등으로 등락률이
    NaN 인 행은 집계에서 제외(보합으로 오분류 방지).
    """
    from pykrx import stock  # noqa: PLC0415 (cron 환경에서만 필요)

    ds = d.strftime("%Y%m%d")
    try:
        df = stock.get_market_ohlcv_by_date(ds, ds, pykrx_market)
    except TypeError:
        # 일부 버전은 (date, market=...) 시그니처 — 폴백.
        df = stock.get_market_ohlcv_by_date(ds, market=pykrx_market)  # type: ignore[call-arg]
    except Exception as ex:  # noqa: BLE001
        print(f"  ! {pykrx_market} {ds} pykrx 실패: {ex}")
        return []
    if df is None or df.empty:
        return []
    out: List[float] = []
    for _, row in df.iterrows():
        raw = row.get("등락률", row.get("ChagesRatio", row.get("Change", None)))
        if raw is None:
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if val != val:  # NaN
            continue
        out.append(val)
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


async def compute_for_date(cli: SupabaseRest, d: date) -> int:
    """하루치 — 모든 시장 집계 후 upsert. 반환: upsert 한 행 수."""
    n = 0
    for breadth_market, (pykrx_market, index_code) in MARKETS.items():
        idx_change = await _index_change_pct(cli, index_code, d)
        if idx_change is None:
            print(
                f"  - {breadth_market} {d}: 지수 등락률 없음(index_prices 미적재) → skip"
            )
            continue
        change_pcts = _fetch_change_pcts(pykrx_market, d)
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
    total = 0
    for d in sorted(dates):
        total += await compute_for_date(cli, d)
    print(f"\n완료: 총 {total} 시장·일 집계 upsert (index_breadth)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=str, default=None, help="YYYY-MM-DD (단일 일자)")
    ap.add_argument("--days", type=int, default=1, help="최근 N일 백필(--date 미지정 시)")
    args = ap.parse_args()
    tgt = date.fromisoformat(args.date) if args.date else None
    asyncio.run(main(tgt, args.days))
