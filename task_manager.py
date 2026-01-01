"""Compatibility wrapper for legacy imports."""

from daydayarxiv.state import StateManager as TaskManager
from daydayarxiv.models import DailyData, Paper, TaskStatus

__all__ = ["TaskManager", "DailyData", "Paper", "TaskStatus"]
