/**
 * 숫자 포맷 + 카운트업 헬퍼.
 * 시안: ko-KR locale, ease-out, 1800ms.
 */
export function formatKRW(n: number): string {
  return Math.round(n).toLocaleString("ko-KR");
}

export function formatPct(p: number): string {
  const sign = p > 0 ? "+" : "";
  return `${sign}${p.toFixed(2)}%`;
}

export function withSign(n: number): string {
  return (n >= 0 ? "+" : "") + formatKRW(n);
}

/**
 * 카운트업 — rAF, 1800ms ease-out (시안과 동일).
 * onTick: 매 프레임 호출되는 값.
 */
export function countUp(
  target: number,
  onTick: (current: number) => void,
  durationMs = 1800,
): () => void {
  let cancelled = false;
  const start = performance.now();
  const from = 0;

  function step(now: number) {
    if (cancelled) return;
    const p = Math.min(1, (now - start) / durationMs);
    const eased = 1 - Math.pow(1 - p, 4);
    const v = from + (target - from) * eased;
    onTick(v);
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);

  return () => {
    cancelled = true;
  };
}
