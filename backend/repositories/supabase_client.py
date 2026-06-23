"""Supabase REST 공용 클라이언트 (httpx).

직접 supabase-py 의존하지 않고 REST 만 사용 — 의존성 최소화.
anon 키: 일반 조회. service_key: 배치/insert.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from ..config import get_settings


class ConfigError(RuntimeError):
    """필수 환경변수 누락 — main.py 에서 503 으로 정규화.

    광범위한 RuntimeError 핸들러는 진짜 버그성 RuntimeError 까지 503 으로
    삼켜 디버깅을 가린다("조용한 실패를 시끄럽게" 위반). 설정 누락만 이
    전용 예외로 좁혀 던지고, 핸들러도 ConfigError 만 잡는다.
    """


class SupabaseRest:
    def __init__(self, *, use_service_role: bool = False, timeout: float = 15.0):
        s = get_settings()
        if not s.supabase_url:
            raise ConfigError(
                "SUPABASE_URL 환경변수가 없습니다. .env.example 를 참조하세요."
            )
        key = s.supabase_service_key if use_service_role else s.supabase_anon_key
        if not key:
            kind = "SUPABASE_SERVICE_KEY" if use_service_role else "SUPABASE_ANON_KEY"
            raise ConfigError(f"{kind} 환경변수가 없습니다.")
        self.base = s.supabase_url.rstrip("/") + "/rest/v1"
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self.timeout = timeout

    async def select(
        self,
        table: str,
        *,
        params: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            r = await cli.get(
                f"{self.base}/{table}",
                headers=self.headers,
                params=params or {},
            )
            r.raise_for_status()
            return r.json()

    async def insert(
        self, table: str, rows: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            r = await cli.post(
                f"{self.base}/{table}",
                headers=self.headers,
                json=rows,
            )
            r.raise_for_status()
            return r.json()

    async def upsert(
        self,
        table: str,
        rows: List[Dict[str, Any]],
        *,
        on_conflict: str,
    ) -> List[Dict[str, Any]]:
        headers = {**self.headers, "Prefer": "resolution=merge-duplicates"}
        params = {"on_conflict": on_conflict}
        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            r = await cli.post(
                f"{self.base}/{table}",
                headers=headers,
                params=params,
                json=rows,
            )
            r.raise_for_status()
            return r.json() if r.text else []

    async def rpc(self, fn: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Postgres 함수(RPC) 호출 — POST /rest/v1/rpc/{fn}.

        Phase B react_to_post(트랜잭션 upsert + 카운트 재집계) 호출용.
        함수가 SET OF / TABLE 을 반환하면 list, 스칼라면 단일 값을 list 로 감싼다.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            r = await cli.post(
                f"{self.base}/rpc/{fn}",
                headers=self.headers,
                json=params,
            )
            r.raise_for_status()
            if not r.text:
                return []
            data = r.json()
            return data if isinstance(data, list) else [data]
