import { ImageResponse } from "@vercel/og";
import { NextRequest } from "next/server";

export const runtime = "edge";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

type Share = {
  ticker: string;
  name: string;
  qty: number;
  buy_date: string;
  profit_amount: number;
  profit_pct: number;
  period_start: string;
  period_end: string;
};

async function getShare(id: string): Promise<Share | null> {
  try {
    const r = await fetch(`${API_BASE}/share/${encodeURIComponent(id)}`, {
      cache: "no-store",
    });
    if (!r.ok) return null;
    return (await r.json()) as Share;
  } catch {
    return null;
  }
}

function formatKRW(n: number): string {
  return Math.round(n).toLocaleString("ko-KR");
}

/**
 * OG 카드 1 — Mode 1 (내 두 번째 월급).
 * 04_OG카드설계.md 기준 — 1200×630, 다크, 면책 포함.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } },
) {
  const data = await getShare(params.id);

  // 데이터 없으면 기본 카드 (사이트명만)
  if (!data) {
    return new ImageResponse(
      (
        <div
          style={{
            background: "#000",
            color: "#fff",
            width: "100%",
            height: "100%",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: "center",
            fontFamily: "sans-serif",
          }}
        >
          <div style={{ fontSize: 64, fontWeight: 800, color: "#00ff9c" }}>껄스닥</div>
          <div style={{ fontSize: 24, color: "#6b6b6b", marginTop: 16 }}>
            전일 종가 기준 · 투자 자문 아님
          </div>
        </div>
      ),
      { width: 1200, height: 630 },
    );
  }

  const sign = data.profit_amount >= 0 ? "+" : "";
  const isPositive = data.profit_amount >= 0;
  const bigColor = isPositive ? "#00ff9c" : "#ff5252";

  return new ImageResponse(
    (
      <div
        style={{
          background: "#000",
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          padding: "64px",
          color: "#fff",
          fontFamily: "sans-serif",
        }}
      >
        {/* 상단: 사이트명 */}
        <div
          style={{
            display: "flex",
            fontSize: 28,
            fontWeight: 700,
            color: "#fff",
            letterSpacing: "-0.02em",
          }}
        >
          껄스닥
        </div>

        {/* 중간: 큰 숫자 */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            justifyContent: "center",
          }}
        >
          <div style={{ display: "flex", fontSize: 28, color: "#6b6b6b", marginBottom: 16 }}>
            이번 달 {data.name}이(가) 당신 대신 번 돈
          </div>
          <div
            style={{
              display: "flex",
              fontSize: 160,
              fontWeight: 800,
              color: bigColor,
              letterSpacing: "-0.05em",
              lineHeight: 1,
            }}
          >
            {sign}
            {formatKRW(data.profit_amount)}원
          </div>
          <div
            style={{
              display: "flex",
              fontSize: 26,
              color: "#fff",
              marginTop: 32,
              fontWeight: 600,
            }}
          >
            {data.name} {data.qty.toLocaleString("ko-KR")}주
            <span style={{ color: "#6b6b6b", marginLeft: 16 }}>
              · {data.profit_pct.toFixed(2)}%
            </span>
          </div>
        </div>

        {/* 하단: 면책 */}
        <div
          style={{
            display: "flex",
            fontSize: 18,
            color: "#6b6b6b",
            letterSpacing: "0.02em",
          }}
        >
          {data.period_start} ~ {data.period_end} · 전일 종가 기준 · 투자 자문 아님
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630,
      headers: {
        "Cache-Control": "public, max-age=3600, s-maxage=3600",
      },
    },
  );
}
