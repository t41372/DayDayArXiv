"""Configuration management using pydantic-settings."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


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


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


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
    backup: ProviderSettings


class Settings(BaseSettings):
    """Project settings with env + TOML support."""

    model_config = SettingsConfigDict(
        env_prefix="DAYDAYARXIV_",
        env_nested_delimiter="__",
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

    failure_patterns: list[str] = Field(default_factory=lambda: ["翻译失败", "生成失败", "快报生成失败"])

    allow_shared_providers: bool = False

    llm: LLMSettings
    langfuse: LangfuseSettings = LangfuseSettings()

    @model_validator(mode="after")
    def _validate_provider_uniqueness(self) -> Settings:
        if self.allow_shared_providers:
            return self
        base_urls = {
            "weak": self.llm.weak.base_url,
            "strong": self.llm.strong.base_url,
            "backup": self.llm.backup.base_url,
        }
        unique_urls = set(base_urls.values())
        if len(unique_urls) != len(base_urls):
            raise ValueError(
                "LLM providers must use different base_url values (set allow_shared_providers=true to override)"
            )
        if self.langfuse.enabled and not self.langfuse.is_configured():
            raise ValueError("Langfuse is enabled but LANGFUSE_PUBLIC_KEY/SECRET_KEY are missing")
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
            env_settings,
            dotenv_settings,
            cast(PydanticBaseSettingsSource, _legacy_env_settings),
            cast(PydanticBaseSettingsSource, _toml_settings),
            file_secret_settings,
        )


def _toml_settings() -> dict[str, Any]:
    config_path = os.environ.get("DAYDAYARXIV_CONFIG")
    if not config_path:
        default = Path("daydayarxiv.toml")
        if default.exists():
            return _load_toml(default)
        return {}
    return _load_toml(Path(config_path))


def _legacy_env_settings() -> dict[str, Any]:
    env = os.environ
    data: dict[str, Any] = {}
    if env.get("RPM") and not env.get("LLM_RPM"):
        env = {**env, "LLM_RPM": env.get("RPM", "")}

    def set_provider(prefix: str, mapping: dict[str, str]) -> None:
        provider: dict[str, Any] = {}
        base_url = env.get(mapping.get("base_url", ""))
        api_key = env.get(mapping.get("api_key", ""))
        model = env.get(mapping.get("model", ""))
        rpm = _coerce_int(env.get(mapping.get("rpm", "")))
        if base_url:
            provider["base_url"] = base_url
        if api_key:
            provider["api_key"] = api_key
        if model:
            provider["model"] = model
        if rpm is not None:
            provider["rpm"] = rpm
        if provider:
            data.setdefault("llm", {})[prefix] = provider

    set_provider(
        "weak",
        {
            "base_url": "OPENAI_API_BASE_URL",
            "api_key": "OPENAI_API_KEY",
            "model": "LLM_MODEL",
            "rpm": "LLM_RPM",
        },
    )

    set_provider(
        "strong",
        {
            "base_url": "OPENAI_API_BASE_URL_STRONG",
            "api_key": "OPENAI_API_KEY_STRONG",
            "model": "LLM_MODEL_STRONG",
            "rpm": "LLM_RPM_STRONG",
        },
    )

    set_provider(
        "backup",
        {
            "base_url": "OPENAI_API_BASE_URL_BACKUP",
            "api_key": "OPENAI_API_KEY_BACKUP",
            "model": "LLM_MODEL_BACKUP",
            "rpm": "LLM_RPM_BACKUP",
        },
    )

    langfuse: dict[str, Any] = {}
    if env.get("LANGFUSE_HOST"):
        langfuse["host"] = env.get("LANGFUSE_HOST")
    if env.get("LANGFUSE_BASE_URL") and "host" not in langfuse:
        langfuse["host"] = env.get("LANGFUSE_BASE_URL")
    if env.get("LANGFUSE_PUBLIC_KEY"):
        langfuse["public_key"] = env.get("LANGFUSE_PUBLIC_KEY")
    if env.get("LANGFUSE_SECRET_KEY"):
        langfuse["secret_key"] = env.get("LANGFUSE_SECRET_KEY")
    if env.get("LANGFUSE_SESSION_NOTE"):
        langfuse["session_note"] = env.get("LANGFUSE_SESSION_NOTE")
    if env.get("LANGFUSE_ENABLED"):
        enabled = _coerce_bool(env.get("LANGFUSE_ENABLED"))
        if enabled is not None:
            langfuse["enabled"] = enabled
    if langfuse:
        data["langfuse"] = langfuse

    if env.get("DAYDAYARXIV_FORCE"):
        force_value = _coerce_bool(env.get("DAYDAYARXIV_FORCE"))
        if force_value is not None:
            data["force"] = force_value

    if env.get("DAYDAYARXIV_MAX_RESULTS"):
        max_results = _coerce_int(env.get("DAYDAYARXIV_MAX_RESULTS"))
        if max_results is not None:
            data["max_results"] = max_results

    return data


def load_settings() -> Settings:
    """Load settings with helpful error messaging."""
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        raise SystemExit(f"Invalid configuration: {exc}") from exc
