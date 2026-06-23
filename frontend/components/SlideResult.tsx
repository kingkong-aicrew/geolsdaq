"use client";

import { useEffect, useRef, useState } from "react";
import type { CalculateResult } from "@/lib/api";
import { submitStash } from "@/lib/api";
import { countUp, formatKRW } from "@/lib/format";

type Props = {
  active: boolean;
  data: CalculateResult | null;
  salaryKrw: number;
  loading: boolean;
  error: string | null;
  onParallel: () => void;
};

export function SlideResult({
  active,
  data,
  salaryKrw,
  loading,
  error,
  onParallel,
}: Props) {
  const numRef = useRef<HTMLDivElement>(null);
  const barWageRef = useRef<HTMLElement>(null);
  const barCapRef = useRef<HTMLElement>(null);
  const valWageRef = useRef<HTMLDivElement>(null);
  const valCapRef = useRef<HTMLDivElement>(null);

  const [stashing, setStashing] = useState(false);
  const [stashDone, setStashDone] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!active || !data || !numRef.current) return;

    // 카운트업 (시안: 1800ms ease-out)
    const target = data.profit_amount_krw;
    const cleanup = countUp(target, (v) => {
      if (!numRef.current) return;
      const sign = target >= 0 ? "+" : v < 0 ? "" : "";
      numRef.current.innerHTML =
        sign + formatKRW(v) + '<span class="won">원</span>';
    });

    // 색상
    if (numRef.current) {
      numRef.current.classList.remove("positive", "negative");
      if (target > 0) numRef.current.classList.add("positive");
      else if (target < 0) numRef.current.classList.add("negative");
    }

    // 비교 막대
    const wage = salaryKrw;
    const max = Math.max(wage, Math.abs(target));
    if (valWageRef.current) valWageRef.current.textContent = formatKRW(wage) + "원";
    if (valCapRef.current)
      valCapRef.current.textContent =
        (target >= 0 ? "+" : "") + formatKRW(target) + "원";
    const barTimer = setTimeout(() => {
      if (barWageRef.current) {
        barWageRef.current.style.width = (wage / max) * 100 + "%";
      }
      if (barCapRef.current) {
        barCapRef.current.style.width = (Math.abs(target) / max) * 100 + "%";
      }
    }, 80);

    return () => {
      cleanup();
      clearTimeout(barTimer);
    };
  }, [active, data, salaryKrw]);

  async function handleFlex() {
    if (!data || stashing || stashDone) return;
    setStashing(true);
    try {
      const r = await submitStash({
        ticker: data.ticker,
        qty: data.qty,
        buy_date: data.buy_date,
      });
      setStashDone(true);
      setToast("등재 완료 · 익명으로 랭킹 반영");
      // share URL 복사 옵션
      if (typeof window !== "undefined") {
        const url = `${window.location.origin}/share/${r.id}`;
        try {
          await navigator.clipboard?.writeText(url);
        } catch {
          /* clipboard 실패는 무시 */
        }
      }
      setTimeout(() => setToast(null), 2500);
    } catch (e) {
      setToast(e instanceof Error ? e.message : "등재 실패");
      setTimeout(() => setToast(null), 3000);
    } finally {
      setStashing(false);
    }
  }

  return (
    <section className={`slide ${active ? "active" : ""}`} id="s5">
      {loading && (
        <>
          <div className="num">…</div>
          <div className="loader">계산 중</div>
        </>
      )}
      {error && !loading && (
        <>
          <div className="num negative" style={{ fontSize: "clamp(32px,5vw,72px)" }}>
            계산 실패
          </div>
          <div className="caption">{error}</div>
        </>
      )}
      {!loading && !error && data && (
        <>
          <div
            ref={numRef}
            className={`num ${data.profit_amount_krw >= 0 ? "positive" : "negative"}`}
          >
            +0<span className="won">원</span>
          </div>
          <div className="caption">
            이번 달 <b>{data.name}</b>이(가) 당신 대신 번 돈
          </div>

          <div className="compare">
            <div className="cmp-row">
              <div className="lbl">내 월급</div>
              <div className="bar">
                <i ref={barWageRef} />
              </div>
              <div className="val" ref={valWageRef}>
                0원
              </div>
            </div>
            <div className="cmp-row">
              <div className="lbl">주식이 번 돈</div>
              <div className="bar">
                <i className="big" ref={barCapRef} />
              </div>
              <div className="val" ref={valCapRef}>
                0원
              </div>
            </div>
          </div>

          <button
            className={`flex-btn ${stashDone ? "done" : ""}`}
            onClick={handleFlex}
            disabled={stashing || stashDone}
          >
            {stashDone
              ? "등재 완료 · 익명으로 랭킹 반영"
              : stashing
              ? "등재 중…"
              : "천하제일 주식자랑대회 등재 →"}
          </button>
          <button className="parallel-btn" onClick={onParallel}>
            5년 전에 샀더라면? 평행우주 보기
          </button>
        </>
      )}
      {toast && <div className="toast">{toast}</div>}
    </section>
  );
}
