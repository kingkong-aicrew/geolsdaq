"use client";

type Props = {
  active: boolean;
  onStart: () => void;
};

/**
 * 진입 후크 슬라이드 (s1).
 * "월급 얼마?"(민감정보 진입) 폐기 → 획득 후회("살걸")와 처분 후회("팔걸")를
 * 동급으로 던지는 자조 후크. 보조 후크는 '이겨도 불안'(수익자도 박탈감) 직격.
 * 톤: 매트릭스 블랙홀 유지, 피식→쓴웃음(드립 절제).
 */
export function SlideIntro({ active, onStart }: Props) {
  return (
    <section className={`slide ${active ? "active" : ""}`} id="s1">
      <div className="intro-hook">
        그때,
        <br />
        <span className="intro-hook-em">살걸</span>{" "}
        <span className="intro-hook-em">팔걸</span>
      </div>
      <div className="intro-sub">수익 났는데, 왜 안 놓이지?</div>
      <button className="intro-cta" onClick={onStart} aria-label="시작하기">
        그 종목, 지금 얼마였나
      </button>
    </section>
  );
}
