import type { Metadata } from "next";
import Link from "next/link";

import { Disclaimer } from "@/components/Disclaimer";

export const metadata: Metadata = {
  title: "껄스닥 — 페이지를 찾을 수 없습니다",
  description: "요청하신 페이지를 찾을 수 없거나 주소가 잘못되었습니다.",
  robots: { index: false, follow: false },
};

export default function NotFound() {
  return (
    <main className="slide active not-found">
      <Disclaimer />
      <div className="q">404</div>
      <div
        className="num"
        style={{ fontSize: "clamp(32px, 5vw, 72px)" }}
      >
        이 페이지를 찾을 수 없습니다
      </div>
      <div className="caption">
        주소가 바뀌었거나 등재가 삭제되었을 수 있어요.
      </div>
      {/* 가드 G1: 본 페이지는 투자 권유/예측 표현 0건 */}
      <div className="actions">
        <Link href="/">처음부터</Link>
      </div>
    </main>
  );
}
