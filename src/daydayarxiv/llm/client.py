"""LLM client with retries, fallbacks, rate limiting, and Langfuse tracing."""

from __future__ import annotations

import asyncio
import importlib
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, ParamSpec, Protocol, TypeVar, cast

from loguru import logger
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from openai import AsyncOpenAI as OpenAIAsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from daydayarxiv.llm.validators import LLMValidationError
from daydayarxiv.prompts.daily_summary_prompt import (
    DAILY_SUMMARY_USER_INSTRUCTION,
    get_daily_summary_system_prompt,
)
from daydayarxiv.prompts.tldr_prompt import (
    TLDR_ASSISTANT_EXAMPLE,
    TLDR_SYSTEM_PROMPT,
    TLDR_USER_EXAMPLE,
)
from daydayarxiv.prompts.translate_title_prompt import (
    TRANSLATE_TITLE_ASSISTANT_EXAMPLE,
    TRANSLATE_TITLE_SYSTEM_PROMPT,
    TRANSLATE_TITLE_USER_EXAMPLE,
)
from daydayarxiv.settings import LangfuseSettings, ProviderSettings

P = ParamSpec("P")
R = TypeVar("R")


class LangfuseContext(Protocol):
    def update_current_trace(self, **kwargs: Any) -> None: ...


def _identity_observe(*_args: Any, **_kwargs: Any) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        return func

    return decorator


try:  # pragma: no cover - optional dependency path
    _langfuse_decorators = importlib.import_module("langfuse.decorators")
    _langfuse_context = _langfuse_decorators.langfuse_context
    _observe = _langfuse_decorators.observe
except Exception:  # pragma: no cover - fallback for optional dependency

    class _DummyLangfuseContext:
        def update_current_trace(self, **_kwargs: Any) -> None:
            return None

    _langfuse_context = _DummyLangfuseContext()
    _observe = _identity_observe

langfuse_context = cast(LangfuseContext, _langfuse_context)


def observe(*args: Any, **kwargs: Any) -> Callable[[Callable[P, R]], Callable[P, R]]:
    return cast(Callable[[Callable[P, R]], Callable[P, R]], _observe(*args, **kwargs))


try:  # pragma: no cover - optional dependency path
    _langfuse_openai = importlib.import_module("langfuse.openai")
    LangfuseAsyncOpenAI = cast(type[OpenAIAsyncOpenAI], _langfuse_openai.AsyncOpenAI)
except Exception:  # pragma: no cover - fallback for optional dependency
    LangfuseAsyncOpenAI = OpenAIAsyncOpenAI


class LLMRetryableError(RuntimeError):
    """Retryable LLM request error."""


class LLMNonRetryableError(RuntimeError):
    """Non-retryable LLM request error."""


class RateLimiter:
    """Smooth rate limiter for API calls."""

    def __init__(self, rpm: int) -> None:
        if rpm <= 0:
            raise ValueError("rpm must be > 0")
        self.rpm = rpm
        self.interval = 60.0 / rpm
        self.last_request_time = 0.0
        self.lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_request_time
            if elapsed < self.interval:
                await asyncio.sleep(self.interval - elapsed)
            self.last_request_time = time.monotonic()


@dataclass
class Provider:
    name: str
    settings: ProviderSettings
    client: OpenAIAsyncOpenAI
    rate_limiter: RateLimiter


def _classify_error(exc: Exception) -> Exception:
    if isinstance(exc, APIStatusError):
        status_code = getattr(exc, "status_code", None)
        if status_code in {400, 401, 402, 403}:
            return LLMNonRetryableError(str(exc))
        return LLMRetryableError(str(exc))
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)):
        return LLMRetryableError(str(exc))
    if isinstance(
        exc,
        (
            AuthenticationError,
            PermissionDeniedError,
            BadRequestError,
            NotFoundError,
            ConflictError,
            UnprocessableEntityError,
        ),
    ):
        return LLMNonRetryableError(str(exc))
    return LLMRetryableError(str(exc))


def _prepare_langfuse_env(settings: LangfuseSettings) -> None:
    if not settings.enabled or not settings.is_configured():
        return
    if settings.host:
        os.environ["LANGFUSE_HOST"] = settings.host
        os.environ["LANGFUSE_BASE_URL"] = settings.host
    if settings.public_key:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.public_key.get_secret_value()
    if settings.secret_key:
        os.environ["LANGFUSE_SECRET_KEY"] = settings.secret_key.get_secret_value()
    os.environ["LANGFUSE_SESSION_NOTE"] = settings.session_note


class LLMClient:
    """LLM client with fallback providers and validation support."""

    _PRIMARY_FAILURES_BEFORE_BACKUP = 3

    def __init__(
        self,
        *,
        weak: ProviderSettings,
        strong: ProviderSettings,
        backup: ProviderSettings | None,
        langfuse: LangfuseSettings,
        failure_patterns: Iterable[str],
    ) -> None:
        _prepare_langfuse_env(langfuse)
        self.failure_patterns = list(failure_patterns)
        self.langfuse = langfuse

        self.providers = {
            "weak": self._build_provider("weak", weak, langfuse),
            "strong": self._build_provider("strong", strong, langfuse),
        }
        if backup:
            self.providers["backup"] = self._build_provider("backup", backup, langfuse)

        self.session_id = (
            time.strftime("%Y-%m-%d_%H-%M", time.gmtime())
            + "_"
            + (langfuse.session_note if langfuse.session_note else "dev")
            + "_"
            + (weak.model or "unknown_model")
        )

    def _build_provider(
        self, name: str, settings: ProviderSettings, langfuse: LangfuseSettings
    ) -> Provider:
        client_cls = LangfuseAsyncOpenAI if langfuse.enabled else OpenAIAsyncOpenAI
        client = client_cls(
            api_key=settings.api_key.get_secret_value(),
            base_url=settings.base_url,
            timeout=settings.timeout_s,
        )
        return Provider(
            name=name, settings=settings, client=client, rate_limiter=RateLimiter(settings.rpm)
        )

    async def _request(
        self,
        provider: Provider,
        *,
        model: str,
        messages: list[ChatCompletionMessageParam],
        temperature: float,
    ) -> str:
        langfuse_context.update_current_trace(session_id=self.session_id)
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(provider.settings.max_retries + 1),
            wait=wait_exponential_jitter(initial=1, max=30),
            retry=retry_if_exception_type(LLMRetryableError),
            reraise=True,
        ):
            with attempt:
                await provider.rate_limiter.wait()
                try:
                    attempt_number = attempt.retry_state.attempt_number
                    max_attempts = provider.settings.max_retries + 1
                    logger.info(
                        "Calling LLM (attempt {attempt}/{max_attempts}): provider={provider} model={model}",
                        attempt=attempt_number,
                        max_attempts=max_attempts,
                        provider=provider.name,
                        model=model,
                    )
                    response = await provider.client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                    )
                except Exception as exc:  # pragma: no cover - exercised via tests with mocks
                    raise _classify_error(exc) from exc

                if not response.choices or not response.choices[0].message:
                    raise LLMRetryableError("Empty response from LLM")

                content = response.choices[0].message.content
                if not content or not content.strip():
                    raise LLMRetryableError("Empty content from LLM")

                return content
        raise LLMRetryableError("Exhausted retries")  # pragma: no cover

    async def _with_fallback(
        self,
        primary: str,
        *,
        messages: list[ChatCompletionMessageParam],
        temperature: float,
        validate: bool = True,
    ) -> str:
        primary_provider = self.providers[primary]
        backup_provider = self.providers.get("backup")
        last_error: Exception | None = None
        for attempt in range(1, self._PRIMARY_FAILURES_BEFORE_BACKUP + 1):
            try:
                logger.debug(
                    f"Calling provider {primary_provider.name} for model {primary_provider.settings.model}"
                )
                result = await self._request(
                    primary_provider,
                    model=primary_provider.settings.model,
                    messages=messages,
                    temperature=temperature,
                )
                if validate and not _is_valid_output(result, self.failure_patterns):
                    raise LLMValidationError("LLM output failed validation")
                return result
            except Exception as exc:  # pragma: no cover - exercised in tests
                last_error = exc
                logger.warning(
                    f"Provider {primary_provider.name} failed (attempt {attempt}/{self._PRIMARY_FAILURES_BEFORE_BACKUP}): {exc}"
                )

        if backup_provider:
            try:
                logger.debug(
                    f"Calling provider {backup_provider.name} for model {backup_provider.settings.model}"
                )
                result = await self._request(
                    backup_provider,
                    model=backup_provider.settings.model,
                    messages=messages,
                    temperature=temperature,
                )
                if validate and not _is_valid_output(result, self.failure_patterns):
                    raise LLMValidationError("LLM output failed validation")
                return result
            except Exception as exc:  # pragma: no cover - exercised in tests
                last_error = exc
                logger.warning(f"Provider {backup_provider.name} failed: {exc}")

        if last_error:
            raise last_error
        raise LLMRetryableError("No providers available")  # pragma: no cover

    @observe()
    async def translate_title(self, title: str, abstract: str) -> str:
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": TRANSLATE_TITLE_SYSTEM_PROMPT},
            {"role": "user", "content": TRANSLATE_TITLE_USER_EXAMPLE},
            {"role": "assistant", "content": TRANSLATE_TITLE_ASSISTANT_EXAMPLE},
            {
                "role": "user",
                "content": f"""# Paper Title:\n```
{title}
```
\n# Abstract:\n```
{abstract}
```
""",
            },
        ]
        return await self._with_fallback("weak", messages=messages, temperature=0.5)

    @observe()
    async def tldr(self, title: str, abstract: str) -> str:
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": TLDR_SYSTEM_PROMPT},
            {"role": "user", "content": TLDR_USER_EXAMPLE},
            {"role": "assistant", "content": TLDR_ASSISTANT_EXAMPLE},
            {
                "role": "user",
                "content": f"""# Paper Title:\n```
{title}
```
\n# Abstract:\n```
{abstract}
```
""",
            },
        ]
        return await self._with_fallback("weak", messages=messages, temperature=0.5)

    @observe()
    async def daily_summary(self, paper_text: str, date_str: str) -> str:
        system_prompt = get_daily_summary_system_prompt(target_date_str=date_str)
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{paper_text}\n{DAILY_SUMMARY_USER_INSTRUCTION}"},
        ]
        return await self._with_fallback("strong", messages=messages, temperature=0.5)


def _is_valid_output(value: str | None, failure_patterns: Iterable[str]) -> bool:
    if not value or not value.strip():
        return False
    lowered = value.lower()
    return all(pattern.lower() not in lowered for pattern in failure_patterns)
