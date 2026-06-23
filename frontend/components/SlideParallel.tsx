"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type { ParallelResult } from "@/lib/api";
import { parallel } from "@/lib/api";
import { countUp, formatKRW } from "@/lib/format";
import { FEATURED_TICKERS, type TickerItem } from "@/lib/tickers";

type Props = {
  active: boolean;
  /** 내 종목 (비교 기준). 없으면 picker 만 노출 안 함 */
  myStock: TickerItem | null;
  qty: number | null;
  buyDate: string | null;
};

/**
 * 평행우주 (종목대체형) — "만약 OO 샀다면".
 *
 * 서버 /parallel 호출(클라 시뮬 폐기). 같은 주식 수(qty 고정)로 내 종목 vs
 * 대체 종목의 이번 달 수익을 나란히 비교. diff.verdict 로 승패 카피 결정.
 */
export function SlideParallel({ active, myStock, qty, buyDate }: Props) {
  const [alt, setAlt] = useState<TickerItem | null>(null);
  const [query, setQuery] = useState("");
  const [data, setData] = useState<ParallelResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deltaRef = useRef<HTMLDivElement>(null);
  const barMineRef = useRef<HTMLElement>(null);
  const barAltRef = useRef<HTMLElement>(null);

  // 내 종목은 비교 대상에서 제외 + 검색 필터(단순 includes — 신규 라이브러리 ✕)
  const candidates = useMemo(() => {
    const q = query.trim().toLowerCase();
    return FEATURED_TICKERS.filter((t) => {
      if (myStock && t.code === myStock.code) return false;
      if (!q) return true;
      return (
        t.name.toLowerCase().includes(q) || t.code.toLowerCase().includes(q)
      );
    });
  }, [query, myStock]);

  // 슬라이드를 벗어나면 상태 초기화 (다시 들어올 때 깨끗하게)
  useEffect(() => {
    if (!active) {
      setAlt(null);
      setData(null);
      setError(null);
      setQuery("");
    }
  }, [active]);

  async function handlePick(t: TickerItem) {
    if (!myStock || qty == null || !buyDate) return;
    setAlt(t);
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const r = await parallel({
        ticker: myStock.code,
        qty,
        buy_date: buyDate,
        alt_ticker: t.code,
      });
      setData(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "알 수 없는 오류");
    } finally {
      setLoading(false);
    }
  }

  // 결과 애니메이션 — 차액 카운트업 + 비교 막대
  useEffect(() => {
    if (!active || !data || !deltaRef.current) return;

    const delta = data.diff.amount_delta_krw;
    const cleanup = countUp(delta, (v) => {
      if (!deltaRef.current) return;
      const sign = v >= 0 ? "+" : "";
      deltaRef.current.innerHTML =
        sign + formatKRW(v) + '<span class="won">원</span>';
    });
    deltaRef.current.classList.remove("positive", "negative");
    if (delta > 0) deltaRef.current.classList.add("positive");
    else if (delta < 0) deltaRef.current.classList.add("negative");

    const mineP = data.mine.profit_amount_krw;
    const altP = data.alt.profit_amount_krw;
    const max = Math.max(Math.abs(mineP), Math.abs(altP), 1);
    const barTimer = setTimeout(() => {
      if (barMineRef.current) {
        barMineRef.current.style.width = (Math.abs(mineP) / max) * 100 + "%";
      }
      if (barAltRef.current) {
        barAltRef.current.style.width = (Math.abs(altP) / max) * 100 + "%";
      }
    }, 80);

    return () => {
      cleanup();
      clearTimeout(barTimer);
    };
  }, [active, data]);

  function verdictText(r: ParallelResult): string {
    const altName = r.alt.name;
    const myName = r.mine.name;
    switch (r.diff.verdict) {
      case "alt_better":
        return `${altName} 샀으면 더 벌었네요`;
      case "mine_better":
        return `그래도 ${myName}가 나았어요`;
      default:
        return `${altName}나 ${myName}나 똑같았어요`;
    }
  }

  return (
    <section className={`slide ${active ? "active" : ""}`} id="s6">
      {/* 1) 대체종목 선택 단계 */}
      {!data && !loading && (
        <>
          <div className="q">만약 다른 걸 샀다면?</div>
          <input
            className="parallel-search"
            type="text"
            inputMode="text"
            placeholder="종목 검색"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="대체 종목 검색"
          />
          <div className="pickers">
            {candidates.map((t) => (
              <button
                key={t.code}
                className={`pick ${alt?.code === t.code ? "on" : ""}`}
                onClick={() => handlePick(t)}
                aria-label={`${t.name} 와 비교`}
              >
                {t.name}
              </button>
            ))}
            {candidates.length === 0 && (
              <div className="meta">검색 결과가 없어요</div>
            )}
          </div>
          <div className="meta">
            {myStock
              ? `${myStock.name} 대신 샀다면 얼마였을지 비교해요`
              : "비교할 내 종목이 없어요"}
          </div>
          {error && <div className="caption">{error}</div>}
        </>
      )}

      {/* 2) 로딩 */}
      {loading && (
        <>
          <div className="num">…</div>
          <div className="loader">평행우주 계산 중</div>
        </>
      )}

      {/* 3) 비교 결과 */}
      {!loading && data && (
        <>
          <div className="caption" style={{ marginTop: 0, marginBottom: 8 }}>
            {data.diff.verdict === "alt_better" ? (
              <>
                만약 <b>{data.alt.name}</b>를 샀다면
              </>
            ) : (
              <>
                <b>{data.mine.name}</b> vs <b>{data.alt.name}</b>
              </>
            )}
          </div>
          <div ref={deltaRef} className="num">
            +0<span className="won">원</span>
          </div>
          <div className="caption">{verdictText(data)}</div>

          <div className="compare">
            <div className="cmp-row">
              <div className="lbl">{data.mine.name}</div>
              <div className="bar">
                <i
                  ref={barMineRef}
                  className={data.diff.verdict === "mine_better" ? "big" : ""}
                />
              </div>
              <div className="val">
                {(data.mine.profit_amount_krw >= 0 ? "+" : "") +
                  formatKRW(data.mine.profit_amount_krw)}
                원
              </div>
            </div>
            <div className="cmp-row">
              <div className="lbl">{data.alt.name}</div>
              <div className="bar">
                <i
                  ref={barAltRef}
                  className={data.diff.verdict === "alt_better" ? "big" : ""}
                />
              </div>
              <div className="val">
                {(data.alt.profit_amount_krw >= 0 ? "+" : "") +
                  formatKRW(data.alt.profit_amount_krw)}
                원
              </div>
            </div>
          </div>

          <button
            className="parallel-btn"
            onClick={() => {
              setData(null);
              setError(null);
              setAlt(null);
            }}
          >
            다른 종목으로 다시 비교
          </button>
        </>
      )}
    </section>
  );
}
