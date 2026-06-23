"use client";

import { FEATURED_TICKERS, type TickerItem } from "@/lib/tickers";

type Props = {
  active: boolean;
  onSelect: (t: TickerItem) => void;
};

export function SlideStock({ active, onSelect }: Props) {
  return (
    <section className={`slide ${active ? "active" : ""}`} id="s2">
      <div className="q">어떤 거 가지고 있어요?</div>
      <div className="pickers">
        {FEATURED_TICKERS.map((t) => (
          <button
            key={t.code}
            className="pick"
            onClick={() => onSelect(t)}
            aria-label={`${t.name} 선택`}
          >
            {t.name}
          </button>
        ))}
      </div>
      <div className="meta">한 개만 골라도 됩니다</div>
    </section>
  );
}
