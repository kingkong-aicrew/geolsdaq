"""점검 ① — env 누락 시 fail-fast / 503 정규화 / /health degraded 검증.

이 파일은 test_api.py 와 **격리**되어야 한다:
- test_api.py 는 import 시 SUPABASE_* env 를 설정하고 모든 의존성을 mock 한다.
- 여기서는 env 를 비운 채 실제 DI 경로(SupabaseRest)가 ConfigError 를 던지고,
  그게 503(raw 500 아님)으로 정규화되는지 본다.

각 테스트는 monkeypatch 로 env 를 격리하고 reset_settings_for_tests() 로 캐시를
초기화한다. import 순서로 인한 전역 오염을 피하려고 settings 를 매번 리셋한다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ..config import reset_settings_for_tests
from ..repositories.supabase_client import ConfigError, SupabaseRest


@pytest.fixture
def _clear_supabase_env(monkeypatch):
    """SUPABASE_* 환경변수를 모두 제거하고 settings 캐시 리셋."""
    for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY"):
        monkeypatch.delenv(k, raising=False)
    reset_settings_for_tests()
    yield
    # 테스트 종료 후에도 리셋 — 뒤따르는 test_api.py 등이 자기 env 로 다시 읽도록.
    reset_settings_for_tests()


def test_supabase_rest_raises_config_error_when_url_missing(_clear_supabase_env):
    """SUPABASE_URL 누락 → RuntimeError 가 아닌 좁힌 ConfigError."""
    with pytest.raises(ConfigError) as ei:
        SupabaseRest()
    assert "SUPABASE_URL" in str(ei.value)
    # ConfigError 는 RuntimeError 의 서브클래스 (기존 except RuntimeError 호환).
    assert isinstance(ei.value, RuntimeError)


def test_supabase_rest_raises_config_error_when_key_missing(monkeypatch):
    """URL 은 있고 키만 없을 때도 ConfigError(키 종류 명시)."""
    monkeypatch.setenv("SUPABASE_URL", "http://test.local")
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    reset_settings_for_tests()
    try:
        with pytest.raises(ConfigError) as ei:
            SupabaseRest(use_service_role=False)
        assert "SUPABASE_ANON_KEY" in str(ei.value)
    finally:
        reset_settings_for_tests()


def test_calculate_returns_503_not_500_when_env_missing(_clear_supabase_env):
    """필수 시나리오: env 비운 채 /calculate → 503 + 한글 detail (raw 500 ✕).

    의존성 override 없이 실제 DI(get_calculator → PriceRepository → SupabaseRest)
    경로를 타게 해서, DI 단계에서 터지는 ConfigError 가 503 으로 정규화되는지 본다.
    raise_server_exceptions=False 로 둬야 핸들러를 거친 503 응답을 받는다.
    """
    from ..main import app

    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/calculate",
        json={"ticker": "000660", "qty": 10, "buy_date": "2024-01-01"},
    )
    assert r.status_code == 503, r.text
    body = r.json()
    assert "설정" in body["detail"]
    assert "다시 시도" in body["detail"]
    # raw traceback 노출 ✕ — detail 만 존재.
    assert "Traceback" not in r.text
    assert "RuntimeError" not in r.text


def test_health_degraded_when_env_missing(_clear_supabase_env):
    """필수 시나리오: env 누락 → /health 가 200 + degraded + missing 목록."""
    from ..main import app

    # lifespan 미실행 경로 대비 state 초기화 (health 가 즉시 재계산하도록).
    if hasattr(app.state, "degraded"):
        delattr(app.state, "degraded")

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "degraded"
    assert "SUPABASE_URL" in body["missing"]
    assert "SUPABASE_ANON_KEY" in body["missing"]


def test_health_ok_when_env_present(monkeypatch):
    """정상 env → /health status=ok, missing 키 없음 (degraded 회귀 방지)."""
    monkeypatch.setenv("SUPABASE_URL", "http://test.local")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc")
    reset_settings_for_tests()
    try:
        from ..main import app

        if hasattr(app.state, "degraded"):
            delattr(app.state, "degraded")
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/health")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok"
        assert "missing" not in body
    finally:
        reset_settings_for_tests()
