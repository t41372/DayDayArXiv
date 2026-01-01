"""Validation helpers for LLM outputs."""

from __future__ import annotations

from collections.abc import Iterable


class LLMValidationError(ValueError):
    """Raised when LLM output fails validation."""


def is_valid_text(value: str | None, failure_patterns: Iterable[str]) -> bool:
    if not value or not value.strip():
        return False
    lowered = value.lower()
    return all(pattern.lower() not in lowered for pattern in failure_patterns)


def require_valid_text(value: str | None, failure_patterns: Iterable[str], field_name: str) -> str:
    if is_valid_text(value, failure_patterns):
        return value.strip()  # type: ignore[return-value]
    raise LLMValidationError(f"Invalid LLM output for {field_name}")
