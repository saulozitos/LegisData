import importlib
import logging
from unittest.mock import MagicMock, patch

import pytest
from app import main as main_module
from app.core.config import settings
from fastapi.testclient import TestClient


@pytest.fixture()
def plain_client():
    """Cliente sem banco: usado nas rotas utilitárias e nos middlewares."""
    return TestClient(main_module.app)


def test_root_and_health(plain_client):
    root = plain_client.get("/")
    assert root.status_code == 200
    data = root.json()
    assert data["status"] == "online"
    assert data["service"] == settings.PROJECT_NAME
    assert data["docs_url"] == "/docs"

    health = plain_client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}


def test_security_headers_on_every_response(plain_client):
    response = plain_client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "geolocation=()" in response.headers["permissions-policy"]
    # HSTS só em produção (evita fixar HTTPS em ambientes locais)
    assert "strict-transport-security" not in response.headers


def test_security_headers_also_on_error_responses(plain_client):
    response = plain_client.get("/rota-que-nao-existe")
    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"


def test_hsts_enabled_in_production(plain_client, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    response = plain_client.get("/health")
    assert "max-age=31536000" in response.headers["strict-transport-security"]


def test_interactive_docs_are_not_blocked_by_strict_csp(plain_client):
    docs = plain_client.get("/docs")
    assert docs.status_code == 200
    assert "content-security-policy" not in docs.headers
    assert docs.headers["x-frame-options"] == "DENY"


def test_docs_and_openapi_disabled_in_production(monkeypatch):
    original = settings.ENVIRONMENT
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    reloaded = importlib.reload(main_module)
    try:
        prod_client = TestClient(reloaded.app)
        assert prod_client.get("/docs").status_code == 404
        assert prod_client.get("/redoc").status_code == 404
        assert prod_client.get(f"{settings.API_V1_STR}/openapi.json").status_code == 404
        assert prod_client.get("/").json()["docs_url"] is None
    finally:
        monkeypatch.setattr(settings, "ENVIRONMENT", original)
        importlib.reload(main_module)


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:3000", "https://legisdata.vercel.app", "https://legisdata-git-feat-x-team.vercel.app"],
)
def test_cors_allows_project_origins(plain_client, origin):
    response = plain_client.get("/health", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize(
    "origin", ["https://evil.vercel.app", "https://legisdata.vercel.app.evil.com", "http://evil.example"]
)
def test_cors_rejects_foreign_origins(plain_client, origin):
    response = plain_client.get("/health", headers={"Origin": origin})
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_only_allows_read_methods(plain_client):
    headers = {"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"}
    assert plain_client.options("/api/v1/politicians", headers=headers).status_code == 400
    headers["Access-Control-Request-Method"] = "GET"
    ok = plain_client.options("/api/v1/politicians", headers=headers)
    assert ok.status_code == 200
    assert "POST" not in ok.headers["access-control-allow-methods"]


def test_api_exposes_no_write_routes(plain_client):
    schema = plain_client.get(f"{settings.API_V1_STR}/openapi.json").json()
    methods = {method for path in schema["paths"].values() for method in path}
    assert methods <= {"get"}


def test_rate_limit_returns_429_with_retry_after(plain_client, data_dir, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 2)
    url = f"{settings.API_V1_STR}/politicians/presidents"
    assert plain_client.get(url).status_code == 404  # sem dados: 404 legítimo, não 500
    assert plain_client.get(url).status_code == 404
    blocked = plain_client.get(url)
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"
    # Health checks não sofrem limite
    assert plain_client.get("/health").status_code == 200
    assert plain_client.get("/").status_code == 200


def test_rate_limit_ignores_forwarded_header_unless_trusted(plain_client, data_dir, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)
    url = f"{settings.API_V1_STR}/politicians/presidents"
    assert plain_client.get(url, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 404
    # Sem proxy confiável, trocar o cabeçalho não burla o limite
    assert plain_client.get(url, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429

    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    assert plain_client.get(url, headers={"X-Forwarded-For": "3.3.3.3, 10.0.0.1"}).status_code == 404
    assert plain_client.get(url, headers={"X-Forwarded-For": "3.3.3.3"}).status_code == 429


def test_rate_limiter_sliding_window_expires(monkeypatch):
    limiter = main_module._RateLimiter()
    clock = {"now": 1000.0}
    monkeypatch.setattr(main_module.time, "monotonic", lambda: clock["now"])
    assert limiter.allow("ip", 2) and limiter.allow("ip", 2)
    assert not limiter.allow("ip", 2)
    clock["now"] += 61
    assert limiter.allow("ip", 2)


def _postgres_session_mock():
    session = MagicMock()
    session.bind.dialect.name = "postgresql"
    factory = MagicMock()
    factory.return_value.__enter__.return_value = session
    return factory, session


def test_migrations_take_advisory_lock_before_any_ddl():
    factory, session = _postgres_session_mock()
    with patch("app.core.database.SessionLocal", factory):
        main_module.run_db_migrations()

    statements = [str(call.args[0]) for call in session.execute.call_args_list]
    assert "pg_advisory_xact_lock" in statements[0]
    assert session.execute.call_args_list[0].args[1] == {"lock_id": main_module.MIGRATION_ADVISORY_LOCK_ID}
    ddl = " ".join(statements[1:])
    assert "ALTER TABLE certidoes_judiciais" in ddl
    assert "CREATE TABLE IF NOT EXISTS processos_judiciais" in ddl
    session.commit.assert_called_once()


def test_migrations_skip_non_postgres_dialects():
    factory, session = _postgres_session_mock()
    session.bind.dialect.name = "sqlite"
    with patch("app.core.database.SessionLocal", factory):
        main_module.run_db_migrations()
    session.execute.assert_not_called()
    session.commit.assert_not_called()


def test_startup_logs_error_but_does_not_crash_when_db_is_down(caplog):
    factory = MagicMock()
    factory.return_value.__enter__.side_effect = RuntimeError("db down")
    with patch("app.core.database.SessionLocal", factory), caplog.at_level(logging.ERROR, logger="uvicorn"):
        main_module.startup_db_migrations()  # não pode levantar
    assert any(r.levelno == logging.ERROR and "auto-migration failed" in r.getMessage() for r in caplog.records)


def test_openapi_documents_the_public_contract(plain_client):
    paths = plain_client.get(f"{settings.API_V1_STR}/openapi.json").json()["paths"]
    for expected in (
        "/politicians/presidents",
        "/politicians/{politician_id}",
        "/analytics/mandates-performance",
        "/economic/annual-summary",
        "/legislative/propositions",
        "/executivo/mandates",
    ):
        assert f"{settings.API_V1_STR}{expected}" in paths
