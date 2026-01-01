"""Compatibility wrapper for legacy imports."""

from daydayarxiv.models import DailyData, Paper, RawPaper, TaskStatus

__all__ = ["RawPaper", "Paper", "DailyData", "TaskStatus"]
