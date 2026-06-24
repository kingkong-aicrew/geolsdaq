"""지수 시계열(코스피/코스닥) EOD 수집 → Supabase index_prices upsert.

데이터소스: FinanceDataReader(FDR) — fdr.DataReader('KS11'|'KQ11', start, end).
   pykrx 1.0.45 의 지수 API(get_index_ohlcv_by_date)가 KRX 응답 포맷 변경으로
   빈 데이터를 반환해 작동 불가(2026-06) → FDR 로 전환. 개별종목 OHLCV(fetch_kr)
   는 pykrx 가 정상이라 그대로 둔다.

설계 A-4:
- FDR DataReader('KS11'=코스피 / 'KQ11'=코스닥) — 지수 1콜로 종가 시계열.
- 등락률(change_pct)은 종가 시계열에서 전 거래일 대비로 계산해 저장
  (조회 시 join 회피). 시리즈 첫 행은 직전 종가가 없으므로 None.

실행:
    python -m backend.batch.fetch_index [--days 30]

기본: 최근 30거래일(시계열 series 화면이 의미를 가지려면 누적 필요).

GitHub Actions:
    .github/workflows/fetch-index.yml — KST 17:30 (fetch-kr 이후) 평일
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from ..repositories.supabase_client import SupabaseRest

# FDR 지수 심볼 → (index_code, 표시명). FDR: 코스피 'KS11', 코스닥 'KQ11'.
# index_code 는 DB(index_prices.index_code CHECK) 와 동일하게 'KOSPI'/'KOSDAQ' 유지.
INDEX_CODES: Dict[str, Tuple[str, str]] = {
    "KS11": ("KOSPI", "코스피"),
    "KQ11": ("KOSDAQ", "코스닥"),
}


def rows_from_closes(
    index_code: str,
    name: str,
    closes: List[Tuple[date, float]],
) -> List[dict]:
    """(date, close) 시계열 → index_prices upsert payload.

    pykrx DataFrame 에 의존하지 않는 순수 변환(테스트 가능). 등락률은
    직전 종가 대비로 계산하며, 시계열 첫 행은 None(직전값 없음).
    closes 는 날짜 오름차순 가정. close<=0 행은 건너뛴다.
    """
    ordered = sorted((d, c) for d, c in closes if c > 0)
    rows: List[dict] = []
    prev: Optional[float] = None
    for d, close in ordered:
        change_pct: Optional[float] = None
        if prev is not None and prev > 0:
            change_pct = round((close - prev) / prev * 100, 4)
        rows.append(
            {
                "index_code": index_code,
                "date": d.isoformat(),
                "close": round(float(close), 2),
                "change_pct": change_pct,
                "name": name,
            }
        )
        prev = close
    return rows


def _fetch_index_closes(symbol: str, start: date, end: date) -> List[Tuple[date, float]]:
    """FDR 지수 일봉 종가 시계열. import 는 함수 안(테스트가 FDR 없이 동작).

    symbol 은 FDR 심볼('KS11'/'KQ11'). FDR 은 인덱스가 DatetimeIndex(Date),
    종가는 'Close' 컬럼. 결측/0 종가는 제외한다.
    """
    import FinanceDataReader as fdr  # noqa: PLC0415 (cron 환경에서만 필요)

    try:
        df = fdr.DataReader(symbol, start.isoformat(), end.isoformat())
    except Exception as ex:  # noqa: BLE001 (배치는 종목/지수 단위로 실패 격리)
        print(f"  ! 지수 {symbol} FDR 실패: {ex}")
        return []
    if df is None or df.empty:
        return []
    out: List[Tuple[date, float]] = []
    for idx, row in df.iterrows():
        d = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
        raw = row.get("Close", row.get("종가", 0))
        try:
            close = float(raw)
        except (TypeError, ValueError):
            continue
        if close != close:  # NaN
            continue
        if close > 0:
            out.append((d, close))
    return out


async def _upsert(cli: SupabaseRest, rows: List[dict]) -> int:
    if not rows:
        return 0
    n = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i : i + 500]
        await cli.upsert("index_prices", chunk, on_conflict="index_code,date")
        n += len(chunk)
    return n


async def main(days: int) -> None:
    cli = SupabaseRest(use_service_role=True)
    end = date.today()
    start = end - timedelta(days=days)

    total = 0
    for symbol, (index_code, name) in INDEX_CODES.items():
        closes = _fetch_index_closes(symbol, start, end)
        rows = rows_from_closes(index_code, name, closes)
        n = await _upsert(cli, rows)
        total += n
        print(f"  {index_code:<8} {name:<6}  {n} rows")
    print(f"\n완료: 총 {total} rows upsert (index_prices)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()
    asyncio.run(main(args.days))
