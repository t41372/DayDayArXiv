"""Configuration management using pydantic-settings."""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any, cast

from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

ENV_PREFIX = "ARXIV_"


def _coerce_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _coerce_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _coerce_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {key: value for key, value in dotenv_values(path).items() if key and value is not None}


class ProviderSettings(BaseModel):
    """OpenAI-compatible provider configuration."""

    base_url: str
    api_key: SecretStr
    model: str
    rpm: int = 20
    timeout_s: float = 60.0
    max_retries: int = 3


class LangfuseSettings(BaseModel):
    """Langfuse configuration."""

    enabled: bool = True
    host: str | None = None
    public_key: SecretStr | None = None
    secret_key: SecretStr | None = None
    session_note: str = "dev"

    def is_configured(self) -> bool:
        return bool(self.public_key and self.secret_key)


class LLMSettings(BaseModel):
    """LLM providers configuration."""

    weak: ProviderSettings
    strong: ProviderSettings
    backup: ProviderSettings | None = None


class Settings(BaseSettings):
    """Project settings with env + TOML support."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        extra="ignore",
    )

    data_dir: Path = Path("daydayarxiv_frontend/public/data")
    log_dir: Path = Path("logs")
    log_level: str = "INFO"

    category: str = "cs.AI"
    max_results: int = 1000
    concurrency: int = 5
    batch_size: int = 10
    force: bool = False
    paper_max_attempts: int = 3
    fail_on_error: bool = False
    state_save_interval_s: float = Field(default=1.0, ge=0)

    failure_patterns: list[str] = Field(default_factory=lambda: ["翻译失败", "生成失败", "快报生成失败"])

    llm: LLMSettings
    langfuse: LangfuseSettings = LangfuseSettings()

    @model_validator(mode="after")
    def _validate_provider_uniqueness(self) -> Settings:
        if self.langfuse.enabled and not self.langfuse.is_configured():
            raise ValueError(
                "Langfuse is enabled but ARXIV_LANGFUSE_PUBLIC_KEY/ARXIV_LANGFUSE_SECRET_KEY are missing"
            )
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            cast(PydanticBaseSettingsSource, _simple_env_settings),
            cast(PydanticBaseSettingsSource, _toml_settings),
            file_secret_settings,
        )


def _toml_settings() -> dict[str, Any]:
    env = {**_load_env_file(Path(".env")), **os.environ}
    config_path = env.get(f"{ENV_PREFIX}CONFIG")
    if not config_path:
        default = Path("daydayarxiv.toml")
        if default.exists():
            return _load_toml(default)
        return {}
    return _load_toml(Path(config_path))


def _simple_env_settings() -> dict[str, Any]:
    env_file = Path(".env")
    env = {**_load_env_file(env_file), **os.environ}
    data: dict[str, Any] = {}
    def set_value(key: str, target_key: str, *, cast_fn=None) -> None:
        raw = env.get(key)
        if raw is None or raw == "":
            return
        value = cast_fn(raw) if cast_fn else raw
        if value is None:
            return
        data[target_key] = value

    def set_nested(section: str, key: str, value: Any) -> None:
        if value is None or value == "":
            return
        data.setdefault(section, {})[key] = value

    def set_provider(provider: str, field: str, env_key: str, *, cast_fn=None) -> None:
        raw = env.get(env_key)
        if raw is None or raw == "":
            return
        value = cast_fn(raw) if cast_fn else raw
        if value is None:
            return
        data.setdefault("llm", {}).setdefault(provider, {})[field] = value

    set_value(f"{ENV_PREFIX}DATA_DIR", "data_dir")
    set_value(f"{ENV_PREFIX}LOG_DIR", "log_dir")
    set_value(f"{ENV_PREFIX}LOG_LEVEL", "log_level")
    set_value(f"{ENV_PREFIX}CATEGORY", "category")
    set_value(f"{ENV_PREFIX}MAX_RESULTS", "max_results", cast_fn=_coerce_int)
    set_value(f"{ENV_PREFIX}CONCURRENCY", "concurrency", cast_fn=_coerce_int)
    set_value(f"{ENV_PREFIX}BATCH_SIZE", "batch_size", cast_fn=_coerce_int)
    set_value(f"{ENV_PREFIX}FORCE", "force", cast_fn=_coerce_bool)
    set_value(f"{ENV_PREFIX}PAPER_MAX_ATTEMPTS", "paper_max_attempts", cast_fn=_coerce_int)
    set_value(f"{ENV_PREFIX}FAIL_ON_ERROR", "fail_on_error", cast_fn=_coerce_bool)
    set_value(f"{ENV_PREFIX}STATE_SAVE_INTERVAL_S", "state_save_interval_s", cast_fn=_coerce_float)

    failure_raw = env.get(f"{ENV_PREFIX}FAILURE_PATTERNS")
    if failure_raw:
        try:
            parsed = json.loads(failure_raw)
        except json.JSONDecodeError:
            parsed = [item.strip() for item in failure_raw.split(",") if item.strip()]
        if isinstance(parsed, list) and parsed:
            data["failure_patterns"] = parsed

    set_provider("weak", "base_url", f"{ENV_PREFIX}LLM_WEAK_BASE_URL")
    set_provider("weak", "api_key", f"{ENV_PREFIX}LLM_WEAK_API_KEY")
    set_provider("weak", "model", f"{ENV_PREFIX}LLM_WEAK_MODEL")
    set_provider("weak", "rpm", f"{ENV_PREFIX}LLM_WEAK_RPM", cast_fn=_coerce_int)
    set_provider("weak", "timeout_s", f"{ENV_PREFIX}LLM_WEAK_TIMEOUT_S", cast_fn=_coerce_float)
    set_provider("weak", "max_retries", f"{ENV_PREFIX}LLM_WEAK_MAX_RETRIES", cast_fn=_coerce_int)

    set_provider("strong", "base_url", f"{ENV_PREFIX}LLM_STRONG_BASE_URL")
    set_provider("strong", "api_key", f"{ENV_PREFIX}LLM_STRONG_API_KEY")
    set_provider("strong", "model", f"{ENV_PREFIX}LLM_STRONG_MODEL")
    set_provider("strong", "rpm", f"{ENV_PREFIX}LLM_STRONG_RPM", cast_fn=_coerce_int)
    set_provider("strong", "timeout_s", f"{ENV_PREFIX}LLM_STRONG_TIMEOUT_S", cast_fn=_coerce_float)
    set_provider("strong", "max_retries", f"{ENV_PREFIX}LLM_STRONG_MAX_RETRIES", cast_fn=_coerce_int)

    set_provider("backup", "base_url", f"{ENV_PREFIX}LLM_BACKUP_BASE_URL")
    set_provider("backup", "api_key", f"{ENV_PREFIX}LLM_BACKUP_API_KEY")
    set_provider("backup", "model", f"{ENV_PREFIX}LLM_BACKUP_MODEL")
    set_provider("backup", "rpm", f"{ENV_PREFIX}LLM_BACKUP_RPM", cast_fn=_coerce_int)
    set_provider("backup", "timeout_s", f"{ENV_PREFIX}LLM_BACKUP_TIMEOUT_S", cast_fn=_coerce_float)
    set_provider("backup", "max_retries", f"{ENV_PREFIX}LLM_BACKUP_MAX_RETRIES", cast_fn=_coerce_int)

    set_nested("langfuse", "enabled", _coerce_bool(env.get(f"{ENV_PREFIX}LANGFUSE_ENABLED")))
    set_nested("langfuse", "host", env.get(f"{ENV_PREFIX}LANGFUSE_HOST"))
    set_nested("langfuse", "public_key", env.get(f"{ENV_PREFIX}LANGFUSE_PUBLIC_KEY"))
    set_nested("langfuse", "secret_key", env.get(f"{ENV_PREFIX}LANGFUSE_SECRET_KEY"))
    set_nested("langfuse", "session_note", env.get(f"{ENV_PREFIX}LANGFUSE_SESSION_NOTE"))

    return data


def load_settings() -> Settings:
    """Load settings with helpful error messaging."""
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        raise SystemExit(f"Invalid configuration: {exc}") from exc
