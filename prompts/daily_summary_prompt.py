"""Compatibility wrapper for prompts."""

from daydayarxiv.prompts.daily_summary_prompt import (
    DAILY_SUMMARY_USER_INSTRUCTION,
    get_daily_summary_system_prompt,
)

__all__ = ["get_daily_summary_system_prompt", "DAILY_SUMMARY_USER_INSTRUCTION"]
