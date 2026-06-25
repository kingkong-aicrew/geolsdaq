"use client";

import { useEffect, useRef, useState } from "react";
import type { CalculateResult, PercentileResult } from "@/lib/api";
import { createPost, fetchPercentile } from "@/lib/api";
import { countUp, formatKRW } from "@/lib/format";

// 생애단위 환산 기준 — 한국 공식 통계 (추측 아님, 출처 주석 필수)
const PENSION_MONTHLY = 679_924; // 국민연금공단 2025.7 전체 노령연금 월평균 수령액
const EDU_MONTHLY = 474_000; // 통계청 2024 초중고 사교육비 전체학생 1인당 월평균
const SEOUL_JEONSE = 660_000_000; // 서울 아파트 평균 전세 ≈ 6.6억 (2024~2025 공개 시세 기준; 지역·시점 변동, 정부기관 출처 단언 회피)

type Props = {
  active: boolean;
  data: CalculateResult | null;
  salaryKrw: number;
  resetKey?: number;
  loading: boolean;
  error: string | null;
  onSalarySubmit: (salaryKrw: number) => void;
  onParallel: () => void;
};

function fmtMonths(m: number): string {
  if (!isFinite(m) || m <= 0) return "0개월치";
  if (m >= 12) {
    let y = Math.floor(m / 12);
    let rem = Math.round(m % 12);
    if (rem === 12) {
      // m % 12 가 [11.5, 12) 이면 반올림이 12 → "1년 12개월치" 방지(carry)
      y += 1;
      rem = 0;
    }
    return rem > 0 ? `${y}년 ${rem}개월치` : `${y}년치`;
  }
  return `${m.toFixed(1)}개월치`;
}

function fmtPct(p: number): string {
  if (!isFinite(p) || p <= 0) return "0%";
  if (p >= 10) return `${Math.round(p)}%`;
  if (p >= 1) return `${p.toFixed(1)}%`;
  return `${p.toFixed(2)}%`;
}

// 시장 상위 % — 서버 percentile(나보다 못한 비율)의 보수(better 비율).
// 0 방지: 1% 하한(전수에서 최상위라도 "상위 1%"로 표기).
function topPctLabel(percentile: number): string {
  const top = Math.max(1, Math.round(100 - percentile));
  return `${top}%`;
}

// buy_date → "N년 전" / "N개월 전" 라벨 (그때 샀다면 시점 표시)
function agoLabel(buyDate: string): string {
  const buy = new Date(buyDate);
  const now = new Date();
  let months =
    (now.getFullYear() - buy.getFullYear()) * 12 +
    (now.getMonth() - buy.getMonth());
  if (months < 0) months = 0;
  if (months >= 12) return `${Math.round(months / 12)}년 전`;
  if (months >= 1) return `${months}개월 전`;
  return "최근";
}

export function SlideResult({
  active,
  data,
  salaryKrw,
  resetKey,
  loading,
  error,
  onSalarySubmit,
  onParallel,
}: Props) {
  const numRef = useRef<HTMLDivElement>(null);

  const [stashing, setStashing] = useState(false);
  const [stashDone, setStashDone] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [showSalary, setShowSalary] = useState(false);
  const [salaryInput, setSalaryInput] = useState("");
  // %지표(순위2) — 서버값만. 실패해도 결과는 표시(graceful degradation).
  const [pctl, setPctl] = useState<PercentileResult | null>(null);
  // cold start(Render 무료 슬립 깨우기) 안내 — 로딩이 4초+ 지속되면 노출
  const [slowHint, setSlowHint] = useState(false);

  // 부모 reset(처음부터) → 월급 토글/입력·등재 상태 초기화
  useEffect(() => {
    setShowSalary(false);
    setSalaryInput("");
    setStashDone(false);
    setPctl(null);
  }, [resetKey]);

  // 로딩이 4초 넘으면 cold start(서버 깨우는 중) 안내로 전환 — 멈춤 오인 방지
  useEffect(() => {
    if (!loading) {
      setSlowHint(false);
      return;
    }
    const t = setTimeout(() => setSlowHint(true), 4000);
    return () => clearTimeout(t);
  }, [loading]);

  // 결과가 보일 때 시장 분위% 조회 — 실패는 조용히 무시(결과 노출 우선)
  useEffect(() => {
    if (!active || !data) {
      setPctl(null);
      return;
    }
    let alive = true;
    setPctl(null);
    fetchPercentile({ ticker: data.ticker, buy_date: data.buy_date })
      .then((r) => {
        if (alive) setPctl(r);
      })
      .catch(() => {
        if (alive) setPctl(null);
      });
    return () => {
      alive = false;
    };
  }, [active, data]);

  useEffect(() => {
    if (!active || !data || !numRef.current) return;

    // 거대숫자 카운트업 (시안: 1800ms ease-out)
    const target = data.profit_amount_krw;
    const cleanup = countUp(target, (v) => {
      if (!numRef.current) return;
      const sign = target >= 0 ? "+" : v < 0 ? "" : "";
      numRef.current.innerHTML =
        sign + formatKRW(v) + '<span class="won">원</span>';
    });

    if (numRef.current) {
      numRef.current.classList.remove("positive", "negative");
      if (target > 0) numRef.current.classList.add("positive");
      else if (target < 0) numRef.current.classList.add("negative");
    }

    return () => cleanup();
  }, [active, data]);

  async function handleFlex() {
    if (!data || stashing || stashDone) return;
    setStashing(true);
    try {
      const r = await createPost({
        ticker: data.ticker,
        qty: data.qty,
        buy_date: data.buy_date,
        origin: "direct",
      });
      setStashDone(true);
      setToast("등재 완료 · 피드로 이동해요");
      // 등재된 카드로 바로 이동 + 하이라이트
      if (typeof window !== "undefined") {
        window.location.href = `/feed?highlight=${encodeURIComponent(r.id)}`;
      }
    } catch (e) {
      setToast(e instanceof Error ? e.message : "등재 실패");
      setTimeout(() => setToast(null), 3000);
      setStashing(false);
    }
  }

  function handleSalaryKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== "Enter") return;
    const raw = salaryInput.replace(/[^\d]/g, "");
    const v = parseInt(raw, 10);
    if (v > 0) {
      onSalarySubmit(v * 10_000); // 만원 단위
      setShowSalary(false);
    }
  }

  const profit = data?.profit_amount_krw ?? 0;
  const abs = Math.abs(profit);
  const gain = profit >= 0;

  return (
    <section className={`slide ${active ? "active" : ""}`} id="s5">
      {loading && (
        <>
          <div className="num">…</div>
          <div className="loader">
            {slowHint
              ? "서버 깨우는 중… 처음엔 최대 1분 걸려요"
              : "그때 그 종목 찾는 중…"}
          </div>
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
            className={`num ${gain ? "positive" : "negative"}`}
          >
            +0<span className="won">원</span>
          </div>
          <div className="caption">
            {agoLabel(data.buy_date)} <b>{data.name}</b> 샀다면, 지금
          </div>

          <div className="life-compare">
            <div className="life-head">
              {gain ? "놓친 수익, 환산하면" : "피한 손실, 환산하면"}
            </div>
            <ul className="life-list">
              <li>
                <span className="life-lbl">국민연금</span>
                <span className="life-val">{fmtMonths(abs / PENSION_MONTHLY)}</span>
              </li>
              <li>
                <span className="life-lbl">자녀 학원비</span>
                <span className="life-val">{fmtMonths(abs / EDU_MONTHLY)}</span>
              </li>
              <li>
                <span className="life-lbl">서울 아파트 전셋값</span>
                <span className="life-val">{fmtPct((abs / SEOUL_JEONSE) * 100)}</span>
              </li>
              {salaryKrw > 0 && (
                <li className="mine">
                  <span className="life-lbl">내 월급</span>
                  <span className="life-val">{fmtMonths(abs / salaryKrw)}</span>
                </li>
              )}
            </ul>
            <div className="life-note">
              {gain
                ? "그때 샀어야 했는데… 이미 지난 기회."
                : "안 사길, 천만다행이네요."}
            </div>
            <div className="life-src">
              기준: 국민연금공단·통계청 공식 통계 · 서울 전셋값은 공개 시세
            </div>

            {pctl && pctl.total_count > 0 && (
              <div className="market-rank">
                <div className="market-rank-head">
                  시장 상위 {topPctLabel(pctl.percentile)} · 다 같이 버티는 중
                </div>
                <div className="market-rank-sub">{pctl.headline}</div>
              </div>
            )}

            {salaryKrw <= 0 && !showSalary && (
              <button
                className="salary-toggle"
                onClick={() => setShowSalary(true)}
              >
                월급으로도 환산해보기
              </button>
            )}
            {salaryKrw <= 0 && showSalary && (
              <div className="salary-inline">
                <input
                  type="text"
                  inputMode="numeric"
                  placeholder="300"
                  autoFocus
                  value={salaryInput}
                  onChange={(e) => setSalaryInput(e.target.value)}
                  onKeyDown={handleSalaryKey}
                  aria-label="월급 (만원)"
                />
                <span className="unit">만원 · 엔터</span>
              </div>
            )}
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
            그때 다른 종목 샀다면? 평행우주
          </button>
        </>
      )}
      {toast && <div className="toast">{toast}</div>}
    </section>
  );
}
