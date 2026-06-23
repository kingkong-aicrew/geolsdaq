"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  active: boolean;
  stockName: string;
  /** 부모가 reset 했을 때 input value 도 비우기 위한 시드. */
  resetKey?: number;
  onSubmit: (qty: number) => void;
};

export function SlideQty({ active, stockName, resetKey, onSubmit }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");

  useEffect(() => {
    if (active && inputRef.current) {
      const t = setTimeout(() => inputRef.current?.focus(), 420);
      return () => clearTimeout(t);
    }
  }, [active]);

  useEffect(() => {
    setValue("");
  }, [resetKey]);

  function handleKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      const raw = value.replace(/[^\d]/g, "");
      const v = parseInt(raw, 10);
      if (v > 0) onSubmit(v);
    }
  }

  return (
    <section className={`slide ${active ? "active" : ""}`} id="s3">
      <div className="q">{stockName ? `${stockName} 몇 주?` : "몇 주?"}</div>
      <input
        ref={inputRef}
        className="input-huge"
        type="text"
        inputMode="numeric"
        placeholder="10"
        autoComplete="off"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKey}
        aria-label="보유 수량"
      />
      <div className="hint">숫자 입력 후 엔터</div>
    </section>
  );
}
