/**
 * 익명 방문자 ID — localStorage UUID.
 *
 * 쿠키 ✕(CORS credentials=false 유지). 1인 1포스트 1반응 식별용.
 * 위조 가능하나 영향=카운트 인플레만(금전 피해 0) — 허용 리스크(설계 B-4).
 */
const KEY = "ss_visitor_id";

function uuid(): string {
  // 표준 randomUUID 우선, 미지원 환경(구형/비보안 컨텍스트)은 폴백.
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  // RFC4122 v4 유사 폴백 (충돌 가능성 무시 가능 — 익명 식별 용도)
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * 방문자 ID 조회(없으면 생성·저장). SSR 안전(window 가드).
 * localStorage 비활성(시크릿 모드 등) 시 세션 임시 ID 반환.
 */
export function getVisitorId(): string {
  if (typeof window === "undefined") return "";
  try {
    let id = window.localStorage.getItem(KEY);
    if (!id) {
      id = uuid();
      window.localStorage.setItem(KEY, id);
    }
    return id;
  } catch {
    // localStorage 차단 — 메모리 폴백(탭 단위, 8자 min_length 충족)
    return uuid();
  }
}
