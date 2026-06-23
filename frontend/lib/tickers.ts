/**
 * 프론트엔드 종목 picker — 시안 8종목 + 알파 (curation).
 * 백엔드 batch/tickers.py 와 동기화. 본 사이클은 정적 배열.
 */
export type TickerItem = {
  code: string; // KR 6자리 또는 US 알파벳
  name: string; // 한글 표시명
  market: "KR" | "US";
};

export const FEATURED_TICKERS: TickerItem[] = [
  // 시안 8종목
  { code: "000660", name: "SK하이닉스", market: "KR" },
  { code: "005930", name: "삼성전자", market: "KR" },
  { code: "NVDA", name: "엔비디아", market: "US" },
  { code: "TSLA", name: "테슬라", market: "US" },
  { code: "AAPL", name: "애플", market: "US" },
  { code: "035420", name: "네이버", market: "KR" },
  { code: "373220", name: "LG에너지솔루션", market: "KR" },
  { code: "207940", name: "삼성바이오로직스", market: "KR" },
];
