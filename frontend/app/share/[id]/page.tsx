import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Disclaimer } from "@/components/Disclaimer";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const SITE_ORIGIN =
  process.env.NEXT_PUBLIC_SITE_ORIGIN || "http://localhost:3000";

type Share = {
  id: string;
  created_at: string;
  ticker: string;
  name: string;
  qty: number;
  buy_date: string;
  profit_amount: number;
  profit_pct: number;
  period_start: string;
  period_end: string;
  og_image_url: string;
  disclaimer: string;
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

export async function generateMetadata({
  params,
}: {
  params: { id: string };
}): Promise<Metadata> {
  const data = await getShare(params.id);
  if (!data) {
    return { title: "껄스닥" };
  }
  const sign = data.profit_amount >= 0 ? "+" : "";
  const title = `껄스닥 ${sign}${Math.round(data.profit_amount).toLocaleString("ko-KR")}원`;
  const description = `이번 달 ${data.name}이(가) 당신 대신 번 돈`;
  const canonical = `${SITE_ORIGIN.replace(/\/+$/, "")}/share/${encodeURIComponent(params.id)}`;

  return {
    title,
    description,
    alternates: { canonical },
    openGraph: {
      title,
      description,
      url: canonical,
      images: [{ url: data.og_image_url, width: 1200, height: 630 }],
      locale: "ko_KR",
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [data.og_image_url],
    },
  };
}

function formatKRW(n: number): string {
  return Math.round(n).toLocaleString("ko-KR");
}

export default async function SharePage({
  params,
}: {
  params: { id: string };
}) {
  const data = await getShare(params.id);
  if (!data) notFound();

  const sign = data.profit_amount >= 0 ? "+" : "";
  const numClass =
    data.profit_amount > 0
      ? "num positive"
      : data.profit_amount < 0
      ? "num negative"
      : "num";

  return (
    <main className="slide active share-page">
      <Disclaimer />
      <div className={numClass}>
        {sign}
        {formatKRW(data.profit_amount)}
        <span className="won">원</span>
      </div>
      <div className="caption">
        이번 달 <b>{data.name}</b>이(가) 당신 대신 번 돈
      </div>
      <div className="meta">
        {data.qty.toLocaleString("ko-KR")}주 · {data.buy_date} 매수 ·{" "}
        {data.profit_pct.toFixed(2)}%
      </div>

      <div className="actions">
        <a href="/">처음부터</a>
      </div>
    </main>
  );
}
