"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  active: boolean;
  /** 부모가 reset 했을 때 input value 도 비우기 위한 시드. null/0 이면 빈칸. */
  resetKey?: number;
  onSubmit: (salary: number) => void;
};

export function SlideSalary({ active, resetKey, onSubmit }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");

  useEffect(() => {
    if (active && inputRef.current) {
      // 시안과 동일: 슬라이드 전환 후 420ms 뒤 포커스
      const t = setTimeout(() => inputRef.current?.focus(), 420);
      return () => clearTimeout(t);
    }
  }, [active]);

  // 부모가 reset 트리거 → 입력값 비우기 (controlled, DOM 직접 조작 ✕)
  useEffect(() => {
    setValue("");
  }, [resetKey]);

  function handleKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      const raw = value.replace(/[^\d]/g, "");
      const v = parseInt(raw, 10);
      if (v > 0) onSubmit(v * 10_000); // 만원 단위
    }
  }

  return (
    <section className={`slide ${active ? "active" : ""}`} id="s1">
      <div className="q">월급 얼마 받으세요?</div>
      <input
        ref={inputRef}
        className="input-huge"
        type="text"
        inputMode="numeric"
        placeholder="300"
        autoComplete="off"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKey}
        aria-label="월급 (만원)"
      />
      <div className="hint">숫자 입력 후 엔터</div>
    </section>
  );
}
