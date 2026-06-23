"""Twelve Data EOD 수집 → Supabase upsert.

실행:
    python -m backend.batch.fetch_us [--days 7] [--sleep 8.0]

종가는 USD 원시값으로 저장. KRW 환산은 서비스 계층(/calculate)에서.
데이터소스: Twelve Data time_series API (yfinance 안티봇 차단으로 2026-06 교체).
키: 환경변수 TWELVEDATA_API_KEY (무료 800콜/일·8콜/분). 무료 티어 rate limit
대응으로 종목당 sleep + 429 단발 재시도.

GitHub Actions:
    .github/workflows/fetch-us.yml — KST 06:00 (UTC 21:00) 평일
"""
from __future__ import annotations

import argparse
import asyncio
import time
from datetime import date, timedelta
from typing import Iterable, List

import httpx

from ..config import get_settings
from ..repositories.supabase_client import SupabaseRest
from .tickers import all_us

BASE_URL = "https://api.twelvedata.com/time_series"

# 저장/표시 코드 → Twelve Data 조회 심볼 오버라이드.
# 클래스주는 야후식 'BRK-B' 가 아니라 'BRK.B'(점) 표기를 써야 조회됨.
# DB·프론트는 'BRK-B' 로 일관 유지하고, API 호출 때만 변환.
SYMBOL_OVERRIDES = {"BRK-B": "BRK.B"}


def _parse_values(ticker: str, name: str, payload: dict) -> List[dict]:
    """Twelve Data 응답(JSON) → prices upsert payload. 순수 변환(테스트 가능)."""
    if payload.get("status") != "ok":
        return []
    rows: List[dict] = []
    for v in payload.get("values", []):
        try:
            d = date.fromisoformat(str(v["datetime"])[:10])
            close = float(v["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if close <= 0:
            continue
        rows.append(
            {
                "ticker": ticker,
                "date": d.isoformat(),
                "close": close,
                "market": "US",
                "name": name,
            }
        )
    return rows


def _fetch_one(
    client: httpx.Client,
    ticker: str,
    name: str,
    start: date,
    end: date,
    api_key: str,
) -> List[dict]:
    """Twelve Data 단일 종목 일봉. 429(rate limit)면 65초 후 1회 재시도."""
    params = {
        "symbol": SYMBOL_OVERRIDES.get(ticker, ticker),
        "interval": "1day",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": "America/New_York",
        "apikey": api_key,
    }
    for attempt in (1, 2):
        try:
            resp = client.get(BASE_URL, params=params, timeout=30.0)
            data = resp.json()
        except Exception as ex:  # noqa: BLE001
            print(f"  ! {ticker} TwelveData 실패: {ex}")
            return []
        # rate limit: code 429 또는 메시지에 'API credits' → 대기 후 재시도
        code = data.get("code")
        if code == 429 and attempt == 1:
            print(f"  … {ticker} rate limit — 65초 대기 후 재시도")
            time.sleep(65)
            continue
        if data.get("status") != "ok":
            print(f"  ! {ticker} TwelveData 오류: {str(data.get('message', data))[:80]}")
            return []
        return _parse_values(ticker, name, data)
    return []


async def _upsert(cli: SupabaseRest, payloads: Iterable[dict]) -> int:
    batch: List[dict] = list(payloads)
    if not batch:
        return 0
    n = 0
    for i in range(0, len(batch), 500):
        chunk = batch[i : i + 500]
        await cli.upsert("prices", chunk, on_conflict="ticker,date")
        n += len(chunk)
    return n


async def main(days: int, sleep_sec: float) -> None:
    settings = get_settings()
    api_key = settings.twelvedata_api_key
    if not api_key:
        raise RuntimeError(
            "TWELVEDATA_API_KEY 환경변수가 없습니다. "
            "https://twelvedata.com/pricing 에서 무료 키 발급 후 .env 에 추가하세요."
        )
    cli = SupabaseRest(use_service_role=True)
    end = date.today()
    start = end - timedelta(days=days)
    total = 0
    tickers = list(all_us())
    with httpx.Client() as client:
        for i, (ticker, name) in enumerate(tickers):
            rows = _fetch_one(client, ticker, name, start, end, api_key)
            n = await _upsert(cli, rows)
            total += n
            if n:
                print(f"  {ticker:<8} {name:<20}  {n} rows")
            # 무료 8콜/분 — 마지막 종목 제외하고 sleep
            if i < len(tickers) - 1 and sleep_sec > 0:
                time.sleep(sleep_sec)
    print(f"\n완료: 총 {total} rows upsert ({len(tickers)} 종목)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument(
        "--sleep",
        type=float,
        default=8.0,
        help="종목당 대기(초). 무료 8콜/분 → 8.0 권장",
    )
    args = ap.parse_args()
    asyncio.run(main(args.days, args.sleep))
