"use client";

import { useState } from "react";

import { react, type PostCard, type ReactionType } from "@/lib/api";
import { getVisitorId } from "@/lib/visitor";

type Props = {
  post: PostCard;
  /** 초기 내 반응(단건 조회 시 전달, 피드에선 보통 null) */
  initialMine?: ReactionType | null;
};

const REACTIONS: { type: ReactionType; emoji: string; label: string }[] = [
  { type: "fire", emoji: "🔥", label: "불타오른다" },
  { type: "clap", emoji: "👏", label: "박수" },
  { type: "cry", emoji: "😭", label: "같이 운다" },
];

/**
 * 반응 바 — 🔥👏😭 3종. 1인 1포스트 1반응(탭하면 변경).
 * 댓글 UI 없음(스펙). 서버 react_to_post 가 단일 진실 → 응답 카운트로 동기화.
 */
export function ReactionBar({ post, initialMine = null }: Props) {
  const [counts, setCounts] = useState({
    fire: post.fire_count,
    clap: post.clap_count,
    cry: post.cry_count,
  });
  const [mine, setMine] = useState<ReactionType | null>(initialMine);
  const [busy, setBusy] = useState(false);

  async function handleReact(type: ReactionType) {
    if (busy) return;
    setBusy(true);

    // 낙관적 업데이트 — 이전 반응 1 감소(있으면) + 새 반응 1 증가.
    // 같은 걸 다시 눌러도 서버는 동일 type 유지(취소 없음 — 스펙상 변경만).
    const prev = { ...counts };
    const prevMine = mine;
    const optimistic = { ...counts };
    if (prevMine && prevMine !== type) {
      optimistic[prevMine] = Math.max(0, optimistic[prevMine] - 1);
    }
    if (prevMine !== type) {
      optimistic[type] = optimistic[type] + 1;
    }
    setCounts(optimistic);
    setMine(type);

    try {
      const res = await react(post.id, {
        type,
        visitor_id: getVisitorId(),
      });
      // 서버 응답으로 확정 동기화(낙관적 추정 보정)
      setCounts({
        fire: res.fire_count,
        clap: res.clap_count,
        cry: res.cry_count,
      });
      setMine(res.my_reaction);
    } catch {
      // 실패 → 롤백
      setCounts(prev);
      setMine(prevMine);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="reaction-bar" role="group" aria-label="반응">
      {REACTIONS.map((r) => (
        <button
          key={r.type}
          type="button"
          className={`reaction ${mine === r.type ? "on" : ""}`}
          onClick={() => handleReact(r.type)}
          disabled={busy}
          aria-pressed={mine === r.type}
          aria-label={`${r.label} ${counts[r.type]}`}
        >
          <span className="emoji" aria-hidden="true">
            {r.emoji}
          </span>
          <span className="cnt">{counts[r.type]}</span>
        </button>
      ))}
    </div>
  );
}
