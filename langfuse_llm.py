"""Compatibility wrapper for legacy AsyncLLM imports."""

from daydayarxiv.llm.client import LLMClient as AsyncLLM

__all__ = ["AsyncLLM"]
