import asyncio
import os

import pytest

from daydayarxiv.llm.client import (
    LLMClient,
    LLMNonRetryableError,
    LLMRetryableError,
    Provider,
    RateLimiter,
    _classify_error,
    _is_valid_output,
    _prepare_langfuse_env,
)
from daydayarxiv.llm.validators import LLMValidationError
from daydayarxiv.settings import LangfuseSettings, ProviderSettings


class DummyMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class DummyChoice:
    def __init__(self, content: str) -> None:
        self.message = DummyMessage(content)


class DummyResponse:
    def __init__(self, content: str) -> None:
        self.choices = [DummyChoice(content)]


class EmptyResponse:
    def __init__(self) -> None:
        self.choices = []


class DummyChat:
    def __init__(self, responses):
        self._responses = responses
        self.completions = self

    async def create(self, **kwargs):
        value = self._responses.pop(0)
        if isinstance(value, Exception):
            raise value
        if value == "__empty__":
            return EmptyResponse()
        return DummyResponse(value)


class DummyClient:
    def __init__(self, responses):
        self.chat = DummyChat(responses)


def _provider_settings() -> ProviderSettings:
    return ProviderSettings(
        base_url="https://example.com",
        api_key="key",
        model="model",
        rpm=1000,
        max_retries=0,
    )


def _make_llm(monkeypatch, weak_client, backup_client=None):
    settings = _provider_settings()
    providers = {
        "weak": Provider("weak", settings, weak_client, RateLimiter(1000)),
        "strong": Provider("strong", settings, weak_client, RateLimiter(1000)),
    }
    if backup_client:
        providers["backup"] = Provider("backup", settings, backup_client, RateLimiter(1000))

    def _build_provider(self, name, *_args):
        return providers[name]

    monkeypatch.setattr(LLMClient, "_build_provider", _build_provider)
    return LLMClient(
        weak=settings,
        strong=settings,
        backup=settings if backup_client else None,
        langfuse=LangfuseSettings(enabled=False),
        failure_patterns=["翻译失败"],
    )


@pytest.mark.asyncio
async def test_llm_fallback_on_invalid(monkeypatch):
    weak_client = DummyClient(["翻译失败", "翻译失败", "翻译失败"])
    backup_client = DummyClient(["有效输出"])
    llm = _make_llm(monkeypatch, weak_client, backup_client)
    result = await llm.translate_title("Title", "Abstract")
    assert result == "有效输出"


@pytest.mark.asyncio
async def test_llm_success(monkeypatch):
    weak_client = DummyClient(["OK"])
    backup_client = DummyClient(["备用"])
    llm = _make_llm(monkeypatch, weak_client, backup_client)
    result = await llm.tldr("Title", "Abstract")
    assert result == "OK"


@pytest.mark.asyncio
async def test_llm_summary(monkeypatch):
    weak_client = DummyClient(["Summary"])
    backup_client = DummyClient(["Summary"])
    llm = _make_llm(monkeypatch, weak_client, backup_client)
    result = await llm.daily_summary("Paper", "2025-01-01")
    assert result == "Summary"


def test_rate_limiter_wait():
    limiter = RateLimiter(600)
    asyncio.run(limiter.wait())


def test_rate_limiter_invalid_rpm():
    with pytest.raises(ValueError):
        RateLimiter(0)


@pytest.mark.asyncio
async def test_rate_limiter_sleep(monkeypatch):
    limiter = RateLimiter(60)
    limiter.last_request_time = 100.0
    calls = {"sleep": 0, "monotonic": 0}

    def _monotonic() -> float:
        calls["monotonic"] += 1
        return 100.5 if calls["monotonic"] == 1 else 101.0

    async def _sleep(duration: float) -> None:
        assert duration == pytest.approx(0.5)
        calls["sleep"] += 1

    monkeypatch.setattr("daydayarxiv.llm.client.time.monotonic", _monotonic)
    monkeypatch.setattr("daydayarxiv.llm.client.asyncio.sleep", _sleep)

    await limiter.wait()
    assert calls["sleep"] == 1


@pytest.mark.asyncio
async def test_llm_request_empty_response(monkeypatch):
    weak_client = DummyClient(["__empty__"])
    backup_client = DummyClient(["Fallback"])
    llm = _make_llm(monkeypatch, weak_client, backup_client)
    provider = llm.providers["weak"]
    with pytest.raises(LLMRetryableError):
        await llm._request(provider, model="m", messages=[], temperature=0.0)


@pytest.mark.asyncio
async def test_llm_request_empty_content(monkeypatch):
    weak_client = DummyClient([" "])
    backup_client = DummyClient(["Fallback"])
    llm = _make_llm(monkeypatch, weak_client, backup_client)
    provider = llm.providers["weak"]
    with pytest.raises(LLMRetryableError):
        await llm._request(provider, model="m", messages=[], temperature=0.0)


def test_prepare_langfuse_env(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    settings = LangfuseSettings(
        enabled=True,
        host="https://langfuse.local",
        public_key="pub",
        secret_key="sec",
        session_note="note",
    )
    _prepare_langfuse_env(settings)
    assert "LANGFUSE_PUBLIC_KEY" in os.environ


def test_llm_client_build_provider(monkeypatch):
    settings = _provider_settings()
    llm = LLMClient(
        weak=settings,
        strong=settings.model_copy(update={"base_url": "https://strong.local"}),
        backup=settings.model_copy(update={"base_url": "https://backup.local"}),
        langfuse=LangfuseSettings(enabled=False),
        failure_patterns=[],
    )
    assert set(llm.providers.keys()) == {"weak", "strong", "backup"}


def test_llm_client_without_backup():
    settings = _provider_settings()
    llm = LLMClient(
        weak=settings,
        strong=settings.model_copy(update={"base_url": "https://strong.local"}),
        backup=None,
        langfuse=LangfuseSettings(enabled=False),
        failure_patterns=[],
    )
    assert set(llm.providers.keys()) == {"weak", "strong"}


def test_is_valid_output_empty():
    assert _is_valid_output("", ["bad"]) is False
    assert _is_valid_output(" ", ["bad"]) is False


@pytest.mark.asyncio
async def test_llm_fallback_raises_last_error(monkeypatch):
    weak_client = DummyClient(["__empty__"])
    backup_client = DummyClient(["__empty__"])
    llm = _make_llm(monkeypatch, weak_client, backup_client)

    async def _fail_request(*_args, **_kwargs):
        raise LLMRetryableError("boom")

    monkeypatch.setattr(LLMClient, "_request", _fail_request)

    with pytest.raises(LLMRetryableError):
        await llm.tldr("Title", "Abstract")


@pytest.mark.asyncio
async def test_llm_no_backup_raises_on_invalid(monkeypatch):
    weak_client = DummyClient(["翻译失败", "翻译失败", "翻译失败"])
    llm = _make_llm(monkeypatch, weak_client, None)
    with pytest.raises(LLMValidationError):
        await llm.translate_title("Title", "Abstract")


@pytest.mark.asyncio
async def test_llm_backup_invalid_raises(monkeypatch):
    weak_client = DummyClient(["翻译失败", "翻译失败", "翻译失败"])
    backup_client = DummyClient(["翻译失败"])
    llm = _make_llm(monkeypatch, weak_client, backup_client)
    with pytest.raises(LLMValidationError):
        await llm.translate_title("Title", "Abstract")


def test_classify_error_branches(monkeypatch):
    import daydayarxiv.llm.client as client_module

    class DummyStatusError(Exception):
        def __init__(self, status_code: int):
            self.status_code = status_code

    class DummyRateLimitError(Exception):
        pass

    class DummyAuthError(Exception):
        pass

    monkeypatch.setattr(client_module, "APIStatusError", DummyStatusError)
    monkeypatch.setattr(client_module, "RateLimitError", DummyRateLimitError)
    monkeypatch.setattr(client_module, "APIConnectionError", DummyRateLimitError)
    monkeypatch.setattr(client_module, "APITimeoutError", DummyRateLimitError)
    monkeypatch.setattr(client_module, "AuthenticationError", DummyAuthError)
    monkeypatch.setattr(client_module, "PermissionDeniedError", DummyAuthError)
    monkeypatch.setattr(client_module, "BadRequestError", DummyAuthError)
    monkeypatch.setattr(client_module, "NotFoundError", DummyAuthError)
    monkeypatch.setattr(client_module, "ConflictError", DummyAuthError)
    monkeypatch.setattr(client_module, "UnprocessableEntityError", DummyAuthError)

    assert isinstance(_classify_error(DummyStatusError(401)), LLMNonRetryableError)
    assert isinstance(_classify_error(DummyStatusError(500)), LLMRetryableError)
    assert isinstance(_classify_error(DummyRateLimitError()), LLMRetryableError)
    assert isinstance(_classify_error(DummyAuthError()), LLMNonRetryableError)
    assert isinstance(_classify_error(Exception("boom")), LLMRetryableError)
