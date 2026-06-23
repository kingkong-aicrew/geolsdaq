"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Disclaimer } from "@/components/Disclaimer";
import { PostCard } from "@/components/PostCard";
import {
  createPost,
  fetchFeed,
  type FeedSort,
  type PostCard as PostCardData,
} from "@/lib/api";
import { FEATURED_TICKERS, type TickerItem } from "@/lib/tickers";

const PAGE_SIZE = 20;

// 매수 시점 옵션 (SlideDate 와 동일 의미)
const YEAR_OPTIONS: Array<{ years: number; label: string }> = [
  { years: 0.5, label: "반 년 전" },
  { years: 1, label: "1년 전" },
  { years: 2, label: "2년 전" },
  { years: 3, label: "3년 전" },
  { years: 5, label: "5년 전" },
  { years: 10, label: "10년 전" },
];

function buyDateFromYears(yearsAgo: number): string {
  const ms = yearsAgo * 365.25 * 24 * 60 * 60 * 1000;
  return new Date(Date.now() - ms).toISOString().slice(0, 10);
}

export default function FeedPage() {
  const [sort, setSort] = useState<FeedSort>("latest");
  const [posts, setPosts] = useState<PostCardData[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reachedEnd, setReachedEnd] = useState(false);

  // 등재 폼
  const [composeOpen, setComposeOpen] = useState(false);
  const [stock, setStock] = useState<TickerItem | null>(null);
  const [qty, setQty] = useState("");
  const [years, setYears] = useState<number | null>(null);
  const [caption, setCaption] = useState("");
  const [posting, setPosting] = useState(false);
  const [postError, setPostError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // 피드 페이지는 스크롤 필요 — body overflow 해제(전역 hidden 무력화)
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "auto";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  const loadFirst = useCallback(async (nextSort: FeedSort) => {
    setLoading(true);
    setError(null);
    setReachedEnd(false);
    try {
      const res = await fetchFeed({ sort: nextSort, limit: PAGE_SIZE });
      setPosts(res.posts);
      setCursor(res.next_cursor);
      if (!res.next_cursor) setReachedEnd(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "불러오지 못했어요");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMore = useCallback(async () => {
    if (loading || reachedEnd || !cursor) return;
    setLoading(true);
    try {
      const res = await fetchFeed({ sort, limit: PAGE_SIZE, cursor });
      setPosts((prev) => [...prev, ...res.posts]);
      setCursor(res.next_cursor);
      if (!res.next_cursor) setReachedEnd(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "더 불러오지 못했어요");
    } finally {
      setLoading(false);
    }
  }, [loading, reachedEnd, cursor, sort]);

  // 정렬 변경 시 첫 페이지 재로드
  useEffect(() => {
    void loadFirst(sort);
  }, [sort, loadFirst]);

  // 무한 스크롤 — 센티넬 관찰
  const sentinelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) void loadMore();
      },
      { rootMargin: "200px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [loadMore]);

  function handleSort(next: FeedSort) {
    if (next === sort) return;
    setSort(next);
  }

  async function handlePost(e: React.FormEvent) {
    e.preventDefault();
    if (posting) return;
    setPostError(null);

    const qtyNum = parseInt(qty, 10);
    if (!stock) {
      setPostError("종목을 골라 주세요");
      return;
    }
    if (!Number.isFinite(qtyNum) || qtyNum < 1) {
      setPostError("수량을 입력해 주세요");
      return;
    }
    if (years == null) {
      setPostError("언제 샀는지 골라 주세요");
      return;
    }

    setPosting(true);
    try {
      const res = await createPost({
        ticker: stock.code,
        qty: qtyNum,
        buy_date: buyDateFromYears(years),
        caption: caption.trim() || null,
      });
      // 새 카드를 피드 맨 앞에 낙관적 추가(latest 기준 자연스러움)
      const newCard: PostCardData = {
        id: res.id,
        created_at: res.created_at,
        ticker: res.ticker,
        name: res.name,
        qty: qtyNum,
        buy_date: buyDateFromYears(years),
        profit_amount: res.profit_amount,
        profit_pct: res.profit_pct,
        caption: res.caption,
        nickname: res.nickname,
        fire_count: res.fire_count,
        clap_count: res.clap_count,
        cry_count: res.cry_count,
        origin: res.origin,
      };
      setPosts((prev) => [newCard, ...prev]);
      setComposeOpen(false);
      setStock(null);
      setQty("");
      setYears(null);
      setCaption("");
      setToast("피드에 올렸어요");
      setTimeout(() => setToast(null), 2500);
    } catch (e) {
      setPostError(e instanceof Error ? e.message : "올리지 못했어요");
    } finally {
      setPosting(false);
    }
  }

  return (
    <main className="feed-page">
      <Disclaimer />

      <header className="feed-header">
        <a href="/" className="feed-home" aria-label="처음으로">
          ← 두 번째 월급
        </a>
        <h1 className="feed-title">천하제일 주식자랑</h1>
        <div className="feed-tabs" role="tablist" aria-label="정렬">
          <button
            role="tab"
            aria-selected={sort === "latest"}
            className={`feed-tab ${sort === "latest" ? "on" : ""}`}
            onClick={() => handleSort("latest")}
          >
            최신
          </button>
          <button
            role="tab"
            aria-selected={sort === "hot"}
            className={`feed-tab ${sort === "hot" ? "on" : ""}`}
            onClick={() => handleSort("hot")}
          >
            🔥 인기
          </button>
        </div>
      </header>

      {/* 등재 폼 */}
      <section className="compose">
        {!composeOpen ? (
          <button
            type="button"
            className="compose-toggle"
            onClick={() => setComposeOpen(true)}
          >
            내 자랑 올리기 +
          </button>
        ) : (
          <form className="compose-form" onSubmit={handlePost}>
            <div className="compose-row">
              <span className="compose-lbl">종목</span>
              <div className="compose-picks">
                {FEATURED_TICKERS.map((t) => (
                  <button
                    type="button"
                    key={t.code}
                    className={`pick sm ${stock?.code === t.code ? "on" : ""}`}
                    onClick={() => setStock(t)}
                  >
                    {t.name}
                  </button>
                ))}
              </div>
            </div>
            <div className="compose-row">
              <span className="compose-lbl">수량</span>
              <input
                className="compose-input"
                type="number"
                inputMode="numeric"
                min={1}
                placeholder="주식 수"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
                aria-label="주식 수량"
              />
            </div>
            <div className="compose-row">
              <span className="compose-lbl">매수</span>
              <div className="compose-picks">
                {YEAR_OPTIONS.map((o) => (
                  <button
                    type="button"
                    key={o.years}
                    className={`pick sm ${years === o.years ? "on" : ""}`}
                    onClick={() => setYears(o.years)}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="compose-row">
              <span className="compose-lbl">한 줄</span>
              <input
                className="compose-input"
                type="text"
                maxLength={60}
                placeholder="한 줄 자랑 (선택, 60자 · 링크/@ 금지)"
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
                aria-label="한 줄 자랑"
              />
            </div>
            {postError && <div className="compose-error">{postError}</div>}
            <div className="compose-actions">
              <button
                type="button"
                className="compose-cancel"
                onClick={() => {
                  setComposeOpen(false);
                  setPostError(null);
                }}
              >
                취소
              </button>
              <button type="submit" className="compose-submit" disabled={posting}>
                {posting ? "올리는 중…" : "익명으로 올리기"}
              </button>
            </div>
          </form>
        )}
      </section>

      {/* 피드 */}
      <section className="feed-list">
        {posts.map((p) => (
          <PostCard key={p.id} post={p} />
        ))}

        {!loading && posts.length === 0 && !error && (
          <div className="feed-empty">
            아직 자랑이 없어요. 첫 번째 주인공이 되어보세요.
          </div>
        )}
        {error && <div className="feed-empty">{error}</div>}
        {loading && <div className="feed-loading">불러오는 중…</div>}
        {reachedEnd && posts.length > 0 && (
          <div className="feed-end">— 여기까지예요 —</div>
        )}
        <div ref={sentinelRef} aria-hidden="true" />
      </section>

      {toast && <div className="toast">{toast}</div>}
    </main>
  );
}
