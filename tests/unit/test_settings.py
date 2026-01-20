import os
import pytest

from daydayarxiv.settings import (
    Settings,
    _coerce_bool,
    _coerce_int,
    _coerce_float,
    _simple_env_settings,
    load_settings,
)


def _set_required_env(monkeypatch, *, include_backup: bool = True):
    monkeypatch.setenv("DDARXIV_LLM_WEAK_BASE_URL", "https://weak.local")
    monkeypatch.setenv("DDARXIV_LLM_WEAK_API_KEY", "weak-key")
    monkeypatch.setenv("DDARXIV_LLM_WEAK_MODEL", "weak-model")
    monkeypatch.setenv("DDARXIV_LLM_STRONG_BASE_URL", "https://strong.local")
    monkeypatch.setenv("DDARXIV_LLM_STRONG_API_KEY", "strong-key")
    monkeypatch.setenv("DDARXIV_LLM_STRONG_MODEL", "strong-model")
    if include_backup:
        monkeypatch.setenv("DDARXIV_LLM_BACKUP_BASE_URL", "https://backup.local")
        monkeypatch.setenv("DDARXIV_LLM_BACKUP_API_KEY", "backup-key")
        monkeypatch.setenv("DDARXIV_LLM_BACKUP_MODEL", "backup-model")


def test_settings_langfuse_requires_keys(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.delenv("DDARXIV_LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("DDARXIV_LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setenv("DDARXIV_LANGFUSE_ENABLED", "true")
    with pytest.raises(SystemExit):
        load_settings()


def test_settings_loads_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.setenv("DDARXIV_LANGFUSE_ENABLED", "false")
    settings = Settings()
    assert settings.llm.weak.model == "weak-model"
    assert settings.llm.strong.base_url == "https://strong.local"


def test_settings_allows_missing_backup(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch, include_backup=False)
    monkeypatch.setenv("DDARXIV_LANGFUSE_ENABLED", "false")
    settings = Settings()
    assert settings.llm.backup is None


def test_load_settings_success(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.setenv("DDARXIV_LANGFUSE_ENABLED", "false")
    settings = load_settings()
    assert settings.llm.backup.base_url == "https://backup.local"


def test_settings_allows_shared_base_urls(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch, include_backup=False)
    monkeypatch.setenv("DDARXIV_LLM_STRONG_BASE_URL", "https://weak.local")
    monkeypatch.setenv("DDARXIV_LANGFUSE_ENABLED", "false")
    settings = Settings()
    assert settings.llm.strong.base_url == "https://weak.local"


def test_load_settings_allows_shared_base_urls(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch, include_backup=False)
    monkeypatch.setenv("DDARXIV_LLM_STRONG_BASE_URL", "https://weak.local")
    monkeypatch.setenv("DDARXIV_LANGFUSE_ENABLED", "false")
    settings = load_settings()
    assert settings.llm.strong.base_url == "https://weak.local"


def test_coerce_helpers():
    assert _coerce_bool(None) is None
    assert _coerce_bool("yes") is True
    assert _coerce_bool("no") is False
    assert _coerce_int("") is None
    assert _coerce_int("abc") is None
    assert _coerce_int("12") == 12
    assert _coerce_float(None) is None
    assert _coerce_float("") is None
    assert _coerce_float("abc") is None
    assert _coerce_float("1.25") == 1.25




def test_simple_env_settings_invalid_values(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DDARXIV_MAX_RESULTS", "not-int")
    monkeypatch.setenv("DDARXIV_LLM_WEAK_TIMEOUT_S", "bad-float")
    data = _simple_env_settings()
    assert "max_results" not in data
    assert data.get("llm", {}).get("weak", {}) == {}


def test_simple_env_settings_failure_patterns(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DDARXIV_FAILURE_PATTERNS", '["a","b"]')
    data = _simple_env_settings()
    assert data["failure_patterns"] == ["a", "b"]
    monkeypatch.setenv("DDARXIV_FAILURE_PATTERNS", "a, b")
    data = _simple_env_settings()
    assert data["failure_patterns"] == ["a", "b"]


def test_simple_env_settings_sets_values(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DDARXIV_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DDARXIV_MAX_RESULTS", "50")
    data = _simple_env_settings()
    assert data["log_level"] == "DEBUG"
    assert data["max_results"] == 50
