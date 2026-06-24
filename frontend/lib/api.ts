/**
 * 백엔드 API 호출.
 * NEXT_PUBLIC_API_BASE: 빌드 시 주입. localhost:8000 기본.
 */
const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE) ||
  "http://localhost:8000";

export type CalculateResult = {
  ticker: string;
  name: string;
  market: "KR" | "US";
  qty: number;
  buy_date: string; // YYYY-MM-DD
  period_start: string;
  period_end: string;
  price_period_start: number;
  price_period_end: number;
  profit_amount_krw: number;
  profit_pct: number;
  disclaimer: string;
};

export type StashResult = {
  id: string;
  profit_amount: number;
  profit_pct: number;
  disclaimer: string;
};

export type ParallelVerdict = "alt_better" | "mine_better" | "tie";

export type ParallelResult = {
  mine: CalculateResult;
  alt: CalculateResult;
  diff: {
    amount_delta_krw: number; // alt.profit - mine.profit (양수=대체가 더 벌었음)
    pct_delta: number;
    verdict: ParallelVerdict;
  };
  disclaimer: string;
};

export type LeaderboardEntry = {
  id: string;
  created_at: string;
  ticker: string;
  name: string;
  qty: number;
  buy_date: string;
  profit_amount: number;
  profit_pct: number;
};

export type LeaderboardResult = {
  sort: "amount" | "pct";
  period: "month";
  ticker: string | null;
  entries: LeaderboardEntry[];
  disclaimer: string;
};

async function jsonFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    // 네트워크 끊김·CORS·타임아웃 → 영문 "Failed to fetch" 대신 한글 안내.
    throw new Error("서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.");
  }
  if (!res.ok) {
    let detail = "잠시 후 다시 시도해 주세요.";
    try {
      const body = await res.json();
      // 백엔드는 모든 4xx/5xx 를 한글 detail 로 내려줌 → 그대로 노출.
      if (body?.detail) detail = body.detail;
    } catch {
      // body 가 JSON 이 아니면 기본 안내 문구 유지.
    }
    // status 코드 prefix 제거 — 사용자에겐 불필요(개발용은 백엔드 로그에).
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export function calculate(input: {
  ticker: string;
  qty: number;
  buy_date: string;
}): Promise<CalculateResult> {
  return jsonFetch<CalculateResult>("/calculate", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function submitStash(input: {
  ticker: string;
  qty: number;
  buy_date: string;
}): Promise<StashResult> {
  return jsonFetch<StashResult>("/stash", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function parallel(input: {
  ticker: string;
  qty: number;
  buy_date: string;
  alt_ticker: string;
}): Promise<ParallelResult> {
  return jsonFetch<ParallelResult>("/parallel", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchLeaderboard(params: {
  sort?: "amount" | "pct";
  ticker?: string;
  limit?: number;
} = {}): Promise<LeaderboardResult> {
  const qs = new URLSearchParams();
  qs.set("sort", params.sort ?? "amount");
  qs.set("period", "month");
  if (params.ticker) qs.set("ticker", params.ticker);
  if (params.limit) qs.set("limit", String(params.limit));
  return jsonFetch<LeaderboardResult>(`/leaderboard?${qs.toString()}`);
}

export type ShareResult = CalculateResult & {
  id: string;
  created_at: string;
  og_image_url: string;
};

export function fetchShare(id: string): Promise<ShareResult> {
  return jsonFetch<ShareResult>(`/share/${encodeURIComponent(id)}`);
}

// ---------- %지표 (순위2 — 시장 분위·위로/연대 프레이밍) ----------

export type PercentileResult = {
  ticker: string;
  name: string;
  market: "KR" | "US";
  buy_date: string; // YYYY-MM-DD
  period_start: string;
  period_end: string;
  profit_pct: number; // 내 종목 보유 수익률(%)
  total_count: number; // 같은 기간 분포 모수(전수)
  worse_count: number; // 나보다 수익률이 낮은 종목 수(= 같이 버티는 개수)
  better_count: number; // 나보다 수익률이 높은 종목 수
  percentile: number; // worse_count / total_count * 100 (0~100, 높을수록 선방)
  headline: string; // 서버 생성 위로·연대 카피(가드레일 통과)
  disclaimer: string;
};

export function fetchPercentile(input: {
  ticker: string;
  buy_date: string;
}): Promise<PercentileResult> {
  const qs = new URLSearchParams();
  qs.set("ticker", input.ticker);
  qs.set("buy_date", input.buy_date);
  return jsonFetch<PercentileResult>(`/percentile?${qs.toString()}`);
}

// ---------- 커뮤니티 (Phase B — posts / feed / react) ----------

export type ReactionType = "fire" | "clap" | "cry";
export type FeedSort = "latest" | "hot";
export type PostOrigin = "direct" | "parallel";

export type PostCard = {
  id: string;
  created_at: string;
  ticker: string;
  name: string;
  qty: number;
  buy_date: string;
  profit_amount: number;
  profit_pct: number;
  caption: string | null;
  nickname: string | null;
  fire_count: number;
  clap_count: number;
  cry_count: number;
  origin: PostOrigin;
};

export type FeedResult = {
  sort: FeedSort;
  ticker: string | null;
  posts: PostCard[];
  next_cursor: string | null;
  disclaimer: string;
};

export type PostCreateResult = {
  id: string;
  created_at: string;
  ticker: string;
  name: string;
  profit_amount: number;
  profit_pct: number;
  caption: string | null;
  nickname: string | null;
  fire_count: number;
  clap_count: number;
  cry_count: number;
  origin: PostOrigin;
  disclaimer: string;
};

export type ReactResult = {
  post_id: string;
  fire_count: number;
  clap_count: number;
  cry_count: number;
  my_reaction: ReactionType;
};

export function createPost(input: {
  ticker: string;
  qty: number;
  buy_date: string;
  caption?: string | null;
  nickname?: string | null;
  origin?: PostOrigin;
}): Promise<PostCreateResult> {
  return jsonFetch<PostCreateResult>("/posts", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchFeed(params: {
  sort?: FeedSort;
  ticker?: string;
  limit?: number;
  cursor?: string;
} = {}): Promise<FeedResult> {
  const qs = new URLSearchParams();
  qs.set("sort", params.sort ?? "latest");
  if (params.ticker) qs.set("ticker", params.ticker);
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.cursor) qs.set("cursor", params.cursor);
  return jsonFetch<FeedResult>(`/feed?${qs.toString()}`);
}

export function react(
  postId: string,
  input: { type: ReactionType; visitor_id: string },
): Promise<ReactResult> {
  return jsonFetch<ReactResult>(
    `/posts/${encodeURIComponent(postId)}/react`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}

export type PostDetailResult = PostCard & {
  my_reaction: ReactionType | null;
  disclaimer: string;
};

export function fetchPost(
  postId: string,
  visitorId?: string,
): Promise<PostDetailResult> {
  const qs = visitorId
    ? `?visitor_id=${encodeURIComponent(visitorId)}`
    : "";
  return jsonFetch<PostDetailResult>(
    `/posts/${encodeURIComponent(postId)}${qs}`,
  );
}
