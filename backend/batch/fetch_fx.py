"""USD-KRW 환율 일봉 → Supabase upsert.

데이터소스: Twelve Data time_series (symbol=USD/KRW). yfinance "USDKRW=X"
안티봇 차단으로 2026-06 교체. 키: 환경변수 TWELVEDATA_API_KEY.

실행:
    python -m backend.batch.fetch_fx [--days 7]
"""
from __future__ import annotations

import argparse
import asyncio
import time
from datetime import date, timedelta
from typing import List

import httpx

from ..config import get_settings
from ..repositories.supabase_client import SupabaseRest

BASE_URL = "https://api.twelvedata.com/time_series"


def _parse_values(payload: dict) -> List[dict]:
    """Twelve Data 응답(JSON) → fx upsert payload. 순수 변환(테스트 가능)."""
    if payload.get("status") != "ok":
        return []
    rows: List[dict] = []
    for v in payload.get("values", []):
        try:
            d = date.fromisoformat(str(v["datetime"])[:10])
            rate = float(v["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if rate <= 0:
            continue
        rows.append({"date": d.isoformat(), "usd_krw": rate})
    return rows


def _fetch(start: date, end: date, api_key: str) -> List[dict]:
    params = {
        "symbol": "USD/KRW",
        "interval": "1day",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "apikey": api_key,
    }
    with httpx.Client() as client:
        for attempt in (1, 2):
            try:
                resp = client.get(BASE_URL, params=params, timeout=30.0)
                data = resp.json()
            except Exception as ex:  # noqa: BLE001
                print(f"  ! USD/KRW 실패: {ex}")
                return []
            if data.get("code") == 429 and attempt == 1:
                print("  … USD/KRW rate limit — 65초 대기 후 재시도")
                time.sleep(65)
                continue
            if data.get("status") != "ok":
                print(f"  ! USD/KRW 오류: {str(data.get('message', data))[:80]}")
                return []
            return _parse_values(data)
    return []


async def main(days: int) -> None:
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
    rows = _fetch(start, end, api_key)
    if not rows:
        print("환율 데이터 없음")
        return
    await cli.upsert("fx", rows, on_conflict="date")
    print(f"완료: {len(rows)} rows upsert (USD/KRW)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()
    asyncio.run(main(args.days))
