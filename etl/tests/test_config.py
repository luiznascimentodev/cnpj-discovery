import pytest
from unittest.mock import patch
import os


def test_dsn_property_format():
    from config import Settings
    s = Settings(
        postgres_host="db", postgres_port=5432,
        postgres_db="mydb", postgres_user="user", postgres_password="pass"
    )
    assert s.dsn == "postgresql://user:pass@db:5432/mydb"


def test_dsn_with_custom_port():
    from config import Settings
    s = Settings(postgres_port=5433, postgres_password="x")
    assert ":5433/" in s.dsn


def test_batch_size_validator_raises_on_zero():
    from config import Settings
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(etl_batch_size=0, postgres_password="x")


def test_batch_size_validator_raises_on_negative():
    from config import Settings
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(etl_batch_size=-1, postgres_password="x")


def test_workers_validator_raises_on_zero():
    from config import Settings
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(etl_workers=0, postgres_password="x")


def test_default_values():
    from config import Settings
    s = Settings(postgres_password="x")
    assert s.postgres_host == "localhost"
    assert s.postgres_port == 5432
    assert s.etl_batch_size == 50_000
    assert s.etl_workers == 4
    assert s.environment == "development"
    assert s.discord_webhook_url == ""
    assert s.rf_share_token == "gn672Ad4CF8N6TK"


def test_settings_from_env_vars(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "myhost")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("ETL_BATCH_SIZE", "10000")
    from importlib import reload
    import config as cfg_module
    reload(cfg_module)
    # Instanciar diretamente para pegar os env vars
    from config import Settings
    s = Settings()
    assert s.postgres_host == "myhost"
    assert s.etl_batch_size == 10000
