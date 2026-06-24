"use client";

import { useCallback, useMemo, useState } from "react";

import { CodeRain } from "@/components/CodeRain";
import { Disclaimer } from "@/components/Disclaimer";
import { SlideDate } from "@/components/SlideDate";
import { SlideIntro } from "@/components/SlideIntro";
import { SlideParallel } from "@/components/SlideParallel";
import { SlideQty } from "@/components/SlideQty";
import { SlideResult } from "@/components/SlideResult";
import { SlideStock } from "@/components/SlideStock";
import { calculate, type CalculateResult } from "@/lib/api";
import type { TickerItem } from "@/lib/tickers";

type Slide = "s1" | "s2" | "s3" | "s4" | "s5" | "s6";

type State = {
  salary: number | null; // 월급은 진입에서 제거 → 결과 화면 토글로 선택 입력
  stock: TickerItem | null;
  qty: number | null;
  yearsAgo: number | null;
  buyDate: string | null; // 평행우주가 mine 과 동일 buy_date 로 비교하도록 보관
};

function buyDateFromYears(yearsAgo: number): string {
  // KST 기준 today - (yearsAgo * 365.25 days)
  const today = new Date();
  const ms = yearsAgo * 365.25 * 24 * 60 * 60 * 1000;
  const past = new Date(today.getTime() - ms);
  return past.toISOString().slice(0, 10);
}

export default function Page() {
  const [slide, setSlide] = useState<Slide>("s1");
  const [s, setS] = useState<State>({
    salary: null,
    stock: null,
    qty: null,
    yearsAgo: null,
    buyDate: null,
  });
  const [result, setResult] = useState<CalculateResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // controlled reset 시드 — 증가시키면 자식 input 값이 빈칸으로 초기화 (DOM 직접 조작 ✕)
  const [resetKey, setResetKey] = useState(0);

  const salaryKrw = useMemo(() => s.salary ?? 0, [s.salary]);

  const runCalculate = useCallback(
    async (ticker: string, qty: number, buyDate: string) => {
      setLoading(true);
      setError(null);
      try {
        const r = await calculate({ ticker, qty, buy_date: buyDate });
        setResult(r);
      } catch (e) {
        setError(e instanceof Error ? e.message : "알 수 없는 오류");
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  function handleStart() {
    // 후크 → 종목 선택으로
    setSlide("s2");
  }

  function handleStock(t: TickerItem) {
    setS((p) => ({ ...p, stock: t }));
    setSlide("s3");
  }

  function handleQty(v: number) {
    setS((p) => ({ ...p, qty: v }));
    setSlide("s4");
  }

  async function handleDate(yearsAgo: number) {
    const buyDate = buyDateFromYears(yearsAgo);
    setS((p) => ({ ...p, yearsAgo, buyDate }));
    setSlide("s5");
    if (!s.stock || !s.qty) return;
    await runCalculate(s.stock.code, s.qty, buyDate);
  }

  // 월급은 진입이 아니라 결과 화면에서 '선택' 입력 (생애단위 비교의 보조 축)
  function handleSalarySubmit(v: number) {
    setS((p) => ({ ...p, salary: v }));
  }

  function handleRestart(e: React.MouseEvent) {
    e.preventDefault();
    setS({
      salary: null,
      stock: null,
      qty: null,
      yearsAgo: null,
      buyDate: null,
    });
    setResult(null);
    setError(null);
    setSlide("s1");
    // 자식 input 들 reset — controlled (DOM 직접 조작 X)
    setResetKey((k) => k + 1);
  }

  function handleShare(e: React.MouseEvent) {
    e.preventDefault();
    const url = typeof window !== "undefined" ? window.location.href : "";
    if (typeof navigator !== "undefined" && navigator.share) {
      navigator
        .share({ title: "껄스닥", text: "그때 살걸 그 종목, 지금 얼마였나 봤다", url })
        .catch(() => {
          // 사용자가 취소하면 무시
        });
    } else if (typeof navigator !== "undefined") {
      navigator.clipboard?.writeText(url).catch(() => {});
    }
  }

  function handleParallel() {
    // 평행우주(종목대체형): 서버 /parallel 로 mine vs alt 재계산.
    // (기존 ×5 클라 시뮬은 폐기 — 서버가 진실, 설계 원칙 2)
    if (!result || !s.stock || s.qty == null || !s.buyDate) return;
    setSlide("s6");
  }

  function handleBackToResult() {
    setSlide("s5");
  }

  return (
    <main>
      <CodeRain />
      <a href="#" className="brandmark" onClick={handleRestart}>껄스닥</a>
      <Disclaimer />

      <SlideIntro active={slide === "s1"} onStart={handleStart} />
      <SlideStock active={slide === "s2"} onSelect={handleStock} />
      <SlideQty
        active={slide === "s3"}
        stockName={s.stock?.name ?? ""}
        resetKey={resetKey}
        onSubmit={handleQty}
      />
      <SlideDate active={slide === "s4"} onSelect={handleDate} />
      <SlideResult
        active={slide === "s5"}
        data={result}
        salaryKrw={salaryKrw}
        resetKey={resetKey}
        loading={loading}
        error={error}
        onSalarySubmit={handleSalarySubmit}
        onParallel={handleParallel}
      />
      <SlideParallel
        active={slide === "s6"}
        myStock={s.stock}
        qty={s.qty}
        buyDate={s.buyDate}
      />

      <div className="actions">
        {slide === "s6" && (
          <a href="#" onClick={(e) => { e.preventDefault(); handleBackToResult(); }}>
            결과로
          </a>
        )}
        <a href="#" onClick={handleRestart}>
          처음부터
        </a>
        <a href="#" onClick={handleShare}>
          공유
        </a>
        {/* 커뮤니티 진입 (설계 Q5=C: 직접 진입 탭) */}
        <a href="/feed">자랑 피드</a>
      </div>
    </main>
  );
}
