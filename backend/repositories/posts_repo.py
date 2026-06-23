"""posts / reactions 테이블 접근.

설계 (점진 확장, SOLID):
- stash 리포지토리 패턴을 그대로 따른다(SupabaseRest 주입 + _parse_row).
- 피드는 **커서(keyset) 페이징**. offset 은 피드가 깊어지면 느려지므로 ✕.
  커서는 정렬 마지막 행의 (정렬키, created_at, id) 를 base64 로 인코딩.
- 반응 카운트 변경은 직접 UPDATE ✕ → react_to_post RPC(트랜잭션) 위임.
  (denormalize 동기화 = reactions 단일 진실, race 방어 — schema.sql 참조)
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from .supabase_client import SupabaseRest

# 피드 카드 표시에 필요한 컬럼만 선택 (calc_snapshot 등 무거운 필드 제외)
_CARD_SELECT = (
    "id,created_at,ticker,name,qty,buy_date,profit_amount,profit_pct,"
    "caption,nickname,fire_count,clap_count,cry_count,origin"
)


@dataclass
class PostRow:
    id: str
    created_at: datetime
    ticker: str
    name: str
    qty: int
    buy_date: date
    profit_amount: float
    profit_pct: float
    caption: Optional[str]
    nickname: Optional[str]
    fire_count: int
    clap_count: int
    cry_count: int
    origin: str


def _parse_row(r: Dict[str, Any]) -> PostRow:
    return PostRow(
        id=r["id"],
        created_at=datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")),
        ticker=r["ticker"],
        name=r["name"],
        qty=int(r["qty"]),
        buy_date=date.fromisoformat(r["buy_date"]),
        profit_amount=float(r["profit_amount"]),
        profit_pct=float(r["profit_pct"]),
        caption=r.get("caption"),
        nickname=r.get("nickname"),
        fire_count=int(r["fire_count"]),
        clap_count=int(r["clap_count"]),
        cry_count=int(r["cry_count"]),
        origin=r.get("origin") or "direct",
    )


def encode_cursor(payload: Dict[str, Any]) -> str:
    """커서 payload(dict) → URL-safe base64 문자열."""
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> Optional[Dict[str, Any]]:
    """커서 문자열 → payload. 손상된 커서는 None(첫 페이지로 폴백)."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except (ValueError, json.JSONDecodeError):
        return None


class PostsRepository:
    """Phase B — posts 조회/등재 + reactions RPC 위임.

    insert 는 위·변조 차단을 위해 service_role 로 수행(백엔드 경유 게이트).
    조회는 anon 으로 충분(RLS posts_read_anon).
    """

    def __init__(
        self,
        client: Optional[SupabaseRest] = None,
        *,
        write_client: Optional[SupabaseRest] = None,
    ):
        # 읽기: anon, 쓰기/RPC: service_role (RLS 우회 — 서버측 검증 후 호출)
        self.cli = client or SupabaseRest(use_service_role=False)
        self.write = write_client or SupabaseRest(use_service_role=True)

    async def insert(self, payload: Dict[str, Any]) -> PostRow:
        rows = await self.write.insert("posts", [payload])
        if not rows:
            raise RuntimeError("posts insert 실패 (응답 비어있음)")
        return _parse_row(rows[0])

    async def get(self, post_id: str) -> Optional[PostRow]:
        rows = await self.cli.select(
            "posts",
            params={"id": f"eq.{post_id}", "limit": "1", "select": _CARD_SELECT},
        )
        if not rows:
            return None
        return _parse_row(rows[0])

    async def feed(
        self,
        *,
        sort: str,                      # "latest" | "hot"
        ticker: Optional[str],
        limit: int,
        cursor: Optional[Dict[str, Any]],
    ) -> Tuple[List[PostRow], Optional[Dict[str, Any]]]:
        """커서(keyset) 페이징. (행 목록, 다음 커서) 반환.

        latest: created_at desc — created_at 은 timestamptz(마이크로초)라 사실상
                유니크. keyset = created_at.lt.{cursor.created_at}.
        hot:    fire_count desc, created_at desc — fire_count 정수 동률 빈번 →
                복합 keyset: fire_count < f  OR  (fire_count = f AND created_at < c).
        """
        params: Dict[str, str] = {
            "select": _CARD_SELECT,
            "limit": str(limit),
        }
        if ticker:
            params["ticker"] = f"eq.{ticker}"

        if sort == "hot":
            params["order"] = "fire_count.desc,created_at.desc"
            if cursor:
                f = cursor["fire_count"]
                c = cursor["created_at"]
                # PostgREST or= 안의 컬럼 필터는 점 표기. created_at 은 콜론 포함이라
                # 인코딩 충돌을 피하려 큰따옴표로 감싼다.
                params["or"] = (
                    f'(fire_count.lt.{f},'
                    f'and(fire_count.eq.{f},created_at.lt."{c}"))'
                )
        else:  # latest
            params["order"] = "created_at.desc"
            if cursor:
                params["created_at"] = f'lt.{cursor["created_at"]}'

        rows = await self.cli.select("posts", params=params)
        parsed = [_parse_row(r) for r in rows]

        next_cursor: Optional[Dict[str, Any]] = None
        if len(parsed) == limit and parsed:
            last = parsed[-1]
            next_cursor = {
                "created_at": last.created_at.isoformat(),
                "id": last.id,
            }
            if sort == "hot":
                next_cursor["fire_count"] = last.fire_count
        return parsed, next_cursor

    async def react(
        self, *, post_id: str, visitor_id: str, type_: str
    ) -> Dict[str, int]:
        """react_to_post RPC — upsert + 카운트 재집계(트랜잭션).

        반환: {"fire":, "clap":, "cry":}. 포스트 미존재 등은 RPC 가 예외를
        던지고 httpx 가 4xx → 호출측(서비스)에서 분기.
        """
        data = await self.write.rpc(
            "react_to_post",
            {"p_post_id": post_id, "p_visitor": visitor_id, "p_type": type_},
        )
        if not data:
            raise RuntimeError("react_to_post 응답 비어있음")
        row = data[0]
        return {
            "fire": int(row["fire"]),
            "clap": int(row["clap"]),
            "cry": int(row["cry"]),
        }

    async def my_reaction(
        self, *, post_id: str, visitor_id: str
    ) -> Optional[str]:
        """방문자의 현재 반응 type 조회.

        reactions 는 RLS 로 anon 직접 SELECT 가 차단되므로 service_role 로 조회.
        단건 조회용(피드 N+1 회피 위해 피드에서는 호출 ✕).
        """
        rows = await self.write.select(
            "reactions",
            params={
                "post_id": f"eq.{post_id}",
                "visitor_id": f"eq.{visitor_id}",
                "limit": "1",
                "select": "type",
            },
        )
        if not rows:
            return None
        return rows[0]["type"]
