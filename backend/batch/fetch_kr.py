"""pykrx 일봉 EOD 수집 → Supabase upsert.

실행:
    python -m backend.batch.fetch_kr [--days 7]

기본: 최근 7거래일. cron 은 매일 실행하면 됨.

GitHub Actions:
    .github/workflows/fetch-kr.yml — KST 17:00 (UTC 08:00) 평일
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta
from typing import Iterable, List

from pykrx import stock

from ..repositories.supabase_client import SupabaseRest
from .tickers import all_kr


def _date_range(days: int) -> List[date]:
    today = date.today()
    return [today - timedelta(days=i) for i in range(days)]


def _fetch_one(ticker: str, name: str, start: date, end: date) -> List[dict]:
    """pykrx 일봉 → upsert payload."""
    s = start.strftime("%Y%m%d")
    e = end.strftime("%Y%m%d")
    try:
        df = stock.get_market_ohlcv_by_date(s, e, ticker)
    except Exception as ex:
        print(f"  ! {ticker} pykrx 실패: {ex}")
        return []
    rows: List[dict] = []
    if df is None or df.empty:
        return rows
    for idx, row in df.iterrows():
        d = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
        close = float(row.get("종가", row.get("Close", 0)))
        if close <= 0:
            continue
        rows.append(
            {
                "ticker": ticker,
                "date": d.isoformat(),
                "close": close,
                "market": "KR",
                "name": name,
            }
        )
    return rows


async def _upsert(cli: SupabaseRest, payloads: Iterable[dict]) -> int:
    batch: List[dict] = list(payloads)
    if not batch:
        return 0
    # asyncpg 제약과는 다르지만 안전하게 500개씩
    n = 0
    for i in range(0, len(batch), 500):
        chunk = batch[i : i + 500]
        await cli.upsert("prices", chunk, on_conflict="ticker,date")
        n += len(chunk)
    return n


async def main(days: int) -> None:
    cli = SupabaseRest(use_service_role=True)
    end = date.today()
    start = end - timedelta(days=days)

    total = 0
    for ticker, name in all_kr():
        rows = _fetch_one(ticker, name, start, end)
        n = await _upsert(cli, rows)
        total += n
        if n:
            print(f"  {ticker:>8} {name:<20}  {n} rows")
    print(f"\n완료: 총 {total} rows upsert")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()
    asyncio.run(main(args.days))
