import os
import textwrap

import pytest

from daydayarxiv.settings import (
    Settings,
    _coerce_bool,
    _coerce_int,
    _coerce_float,
    _load_toml,
    _simple_env_settings,
    _toml_settings,
    load_settings,
)


def _set_required_env(monkeypatch, *, include_backup: bool = True):
    monkeypatch.setenv("ARXIV_LLM_WEAK_BASE_URL", "https://weak.local")
    monkeypatch.setenv("ARXIV_LLM_WEAK_API_KEY", "weak-key")
    monkeypatch.setenv("ARXIV_LLM_WEAK_MODEL", "weak-model")
    monkeypatch.setenv("ARXIV_LLM_STRONG_BASE_URL", "https://strong.local")
    monkeypatch.setenv("ARXIV_LLM_STRONG_API_KEY", "strong-key")
    monkeypatch.setenv("ARXIV_LLM_STRONG_MODEL", "strong-model")
    if include_backup:
        monkeypatch.setenv("ARXIV_LLM_BACKUP_BASE_URL", "https://backup.local")
        monkeypatch.setenv("ARXIV_LLM_BACKUP_API_KEY", "backup-key")
        monkeypatch.setenv("ARXIV_LLM_BACKUP_MODEL", "backup-model")


def test_settings_langfuse_requires_keys(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.delenv("ARXIV_LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("ARXIV_LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setenv("ARXIV_LANGFUSE_ENABLED", "true")
    with pytest.raises(SystemExit):
        load_settings()


def test_settings_loads_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.setenv("ARXIV_LANGFUSE_ENABLED", "false")
    settings = Settings()
    assert settings.llm.weak.model == "weak-model"
    assert settings.llm.strong.base_url == "https://strong.local"


def test_settings_allows_missing_backup(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch, include_backup=False)
    monkeypatch.setenv("ARXIV_LANGFUSE_ENABLED", "false")
    settings = Settings()
    assert settings.llm.backup is None


def test_load_settings_success(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.setenv("ARXIV_LANGFUSE_ENABLED", "false")
    settings = load_settings()
    assert settings.llm.backup.base_url == "https://backup.local"


def test_settings_allows_shared_base_urls(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch, include_backup=False)
    monkeypatch.setenv("ARXIV_LLM_STRONG_BASE_URL", "https://weak.local")
    monkeypatch.setenv("ARXIV_LANGFUSE_ENABLED", "false")
    settings = Settings()
    assert settings.llm.strong.base_url == "https://weak.local"


def test_settings_toml_loading(monkeypatch, tmp_path):
    config_path = tmp_path / "daydayarxiv.toml"
    config_path.write_text(
        textwrap.dedent(
            """
            category = "cs.CL"
            [llm.weak]
            base_url = "https://weak.local"
            api_key = "weak-key"
            model = "weak-model"
            [llm.strong]
            base_url = "https://weak.local"
            api_key = "strong-key"
            model = "strong-model"
            [llm.backup]
            base_url = "https://backup.local"
            api_key = "backup-key"
            model = "backup-model"
            [langfuse]
            enabled = false
            """
    ).strip()
    )
    for key in list(os.environ):
        if key.startswith("ARXIV_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ARXIV_CONFIG", str(config_path))
    settings = Settings()
    assert settings.category == "cs.CL"
    assert settings.llm.backup.base_url == "https://backup.local"


def test_load_settings_allows_shared_base_urls(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch, include_backup=False)
    monkeypatch.setenv("ARXIV_LLM_STRONG_BASE_URL", "https://weak.local")
    monkeypatch.setenv("ARXIV_LANGFUSE_ENABLED", "false")
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


def test_load_toml_missing(tmp_path):
    missing = tmp_path / "missing.toml"
    assert _load_toml(missing) == {}


def test_toml_settings_default_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "daydayarxiv.toml"
    config_path.write_text('category = "cs.LG"\n')
    data = _toml_settings()
    assert data["category"] == "cs.LG"


def test_toml_settings_from_env_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "custom.toml"
    config_path.write_text('category = "cs.NE"\n')
    (tmp_path / ".env").write_text(f"ARXIV_CONFIG={config_path}\n", encoding="utf-8")
    data = _toml_settings()
    assert data["category"] == "cs.NE"


def test_simple_env_settings_invalid_values(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ARXIV_MAX_RESULTS", "not-int")
    monkeypatch.setenv("ARXIV_LLM_WEAK_TIMEOUT_S", "bad-float")
    data = _simple_env_settings()
    assert "max_results" not in data
    assert data.get("llm", {}).get("weak", {}) == {}


def test_simple_env_settings_failure_patterns(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ARXIV_FAILURE_PATTERNS", '["a","b"]')
    data = _simple_env_settings()
    assert data["failure_patterns"] == ["a", "b"]
    monkeypatch.setenv("ARXIV_FAILURE_PATTERNS", "a, b")
    data = _simple_env_settings()
    assert data["failure_patterns"] == ["a", "b"]


def test_simple_env_settings_sets_values(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ARXIV_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ARXIV_MAX_RESULTS", "50")
    data = _simple_env_settings()
    assert data["log_level"] == "DEBUG"
    assert data["max_results"] == 50
