-- 두 번째 월급 v2 — Supabase Postgres 스키마 + RLS
-- 적용: Supabase Dashboard > SQL Editor 에서 실행
-- Exposure: public (security-qa.md #5)
--
-- 원칙:
--   anon = 익명 방문자 (브라우저 fetch)
--     SELECT: prices, fx, stash  (공개 시세 + 자랑 등재 결과)
--     INSERT: stash 만 허용 (캡션·닉네임 X — 가드레일)
--     UPDATE/DELETE: 차단
--   service_role = cron / 백엔드 어드민
--     모든 권한
-- ---------------------------------------------------------------

-- 1. prices: 일봉 종가 (KR + US 단일 테이블)
CREATE TABLE IF NOT EXISTS prices (
    ticker     text        NOT NULL,
    date       date        NOT NULL,
    close      numeric(18, 4) NOT NULL CHECK (close > 0),
    market     text        NOT NULL CHECK (market IN ('KR', 'US')),
    name       text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS prices_market_date_idx
    ON prices (market, date DESC);

CREATE INDEX IF NOT EXISTS prices_ticker_date_idx
    ON prices (ticker, date DESC);

-- 2. fx: USD-KRW 일봉
CREATE TABLE IF NOT EXISTS fx (
    date        date        NOT NULL PRIMARY KEY,
    usd_krw     numeric(10, 4) NOT NULL CHECK (usd_krw > 0),
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- 3. stash: 익명 자랑대회 등재 (캡션·닉네임 X — Phase A)
--    Phase B에서 caption/nickname/reactions 추가 예정
CREATE TABLE IF NOT EXISTS stash (
    id              uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),
    ticker          text        NOT NULL,
    name            text        NOT NULL,            -- 표시용 (회사명)
    qty             integer     NOT NULL CHECK (qty > 0 AND qty < 1000000),
    buy_date        date        NOT NULL CHECK (buy_date >= '2000-01-01' AND buy_date <= CURRENT_DATE),
    profit_amount   numeric(18, 2) NOT NULL,         -- 이번 달 KRW 수익액
    profit_pct      numeric(8, 2)  NOT NULL,         -- 이번 달 수익률 (%)
    period_start    date        NOT NULL,
    period_end      date        NOT NULL,
    calc_snapshot   jsonb       NOT NULL,            -- 계산 근거 (재현용)
    ip_hash         text        -- rate-limit/유사 도용 차단용 (해시만)
);

CREATE INDEX IF NOT EXISTS stash_created_at_idx ON stash (created_at DESC);
CREATE INDEX IF NOT EXISTS stash_profit_amount_idx ON stash (profit_amount DESC);
CREATE INDEX IF NOT EXISTS stash_profit_pct_idx ON stash (profit_pct DESC);
CREATE INDEX IF NOT EXISTS stash_ticker_idx ON stash (ticker);

-- ---------------------------------------------------------------
-- RLS (Row Level Security)
-- ---------------------------------------------------------------

ALTER TABLE prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE fx     ENABLE ROW LEVEL SECURITY;
ALTER TABLE stash  ENABLE ROW LEVEL SECURITY;

-- prices: anon SELECT 만, 쓰기 차단
DROP POLICY IF EXISTS "prices_read_anon" ON prices;
CREATE POLICY "prices_read_anon"
    ON prices FOR SELECT
    TO anon, authenticated
    USING (true);

-- fx: anon SELECT 만, 쓰기 차단
DROP POLICY IF EXISTS "fx_read_anon" ON fx;
CREATE POLICY "fx_read_anon"
    ON fx FOR SELECT
    TO anon, authenticated
    USING (true);

-- stash: anon SELECT (랭킹 조회)
DROP POLICY IF EXISTS "stash_read_anon" ON stash;
CREATE POLICY "stash_read_anon"
    ON stash FOR SELECT
    TO anon, authenticated
    USING (true);

-- stash: anon INSERT (자랑 등재)
--   ⚠️ security-qa #5 — WITH CHECK (true) 단독 금지.
--   여기선 ip_hash NOT NULL 강제 + 백엔드에서 서버측 계산 후 insert 만 허용.
--   anon 직접 insert 도 가능하나 백엔드 경유 권장 (rate-limit 적용 위해).
DROP POLICY IF EXISTS "stash_insert_anon" ON stash;
CREATE POLICY "stash_insert_anon"
    ON stash FOR INSERT
    TO anon, authenticated
    WITH CHECK (
        qty > 0
        AND qty < 1000000
        AND buy_date >= '2000-01-01'
        AND buy_date <= CURRENT_DATE
        AND ticker IS NOT NULL
        AND ip_hash IS NOT NULL
    );

-- stash: 수정/삭제는 차단 (스펙: 캡션 수정 불가)
DROP POLICY IF EXISTS "stash_update_block" ON stash;
DROP POLICY IF EXISTS "stash_delete_block" ON stash;
-- (정책을 만들지 않으면 자동 차단 — RLS 기본)

-- ===============================================================
-- Phase B — 커뮤니티 (posts / reactions / react_to_post RPC)
-- ===============================================================
--   posts: 익명 자랑 피드 카드. 반응 카운트를 denormalize 하여 보관
--          (hot 정렬·카드 표시가 가장 빈번한 읽기 — 매번 GROUP BY 회피).
--   reactions: 방문자별 1행(1인 1포스트 1반응). UPSERT 로 type 변경.
--   react_to_post: reactions upsert + posts 카운트 재집계를 한 트랜잭션으로
--                  (denormalize 동기화 = reactions 가 단일 진실, race 방어).
--   ⚠️ 댓글(comments) 테이블·엔드포인트 없음 (스펙 금지) — 반응만.

-- 4. posts: 피드 카드 (caption≤60, nickname≤12, 반응 카운트 denormalize)
CREATE TABLE IF NOT EXISTS posts (
    id              uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),
    -- 계산 스냅샷 (stash 와 동일 골격 — 위·변조 차단 위해 서버 재계산값 저장)
    ticker          text        NOT NULL,
    name            text        NOT NULL,
    qty             integer     NOT NULL CHECK (qty > 0 AND qty < 1000000),
    buy_date        date        NOT NULL CHECK (buy_date >= '2000-01-01' AND buy_date <= CURRENT_DATE),
    profit_amount   numeric(18, 2) NOT NULL,
    profit_pct      numeric(8, 2)  NOT NULL,
    period_start    date        NOT NULL,
    period_end      date        NOT NULL,
    calc_snapshot   jsonb       NOT NULL,
    -- 커뮤니티 필드
    caption         text        CHECK (caption IS NULL OR char_length(caption) <= 60),
    nickname        text        CHECK (nickname IS NULL OR char_length(nickname) <= 12),
    -- 반응 집계 (denormalized — /feed hot 정렬·표시 시 join 회피)
    fire_count      integer     NOT NULL DEFAULT 0 CHECK (fire_count >= 0),
    clap_count      integer     NOT NULL DEFAULT 0 CHECK (clap_count >= 0),
    cry_count       integer     NOT NULL DEFAULT 0 CHECK (cry_count >= 0),
    ip_hash         text,
    -- 평행우주 출처 표식 (평행우주 결과를 피드에 올린 경우)
    origin          text        NOT NULL DEFAULT 'direct' CHECK (origin IN ('direct', 'parallel'))
);

CREATE INDEX IF NOT EXISTS posts_created_at_idx ON posts (created_at DESC);
-- hot 정렬: fire_count desc, 동률은 created_at desc (커서 안정성)
CREATE INDEX IF NOT EXISTS posts_fire_count_idx ON posts (fire_count DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS posts_ticker_idx ON posts (ticker);

-- 5. reactions: 방문자별 1행 (1인 1포스트 1반응)
CREATE TABLE IF NOT EXISTS reactions (
    post_id     uuid        NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    visitor_id  text        NOT NULL,            -- 익명 localStorage UUID
    type        text        NOT NULL CHECK (type IN ('fire', 'clap', 'cry')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (post_id, visitor_id)            -- 탭하면 type UPDATE, 중복 INSERT 불가
);

CREATE INDEX IF NOT EXISTS reactions_post_idx ON reactions (post_id);

-- react_to_post: reactions upsert + posts 카운트 재집계 (1 트랜잭션, race 방어)
--   SECURITY DEFINER + 백엔드 service_role 호출 → anon 의 카운트 직접 조작 차단
--   (security-qa #5). 반환값은 갱신된 3종 카운트.
CREATE OR REPLACE FUNCTION react_to_post(
    p_post_id uuid, p_visitor text, p_type text
) RETURNS TABLE(fire int, clap int, cry int)
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    IF p_type NOT IN ('fire', 'clap', 'cry') THEN
        RAISE EXCEPTION 'invalid reaction type: %', p_type;
    END IF;
    IF p_visitor IS NULL OR length(p_visitor) = 0 THEN
        RAISE EXCEPTION 'visitor_id required';
    END IF;
    -- 대상 포스트가 없으면 에러 (백엔드가 404 로 정규화)
    IF NOT EXISTS (SELECT 1 FROM posts WHERE id = p_post_id) THEN
        RAISE EXCEPTION 'post not found: %', p_post_id;
    END IF;

    INSERT INTO reactions(post_id, visitor_id, type)
        VALUES (p_post_id, p_visitor, p_type)
        ON CONFLICT (post_id, visitor_id)
        DO UPDATE SET type = EXCLUDED.type, updated_at = now();

    -- 카운트를 reactions 에서 재집계 (denormalize 동기화 — 단일 진실)
    UPDATE posts p SET
        fire_count = (SELECT count(*) FROM reactions WHERE post_id = p_post_id AND type = 'fire'),
        clap_count = (SELECT count(*) FROM reactions WHERE post_id = p_post_id AND type = 'clap'),
        cry_count  = (SELECT count(*) FROM reactions WHERE post_id = p_post_id AND type = 'cry')
        WHERE p.id = p_post_id;

    RETURN QUERY SELECT p.fire_count, p.clap_count, p.cry_count FROM posts p WHERE p.id = p_post_id;
END $$;

-- 함수 실행권한: anon 직접 RPC 차단, service_role(백엔드) 전용 (P2-1 fix · security-qa #5 집행)
REVOKE EXECUTE ON FUNCTION react_to_post(uuid, text, text) FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION react_to_post(uuid, text, text) TO service_role;

-- RLS — posts / reactions
ALTER TABLE posts     ENABLE ROW LEVEL SECURITY;
ALTER TABLE reactions ENABLE ROW LEVEL SECURITY;

-- posts: anon SELECT (피드 조회)
DROP POLICY IF EXISTS "posts_read_anon" ON posts;
CREATE POLICY "posts_read_anon"
    ON posts FOR SELECT
    TO anon, authenticated
    USING (true);

-- posts: anon INSERT — WITH CHECK (true) 단독 금지 (security-qa #5).
--   백엔드 service_role 경유가 1차 게이트(재계산·필터·rate limit). 이 정책은 2차 방어선:
--   필드 제약 + 카운트 0 강제(생성 시 조작 차단) + ip_hash NOT NULL.
DROP POLICY IF EXISTS "posts_insert_anon" ON posts;
CREATE POLICY "posts_insert_anon"
    ON posts FOR INSERT
    TO anon, authenticated
    WITH CHECK (
        qty > 0
        AND qty < 1000000
        AND buy_date >= '2000-01-01'
        AND buy_date <= CURRENT_DATE
        AND ticker IS NOT NULL
        AND ip_hash IS NOT NULL
        AND (caption IS NULL OR char_length(caption) <= 60)
        AND (nickname IS NULL OR char_length(nickname) <= 12)
        AND fire_count = 0 AND clap_count = 0 AND cry_count = 0   -- 카운트 조작 차단
        AND origin IN ('direct', 'parallel')
    );

-- posts: UPDATE/DELETE 정책 없음 → 자동 차단 (캡션 수정 ✕ 스펙).
--   카운트 변경은 react_to_post(SECURITY DEFINER) 함수로만.

-- reactions: anon 직접 접근 정책 없음 → react_to_post 함수로만 변경.
--   집계는 posts 의 denormalize 카운트로 노출 (reactions 행 자체는 비공개).

-- ===============================================================
-- Phase 4 — 지수착시 (index_prices / index_breadth)
-- ===============================================================
--   "오늘 코스피는 +X% 라는데 내 종목만 녹았다" — 지수 등락 vs 개별종목
--   등락 분포의 괴리(착시)를 매일 1회 배치로 미리 계산해 저장.
--   index_prices:  지수 시계열(코스피/코스닥) — 지수 등락률 축(a).
--   index_breadth: 일자별 전종목 등락 집계(상승/하락/중앙값) — 분포 축(b).
--                  무거운 GROUP BY 를 조회 시점에 돌리지 않도록 배치가 사전 계산.
--   ⚠️ 둘 다 공개 시세/집계 → anon SELECT 만, 쓰기는 service_role(배치)로만.

-- 6. index_prices: 지수 일봉 (KOSPI / KOSDAQ)
CREATE TABLE IF NOT EXISTS index_prices (
    index_code  text        NOT NULL CHECK (index_code IN ('KOSPI', 'KOSDAQ')),
    date        date        NOT NULL,
    close       numeric(12, 2) NOT NULL CHECK (close > 0),
    change_pct  numeric(8, 4),                  -- 전 거래일 대비 등락률(%) (배치 계산·저장)
    name        text        NOT NULL,           -- '코스피' | '코스닥'
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (index_code, date)
);

CREATE INDEX IF NOT EXISTS index_prices_code_date_idx
    ON index_prices (index_code, date DESC);

-- 7. index_breadth: 일자별 전종목 등락 집계 (착시 핵심 — 사전 계산)
--    illusion_gap = index_change_pct - median_change_pct.
--    클수록(지수↑ 중앙값↓) "착시 강도" 큼 → 화면 카피 톤을 데이터로 결정.
--    total_count 를 항상 같이 저장해 "모수 N개 중" 으로 정직하게 노출
--    (공공 API 샘플링 외삽 금지 정신 — fact_api_sort_order_extrapolation).
CREATE TABLE IF NOT EXISTS index_breadth (
    market            text        NOT NULL CHECK (market IN ('KR_KOSPI', 'KR_KOSDAQ')),
    date              date        NOT NULL,
    index_change_pct  numeric(8, 4) NOT NULL,   -- 그날 지수 등락률
    total_count       integer     NOT NULL CHECK (total_count >= 0),  -- 집계 대상 종목 수
    up_count          integer     NOT NULL CHECK (up_count >= 0),     -- 상승 종목 수
    down_count        integer     NOT NULL CHECK (down_count >= 0),   -- 하락 종목 수
    flat_count        integer     NOT NULL CHECK (flat_count >= 0),   -- 보합
    up_ratio          numeric(6, 4) NOT NULL,   -- up/total (0~1)
    median_change_pct numeric(8, 4) NOT NULL,   -- 개별종목 등락률 중앙값
    illusion_gap      numeric(8, 4) NOT NULL,   -- index_change_pct - median_change_pct
    created_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (market, date)
);

CREATE INDEX IF NOT EXISTS index_breadth_market_date_idx
    ON index_breadth (market, date DESC);

-- RLS — index_prices / index_breadth (읽기 전용)
ALTER TABLE index_prices  ENABLE ROW LEVEL SECURITY;
ALTER TABLE index_breadth ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "index_prices_read_anon" ON index_prices;
CREATE POLICY "index_prices_read_anon"
    ON index_prices FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS "index_breadth_read_anon" ON index_breadth;
CREATE POLICY "index_breadth_read_anon"
    ON index_breadth FOR SELECT
    TO anon, authenticated
    USING (true);

-- index_prices / index_breadth: INSERT/UPDATE/DELETE 정책 없음 → 자동 차단.
--   적재는 배치(service_role)만. anon 은 SELECT 만.

-- ---------------------------------------------------------------
-- 검증 쿼리 (수동 실행)
-- ---------------------------------------------------------------
-- anon 으로 다음을 시도하면 결과:
--   SELECT * FROM prices LIMIT 5;      -- OK
--   INSERT INTO prices VALUES (...);   -- ERROR (정책 없음)
--   SELECT * FROM stash;               -- OK
--   INSERT INTO stash (...);           -- OK (CHECK 통과 시)
--   UPDATE stash SET ...;              -- ERROR
--   SELECT * FROM posts;               -- OK
--   INSERT INTO posts (... fire_count=1 ...);  -- ERROR (카운트 0 강제)
--   SELECT * FROM reactions;           -- (정책 없음 → 빈 결과/차단)
--   SELECT react_to_post('<uuid>','v1','fire'); -- 백엔드 service_role 로만
--   SELECT * FROM index_prices LIMIT 5;   -- OK
--   SELECT * FROM index_breadth LIMIT 5;  -- OK
--   INSERT INTO index_breadth (...);      -- ERROR (정책 없음 — 배치 service_role 만)
