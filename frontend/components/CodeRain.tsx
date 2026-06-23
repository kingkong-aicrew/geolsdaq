"use client";

import { useEffect, useRef } from "react";

/**
 * 매트릭스 코드레인 배경 — 종목코드·등락률이 초록 비처럼 흐른다.
 * 시안(hero_v2) 톤. 캔버스 1개, requestAnimationFrame, 가벼운 부하.
 * - pointer-events 없음(배경), prefers-reduced-motion 존중.
 * - 글자 소스: 실제 종목코드/티커 + 등락률 → "데이터가 쏟아진다" 느낌.
 */
const GLYPHS = [
  "005930", "000660", "035420", "035720", "051910", "207940",
  "NVDA", "TSLA", "AAPL", "MSFT", "GOOGL", "META", "AMZN",
  "+12.4%", "-8.1%", "+340%", "-27%", "+1.4%", "-15.5%", "+16.9%",
  "KOSPI", "KOSDAQ", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
];

export function CodeRain() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    const FONT_SIZE = 16;
    let cols = 0;
    let drops: number[] = [];
    let speeds: number[] = [];

    function resize() {
      if (!canvas) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      canvas.style.width = window.innerWidth + "px";
      canvas.style.height = window.innerHeight + "px";
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      cols = Math.ceil(window.innerWidth / (FONT_SIZE * 3.2));
      drops = Array.from({ length: cols }, () =>
        Math.floor((Math.random() * window.innerHeight) / FONT_SIZE),
      );
      speeds = Array.from({ length: cols }, () => 0.4 + Math.random() * 0.8);
    }

    function pick(i: number): string {
      // 컬럼·행마다 결정적이지 않게(시각적 랜덤). index 기반 변주.
      // drops[i] 는 소수(speed 누적) → Math.floor 로 정수 인덱스 보장.
      const idx = Math.floor(i * 7 + Math.floor(drops[i]) * 13) % GLYPHS.length;
      return GLYPHS[idx];
    }

    let raf = 0;
    let last = 0;

    function frame(t: number) {
      raf = requestAnimationFrame(frame);
      if (t - last < 70) return; // ~14fps (은은하게 + 가벼움)
      last = t;
      if (!canvas) return;
      // 잔상(트레일) — 반투명 검정 덮기
      ctx!.fillStyle = "rgba(0, 0, 0, 0.16)";
      ctx!.fillRect(0, 0, window.innerWidth, window.innerHeight);
      ctx!.font = `700 ${FONT_SIZE}px "JetBrains Mono", monospace`;
      for (let i = 0; i < cols; i++) {
        const x = i * FONT_SIZE * 3.2 + 4;
        const y = drops[i] * FONT_SIZE;
        // 선두 글자는 밝게, 뒤는 어둡게
        ctx!.fillStyle = "rgba(0, 255, 156, 0.85)";
        ctx!.fillText(pick(i), x, y);
        if (y > window.innerHeight && Math.random() > 0.975) {
          drops[i] = 0;
        }
        drops[i] += speeds[i];
      }
    }

    resize();
    window.addEventListener("resize", resize);
    if (!reduce) {
      raf = requestAnimationFrame(frame);
    } else {
      // 모션 최소화 옵션: 정적 1프레임만
      ctx.font = `700 ${FONT_SIZE}px "JetBrains Mono", monospace`;
      ctx.fillStyle = "rgba(0, 255, 156, 0.25)";
      for (let i = 0; i < cols; i++) {
        ctx.fillText(pick(i), i * FONT_SIZE * 3.2 + 4, drops[i] * FONT_SIZE);
      }
    }

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={canvasRef} className="code-rain" aria-hidden="true" />;
}
