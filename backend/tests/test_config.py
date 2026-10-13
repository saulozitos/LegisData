import re

import pytest
from app.core.config import CLOUD_DB_HOST_SUFFIXES, Settings
from sqlalchemy.engine import make_url


def make_settings(**kwargs):
    kwargs.setdefault("DB_SSLMODE", "")
    return Settings(_env_file=None, **kwargs)


def test_missing_database_credentials_abort_startup(monkeypatch):
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD"):
        Settings(_env_file=None, POSTGRES_PASSWORD="", DATABASE_URL="")


def test_password_is_url_encoded_when_building_the_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = make_settings(POSTGRES_PASSWORD="p@ss:w/rd#1", POSTGRES_SERVER="db", DATABASE_URL="")
    url = make_url(s.sync_database_url)
    assert url.password == "p@ss:w/rd#1"
    assert url.host == "db"
    assert url.drivername == "postgresql+psycopg2"


@pytest.mark.parametrize(
    "raw,expected_driver",
    [
        ("postgres://u:p@localhost/db", "postgresql+psycopg2"),
        ("postgresql://u:p@localhost/db", "postgresql+psycopg2"),
        ("postgresql+psycopg2://u:p@localhost/db", "postgresql+psycopg2"),
    ],
)
def test_driver_is_normalized(raw, expected_driver):
    assert make_url(make_settings(DATABASE_URL=raw).sync_database_url).drivername == expected_driver


@pytest.mark.parametrize("host", ["db.abc.supabase.co", "ep-x.neon.tech", "mydb.rds.amazonaws.com", "x.render.com"])
def test_managed_cloud_hosts_require_tls_automatically(host):
    url = make_settings(DATABASE_URL=f"postgresql://u:p@{host}:5432/db").sync_database_url
    assert url.endswith("sslmode=require")


@pytest.mark.parametrize(
    "raw",
    [
        # "aws"/"rds" no usuário ou na senha NÃO podem ser tratados como banco em nuvem
        "postgresql://rds:aws@localhost:5432/db",
        "postgresql://words:neon.tech@postgres:5432/db",
        # sufixo parecido, mas outro domínio
        "postgresql://u:p@evil-supabase.co.example.com/db",
        "postgresql://u:p@notsupabase.co/db",
    ],
)
def test_local_hosts_are_not_misdetected_as_cloud(raw):
    assert "sslmode" not in make_settings(DATABASE_URL=raw).sync_database_url


def test_production_environment_does_not_force_ssl_on_local_database():
    s = make_settings(ENVIRONMENT="production", DATABASE_URL="postgresql://u:p@postgres:5432/db")
    assert "sslmode" not in s.sync_database_url


def test_explicit_sslmode_setting_is_honoured():
    local = make_settings(DB_SSLMODE="verify-full", DATABASE_URL="postgresql://u:p@postgres:5432/db")
    assert local.sync_database_url.endswith("?sslmode=verify-full")
    cloud_disabled = make_settings(DB_SSLMODE="disable", DATABASE_URL="postgresql://u:p@x.supabase.co/db")
    assert cloud_disabled.sync_database_url.endswith("sslmode=disable")


def test_sslmode_already_in_url_is_never_duplicated():
    url = make_settings(
        DB_SSLMODE="require", DATABASE_URL="postgresql://u:p@x.supabase.co/db?sslmode=prefer"
    ).sync_database_url
    assert url.count("sslmode") == 1 and url.endswith("sslmode=prefer")


def test_sslmode_appended_with_ampersand_when_query_exists():
    url = make_settings(DB_SSLMODE="require", DATABASE_URL="postgresql://u:p@h/db?application_name=x").sync_database_url
    assert url.endswith("application_name=x&sslmode=require")


def test_cloud_suffix_list_is_not_empty():
    assert "supabase.co" in CLOUD_DB_HOST_SUFFIXES


def test_default_pool_stays_below_postgres_connection_limit():
    s = make_settings(DATABASE_URL="postgresql://u:p@h/db")
    workers = 4  # gunicorn -w 4 do Dockerfile
    assert workers * (s.DB_POOL_SIZE + s.DB_MAX_OVERFLOW) <= 100


def test_vercel_cors_regex_is_restricted_to_the_project():
    regex = make_settings(DATABASE_URL="postgresql://u:p@h/db").CORS_ORIGIN_REGEX
    assert re.match(regex, "https://legisdata.vercel.app")
    assert re.match(regex, "https://legisdata-git-branch-team.vercel.app")
    assert not re.match(regex, "https://evil.vercel.app")
    assert not re.match(regex, "http://legisdata.vercel.app")
    assert not re.match(regex, "https://legisdata.vercel.app.evil.com")


def test_cors_origins_are_merged_without_duplicates():
    s = make_settings(DATABASE_URL="postgresql://u:p@h/db", CORS_ORIGINS="http://localhost:3000, https://app.example ,")
    assert s.all_cors_origins.count("http://localhost:3000") == 1
    assert s.all_cors_origins == ["http://localhost:3000", "https://app.example"]


def test_is_production_flag_is_case_insensitive():
    assert make_settings(DATABASE_URL="postgresql://u:p@h/db", ENVIRONMENT="Production").is_production
    assert not make_settings(DATABASE_URL="postgresql://u:p@h/db", ENVIRONMENT="development").is_production
