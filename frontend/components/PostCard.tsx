"use client";

import { ReactionBar } from "@/components/ReactionBar";
import type { PostCard as PostCardData } from "@/lib/api";
import { formatKRW, formatPct } from "@/lib/format";

type Props = {
  post: PostCardData;
  highlight?: boolean;
};

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffSec = Math.max(0, (Date.now() - then) / 1000);
  if (diffSec < 60) return "방금 전";
  const min = Math.floor(diffSec / 60);
  if (min < 60) return `${min}분 전`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}시간 전`;
  const day = Math.floor(hr / 24);
  return `${day}일 전`;
}

/**
 * 피드 카드 1장 — 익명 자랑.
 * 종목 · 이번 달 수익(액/율) · (옵션)캡션 · (옵션)닉네임 · 반응바.
 * 댓글 UI 없음(스펙). 평행우주 출처면 작은 배지.
 */
export function PostCard({ post, highlight = false }: Props) {
  const positive = post.profit_amount >= 0;
  return (
    <article
      id={`post-${post.id}`}
      className={`post-card${highlight ? " highlight" : ""}`}
    >
      <div className="post-head">
        <span className="post-name">{post.name}</span>
        {post.origin === "parallel" && (
          <span className="post-badge">평행우주</span>
        )}
        <span className="post-time">{relativeTime(post.created_at)}</span>
      </div>

      <div className={`post-amount ${positive ? "positive" : "negative"}`}>
        {(positive ? "+" : "") + formatKRW(post.profit_amount)}
        <span className="won">원</span>
      </div>
      <div className={`post-pct ${positive ? "positive" : "negative"}`}>
        {formatPct(post.profit_pct)}
      </div>

      {post.caption && <p className="post-caption">{post.caption}</p>}

      <div className="post-foot">
        <span className="post-nick">{post.nickname || "익명의 개미"}</span>
        <ReactionBar post={post} />
      </div>
    </article>
  );
}
