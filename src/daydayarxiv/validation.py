"""Validation for pipeline outputs to avoid silent failures."""

from __future__ import annotations

from collections.abc import Iterable

from daydayarxiv.llm.validators import is_valid_text
from daydayarxiv.models import DailyData, Paper, TaskStatus


def validate_paper(paper: Paper, failure_patterns: Iterable[str]) -> list[str]:
    issues: list[str] = []
    if paper.processing_status != TaskStatus.COMPLETED:
        issues.append(f"Paper {paper.arxiv_id} not completed")
        return issues
    if not is_valid_text(paper.title_zh, failure_patterns):
        issues.append(f"Paper {paper.arxiv_id} has invalid title_zh")
    if not is_valid_text(paper.tldr_zh, failure_patterns):
        issues.append(f"Paper {paper.arxiv_id} has invalid tldr_zh")
    return issues


def validate_daily_data(data: DailyData, failure_patterns: Iterable[str]) -> list[str]:
    issues: list[str] = []
    if not data.papers:
        if not is_valid_text(data.summary, failure_patterns):
            issues.append("Summary invalid for no-paper day")
        return issues

    if not is_valid_text(data.summary, failure_patterns):
        issues.append("Summary invalid")

    for paper in data.papers:
        issues.extend(validate_paper(paper, failure_patterns))
    return issues
