# 두 번째 월급 — Backend

FastAPI + Supabase Postgres. 익명·EOD 기준.

---

## 0. 사전 준비 — Supabase 프로젝트

1. https://supabase.com → 새 프로젝트
2. Database > Connection 에서 Project URL 확인
3. Settings > API 에서 두 키 확인:
   - **anon public** — 프론트/일반 API 용
   - **service_role secret** — 배치 cron 전용 (절대 노출 ✕)
4. SQL Editor 열고 `db/schema.sql` 전체 붙여넣고 실행
5. (선택) Settings > Billing 에서 **월 예산 한도** 설정 + 80% 알람

---

## 1. 로컬 실행

```bash
cd geolsdaq
python -m venv .venv && source .venv/Scripts/activate  # Git Bash
pip install -r backend/requirements.txt

# 환경변수 — .env 파일 생성 (최초 1회만)
cp backend/.env.example backend/.env
# 편집: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY 채우기
# → config.py 가 backend/.env 를 자동 로드한다(python-dotenv). 매 실행 set-env 불필요.
# .env 는 .gitignore 됨 → 커밋·노출 안 됨. 한 번 넣으면 끝.

# 서버 실행
uvicorn backend.main:app --reload --port 8000
```

OpenAPI: http://localhost:8000/docs

---

## 2. 배치 (수동 실행)

처음 한 번은 수동으로 데이터를 채워 넣어야 합니다.

```bash
# KR 100종목, 최근 30일
python -m backend.batch.fetch_kr --days 30

# US 50종목, 최근 30일
python -m backend.batch.fetch_us --days 30

# 환율 30일
python -m backend.batch.fetch_fx --days 30
```

이후엔 GitHub Actions cron이 매일 자동 실행.

---

## 3. 테스트

```bash
python -m pytest backend/ -v
```

23 tests. period / schemas / calculator / api 통합 mock 검증.

---

## 4. API

| Method | Path | 설명 |
|--------|------|------|
| GET | `/health` | 상태 |
| POST | `/calculate` | 이번 달 수익 계산 |
| GET | `/leaderboard?sort=amount|pct&period=month&ticker=000660&limit=50` | 랭킹 (종목 필터 가능) |
| POST | `/stash` | 익명 등재 (서버 재계산 + insert) |
| GET | `/share/{id}` | 등재된 결과 + OG 메타 URL |

### 예시

```bash
# 계산
curl -X POST http://localhost:8000/calculate \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"000660","qty":10,"buy_date":"2024-01-01"}'

# 랭킹 — 절대 수익액
curl 'http://localhost:8000/leaderboard?sort=amount&limit=10'

# 랭킹 — 종목 필터
curl 'http://localhost:8000/leaderboard?ticker=000660&sort=pct'

# 등재
curl -X POST http://localhost:8000/stash \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"000660","qty":10,"buy_date":"2024-01-01"}'

# 공유 메타
curl http://localhost:8000/share/{stash_id}
```

---

## 5. 가드 (security-qa public)

| # | 항목 | 상태 |
|---|------|------|
| S1 | API 키 env 만 (코드 ✕) | `config.py` 통과, repo grep 시 sk-/SECRET 없음 |
| S2 | 인증 없는 유료 API 호출 ✕ | 본 백엔드는 외부 유료 API 직호출 ✕ (Supabase 만) |
| S3 | rate limit | calc 30/분, stash 10/분, default 60/분 — slowapi |
| S4 | CORS | env 화이트리스트, credentials=False |
| S5 | RLS | `db/schema.sql` — anon read-only + stash insert only |
| S6 | 비용 한도 | Supabase 무료 티어 한도 + Settings > Billing 예산 알람 |

---

## 6. 폴더

```
backend/
├── main.py              FastAPI 라우팅·미들웨어·DI 조립 (≤200줄)
├── config.py            설정 통합 (env)
├── models/schemas.py    Pydantic 입/출력
├── services/            비즈니스 로직
│   ├── period.py        "이번 달" KST 1일 ~ 어제
│   ├── calculator.py    수익 계산
│   ├── leaderboard.py   랭킹 조회
│   └── stash.py         등재
├── repositories/        Supabase REST
│   ├── supabase_client.py
│   ├── prices.py
│   └── stash.py
├── batch/               EOD 수집 (cron)
│   ├── tickers.py       KR100 + US50 큐레이션
│   ├── fetch_kr.py      pykrx
│   ├── fetch_us.py      yfinance
│   └── fetch_fx.py      USDKRW
├── db/schema.sql        Supabase 테이블 + RLS
├── tests/               pytest
└── requirements.txt
```

---

## 7. 정의

- **"이번 달"** = KST 당월 1일 00:00 ~ 어제 EOD
- **휴장일** 대응 = 요청 날짜 이전 가장 가까운 거래일 종가 (자동)
- **buy_date** 가 당월 1일보다 늦으면 = buy_date 종가가 시작점 (당월 매수자도 포함)
- **수익률** = `((end - start) / start) * 100` — 종목 자체 수익률
- **수익액** = `(end - start) × qty` (KRW 환산 후)
- **USD 종목** = 시작·종료 각 일자 환율로 KRW 환산
- **cron 장애·연휴 후 백필** = GitHub Actions > Actions 탭 > 해당 workflow 선택 > `Run workflow` (workflow_dispatch). cron 기본 `--days 7`로 자동 보강되지만 연휴 7일 초과 누락 시 수동 백필 권장

---

## 8. 운영 주의

- pykrx 는 KRX 트래픽 제한 — 대량 fetch 시 sleep 권장 (현재 일별 1회 cron 으로 충분)
- yfinance 는 무료 제한 있음 — 종목 50개 × 일 1회 정도는 안전
- Vercel/Render 등에 백엔드 배포 시 Supabase 키는 환경변수로만 주입
- `service_key` 노출 시 → 즉시 Supabase 대시보드에서 rotate
