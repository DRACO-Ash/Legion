import configparser

import pytest

from src import config as config_module
from src.config import load_settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in [
        "PORT",
        "ALLOWED_ORIGIN",
        "TEAM_TOKEN",
        "UDL_BASE_URL",
        "UDL_USERNAME",
        "UDL_PASSWORD",
        "UDL_TIMEOUT_SECONDS",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_defaults_when_nothing_set(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "CRED_PATH", tmp_path / "missing.ini")
    settings = load_settings()
    assert settings.port == 8080
    assert settings.udl_base_url == "https://unifieddatalibrary.com"
    assert settings.udl_credentials_configured is False
    assert settings.auth_required is False


def test_env_vars_take_precedence_over_credentials_ini(monkeypatch, tmp_path):
    ini_path = tmp_path / "credentials.ini"
    parser = configparser.ConfigParser()
    parser["udl"] = {"username": "ini_user", "password": "ini_pass"}
    with open(ini_path, "w") as fh:
        parser.write(fh)
    monkeypatch.setattr(config_module, "CRED_PATH", ini_path)

    monkeypatch.setenv("UDL_USERNAME", "env_user")
    monkeypatch.setenv("UDL_PASSWORD", "env_pass")

    settings = load_settings()
    assert settings.udl_username == "env_user"
    assert settings.udl_password == "env_pass"


def test_credentials_ini_fallback_when_env_unset(monkeypatch, tmp_path):
    ini_path = tmp_path / "credentials.ini"
    parser = configparser.ConfigParser()
    parser["udl"] = {"username": "ini_user", "password": "ini_pass"}
    with open(ini_path, "w") as fh:
        parser.write(fh)
    monkeypatch.setattr(config_module, "CRED_PATH", ini_path)

    settings = load_settings()
    assert settings.udl_username == "ini_user"
    assert settings.udl_password == "ini_pass"
    assert settings.udl_credentials_configured is True


def test_credentials_ini_missing_file_is_a_silent_miss(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "CRED_PATH", tmp_path / "does-not-exist.ini")
    settings = load_settings()
    assert settings.udl_credentials_configured is False


def test_credentials_ini_incomplete_section_is_ignored(monkeypatch, tmp_path):
    ini_path = tmp_path / "credentials.ini"
    parser = configparser.ConfigParser()
    parser["udl"] = {"username": "only_user"}  # no password
    with open(ini_path, "w") as fh:
        parser.write(fh)
    monkeypatch.setattr(config_module, "CRED_PATH", ini_path)

    settings = load_settings()
    assert settings.udl_credentials_configured is False


def test_strips_quotes_and_whitespace_from_pasted_env_values(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "CRED_PATH", tmp_path / "missing.ini")
    monkeypatch.setenv("ALLOWED_ORIGIN", '  "https://example.com"  ')
    monkeypatch.setenv("PORT", " 9090 ")
    settings = load_settings()
    assert settings.allowed_origin == "https://example.com"
    assert settings.port == 9090


def test_auth_required_true_when_team_token_set(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "CRED_PATH", tmp_path / "missing.ini")
    monkeypatch.setenv("TEAM_TOKEN", "some-token")
    settings = load_settings()
    assert settings.auth_required is True
