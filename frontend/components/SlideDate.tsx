"use client";

type Props = {
  active: boolean;
  onSelect: (yearsAgo: number) => void;
};

const OPTIONS: Array<{ years: number; label: string }> = [
  { years: 0.5, label: "반 년 전" },
  { years: 1, label: "1년 전" },
  { years: 2, label: "2년 전" },
  { years: 3, label: "3년 전" },
  { years: 5, label: "5년 전" },
  { years: 10, label: "10년 전" },
];

export function SlideDate({ active, onSelect }: Props) {
  return (
    <section className={`slide ${active ? "active" : ""}`} id="s4">
      <div className="q">언제 샀어요?</div>
      <div className="pickers">
        {OPTIONS.map((o) => (
          <button
            key={o.years}
            className="pick"
            onClick={() => onSelect(o.years)}
            aria-label={o.label}
          >
            {o.label}
          </button>
        ))}
      </div>
    </section>
  );
}
