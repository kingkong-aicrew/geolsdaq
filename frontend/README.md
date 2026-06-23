# 두 번째 월급 — Frontend

Next.js 14 App Router + Tailwind + Vercel Edge OG.

---

## 0. 사전 준비

백엔드가 먼저 실행되어 있어야 합니다 (`backend/README.md` 참조).

---

## 1. 로컬 실행

```bash
cd geolsdaq/frontend
npm install

cp .env.example .env.local
# 편집: NEXT_PUBLIC_API_BASE=http://localhost:8000

npm run dev
```

브라우저: http://localhost:3000

---

## 2. 빌드/타입체크

```bash
npm run typecheck   # tsc --noEmit
npm run build       # production build
npm run lint        # eslint
```

---

## 3. 폴더

```
frontend/
├── app/
│   ├── layout.tsx              루트 레이아웃 + 메타
│   ├── page.tsx                슬라이드 5장 메인
│   ├── globals.css             Tailwind + 시안 호환 CSS
│   ├── share/[id]/page.tsx     공유 페이지 (SSR generateMetadata)
│   └── api/og/[id]/route.tsx   Vercel Edge OG 1200×630
├── components/
│   ├── Disclaimer.tsx          면책 푸터
│   ├── SlideSalary.tsx         슬라이드 1
│   ├── SlideStock.tsx          슬라이드 2
│   ├── SlideQty.tsx            슬라이드 3
│   ├── SlideDate.tsx           슬라이드 4
│   └── SlideResult.tsx         슬라이드 5
├── lib/
│   ├── api.ts                  백엔드 API 호출
│   ├── format.ts               숫자 포맷·카운트업
│   └── tickers.ts              종목 메타
├── package.json
├── tailwind.config.ts
├── tsconfig.json
├── next.config.mjs
└── .env.example
```

---

## 4. 시안 대비 변경 사항

| 항목 | 시안 | v2 |
|------|------|-----|
| 가격 | mock 8종목 | `/calculate` 실데이터 |
| 카운트업 | 1800ms ease-out | 동일 유지 |
| 자랑대회 등재 | 토스트만 | `POST /stash` + 토스트 + URL 복사 |
| 평행우주 | 클라이언트 재계산 | 동일 (서버 호출 ✕) |
| 로딩 인디케이터 | 없음 | 추가 |
| 면책 푸터 | 우상단 | 동일 |
| 공유 페이지 | 없음 | `/share/{id}` SSR + OG meta |

---

## 5. OG (Edge)

- 경로: `/api/og/[id]` — Vercel Edge Function
- 사이즈: 1200×630
- 캐시: `s-maxage=3600`
- 내용: 큰 숫자(+/-수익액) + 종목명·수량 + 면책

배포 후 OG 미리보기 도구로 검증:
- https://www.opengraph.xyz/
- https://metatags.io/
- https://cards-dev.twitter.com/validator
- https://developers.facebook.com/tools/debug/

---

## 6. 가드

- 회사 로고/CI ✕ — 텍스트만
- 영문 서브타이틀 ✕ — 한글 only (feedback_no_english_subtext)
- "사라/오를 것/추천" 표현 ✕
- 모든 화면 면책 푸터 (Disclaimer.tsx)
- OG 카드에도 면책

---

## 7. 배포 (Vercel)

```bash
# Vercel CLI
npm i -g vercel
vercel link
vercel env add NEXT_PUBLIC_API_BASE   # 백엔드 URL (prod)
vercel --prod
```

본 사이클은 **로컬 + Vercel preview** 까지. 실제 도메인은 사용자 결정 후.
