import os
import textwrap

import pytest
from pydantic import ValidationError

from daydayarxiv.settings import (
    Settings,
    _coerce_bool,
    _coerce_int,
    _legacy_env_settings,
    _load_toml,
    _toml_settings,
    load_settings,
)


def _set_required_env(monkeypatch, *, prefix: str = "DAYDAYARXIV_", include_backup: bool = True):
    monkeypatch.setenv(f"{prefix}LLM__WEAK__BASE_URL", "https://weak.local")
    monkeypatch.setenv(f"{prefix}LLM__WEAK__API_KEY", "weak-key")
    monkeypatch.setenv(f"{prefix}LLM__WEAK__MODEL", "weak-model")
    monkeypatch.setenv(f"{prefix}LLM__STRONG__BASE_URL", "https://strong.local")
    monkeypatch.setenv(f"{prefix}LLM__STRONG__API_KEY", "strong-key")
    monkeypatch.setenv(f"{prefix}LLM__STRONG__MODEL", "strong-model")
    if include_backup:
        monkeypatch.setenv(f"{prefix}LLM__BACKUP__BASE_URL", "https://backup.local")
        monkeypatch.setenv(f"{prefix}LLM__BACKUP__API_KEY", "backup-key")
        monkeypatch.setenv(f"{prefix}LLM__BACKUP__MODEL", "backup-model")


def test_settings_langfuse_requires_keys(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("DAYDAYARXIV_LANGFUSE__PUBLIC_KEY", raising=False)
    monkeypatch.delenv("DAYDAYARXIV_LANGFUSE__SECRET_KEY", raising=False)
    monkeypatch.setenv("DAYDAYARXIV_LANGFUSE__ENABLED", "true")
    with pytest.raises(SystemExit):
        load_settings()


def test_settings_loads_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.setenv("DAYDAYARXIV_LANGFUSE__ENABLED", "false")
    settings = Settings()
    assert settings.llm.weak.model == "weak-model"
    assert settings.llm.strong.base_url == "https://strong.local"


def test_settings_allows_missing_backup(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch, include_backup=False)
    monkeypatch.setenv("DAYDAYARXIV_LANGFUSE__ENABLED", "false")
    settings = Settings()
    assert settings.llm.backup is None


def test_load_settings_success(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.setenv("DAYDAYARXIV_LANGFUSE__ENABLED", "false")
    settings = load_settings()
    assert settings.llm.backup.base_url == "https://backup.local"


def test_settings_requires_unique_base_urls(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.setenv("DAYDAYARXIV_LLM__STRONG__BASE_URL", "https://weak.local")
    monkeypatch.setenv("DAYDAYARXIV_LANGFUSE__ENABLED", "false")
    with pytest.raises(ValidationError):
        Settings()


def test_settings_legacy_env_mapping(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_BASE_URL", "https://legacy.local")
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    monkeypatch.setenv("LLM_MODEL", "legacy-model")
    monkeypatch.setenv("LLM_RPM", "12")
    monkeypatch.setenv("OPENAI_API_BASE_URL_STRONG", "https://legacy-strong.local")
    monkeypatch.setenv("OPENAI_API_KEY_STRONG", "legacy-strong-key")
    monkeypatch.setenv("LLM_MODEL_STRONG", "legacy-strong-model")
    monkeypatch.setenv("OPENAI_API_BASE_URL_BACKUP", "https://legacy-backup.local")
    monkeypatch.setenv("OPENAI_API_KEY_BACKUP", "legacy-backup-key")
    monkeypatch.setenv("LLM_MODEL_BACKUP", "legacy-backup-model")
    monkeypatch.setenv("DAYDAYARXIV_LANGFUSE__ENABLED", "false")

    settings = Settings()
    assert settings.llm.weak.base_url == "https://legacy.local"
    assert settings.llm.weak.rpm == 12
    assert settings.llm.backup.model == "legacy-backup-model"


def test_settings_toml_loading(monkeypatch, tmp_path):
    config_path = tmp_path / "daydayarxiv.toml"
    config_path.write_text(
        textwrap.dedent(
            """
            category = "cs.CL"
            allow_shared_providers = true
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
        if key.startswith("DAYDAYARXIV_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DAYDAYARXIV_CONFIG", str(config_path))
    settings = Settings()
    assert settings.category == "cs.CL"
    assert settings.allow_shared_providers is True
    assert settings.llm.backup.base_url == "https://backup.local"


def test_load_settings_invalid_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_required_env(monkeypatch)
    monkeypatch.setenv("DAYDAYARXIV_LLM__STRONG__BASE_URL", "https://weak.local")
    monkeypatch.setenv("DAYDAYARXIV_LANGFUSE__ENABLED", "false")
    with pytest.raises(SystemExit):
        load_settings()


def test_coerce_helpers():
    assert _coerce_bool(None) is None
    assert _coerce_bool("yes") is True
    assert _coerce_bool("no") is False
    assert _coerce_int("") is None
    assert _coerce_int("abc") is None
    assert _coerce_int("12") == 12


def test_load_toml_missing(tmp_path):
    missing = tmp_path / "missing.toml"
    assert _load_toml(missing) == {}


def test_toml_settings_default_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "daydayarxiv.toml"
    config_path.write_text('category = "cs.LG"\n')
    data = _toml_settings()
    assert data["category"] == "cs.LG"


def test_legacy_env_settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.setenv("RPM", "8")
    monkeypatch.setenv("OPENAI_API_BASE_URL", "https://legacy.local")
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    monkeypatch.setenv("LLM_MODEL", "legacy-model")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://langfuse.local")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pub")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sec")
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("DAYDAYARXIV_FORCE", "1")
    monkeypatch.setenv("DAYDAYARXIV_MAX_RESULTS", "42")

    data = _legacy_env_settings()
    assert data["llm"]["weak"]["rpm"] == 8
    assert data["langfuse"]["host"] == "https://langfuse.local"
    assert data["langfuse"]["enabled"] is True
    assert data["force"] is True
    assert data["max_results"] == 42


def test_legacy_env_from_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_BASE_URL=https://legacy.local",
                "OPENAI_API_KEY=legacy-key",
                "LLM_MODEL=legacy-model",
                "OPENAI_API_BASE_URL_STRONG=https://legacy-strong.local",
                "OPENAI_API_KEY_STRONG=legacy-strong-key",
                "LLM_MODEL_STRONG=legacy-strong-model",
                "OPENAI_API_BASE_URL_BACKUP=https://legacy-backup.local",
                "OPENAI_API_KEY_BACKUP=legacy-backup-key",
                "LLM_MODEL_BACKUP=legacy-backup-model",
                "LANGFUSE_ENABLED=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    data = _legacy_env_settings()
    assert data["llm"]["weak"]["base_url"] == "https://legacy.local"
    assert data["llm"]["strong"]["model"] == "legacy-strong-model"
    assert data["llm"]["backup"]["model"] == "legacy-backup-model"
    assert data["langfuse"]["enabled"] is False
