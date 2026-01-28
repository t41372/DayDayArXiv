"""Refresh the frontend data index by scanning validated daily data files."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from dotenv import dotenv_values

from daydayarxiv.models import DailyData, DailyStatus, DataIndex
from daydayarxiv.storage import write_json_atomic
from daydayarxiv.validation import validate_daily_data

ENV_PREFIX = "DDARXIV_"
DEFAULT_DATA_DIR = Path("daydayarxiv_frontend/public/data")
DEFAULT_FAILURE_PATTERNS = ("翻译失败", "生成失败", "快报生成失败")


@dataclass(frozen=True)
class ScanIssue:
    path: Path
    message: str
    is_hard: bool = False


@dataclass(frozen=True)
class ValidationResult:
    issues: list[str]
    hard_failure: bool


def _load_env() -> dict[str, str]:
    env_file = Path(".env")
    env = {**dotenv_values(env_file), **os.environ}
    return {key: value for key, value in env.items() if key and value is not None}


def load_failure_patterns() -> list[str]:
    env = _load_env()
    raw = env.get(f"{ENV_PREFIX}FAILURE_PATTERNS")
    if not raw:
        return list(DEFAULT_FAILURE_PATTERNS)

    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in raw.split(",") if item.strip()]

    if isinstance(parsed, list):
        cleaned = [str(item).strip() for item in cast(list[object], parsed)]
        cleaned = [item for item in cleaned if item]
        if cleaned:
            return cleaned
    return list(DEFAULT_FAILURE_PATTERNS)


def resolve_data_dir(cli_value: Path | None) -> Path:
    if cli_value is not None:
        return cli_value
    env = _load_env()
    raw = env.get(f"{ENV_PREFIX}DATA_DIR")
    return Path(raw) if raw else DEFAULT_DATA_DIR


def is_valid_date_str(date_str: str) -> bool:
    if len(date_str) != 10:
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def load_daily_data(path: Path) -> DailyData:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return DailyData.model_validate(raw)


def validate_daily_file(
    path: Path,
    date_str: str,
    category: str,
    *,
    failure_patterns: Iterable[str],
    validate_content: bool,
) -> ValidationResult:
    issues: list[str] = []
    hard_failure = False
    try:
        daily = load_daily_data(path)
    except Exception as exc:
        return ValidationResult([f"invalid JSON or schema: {exc}"], True)

    if daily.date != date_str:
        issues.append(f"date mismatch: {daily.date} != {date_str}")
        hard_failure = True
    if daily.category != category:
        issues.append(f"category mismatch: {daily.category} != {category}")
        hard_failure = True
    if daily.papers_count < 0 or daily.processed_papers_count < 0 or daily.failed_papers_count < 0:
        issues.append("paper counts must be non-negative")
    if daily.processing_status not in {DailyStatus.COMPLETED, DailyStatus.NO_PAPERS}:
        issues.append(f"processing_status not final: {daily.processing_status}")

    if validate_content:
        issues.extend(validate_daily_data(daily, failure_patterns))

    return ValidationResult(issues, hard_failure)


def rebuild_index(
    base_dir: Path,
    *,
    categories_filter: set[str] | None,
    failure_patterns: Iterable[str],
    validate_content: bool,
    allow_partial: bool,
) -> tuple[DataIndex, list[ScanIssue]]:
    index = DataIndex()
    issues: list[ScanIssue] = []

    if not base_dir.exists():
        return index, issues

    for date_dir in sorted(base_dir.iterdir()):
        if not date_dir.is_dir():
            continue
        date_str = date_dir.name
        if not is_valid_date_str(date_str):
            continue

        date_categories: list[str] = []
        for data_file in sorted(date_dir.glob("*.json")):
            if data_file.name.endswith("_raw.json"):
                continue
            category = data_file.stem
            if categories_filter and category not in categories_filter:
                continue

            result = validate_daily_file(
                data_file,
                date_str,
                category,
                failure_patterns=failure_patterns,
                validate_content=validate_content,
            )
            if result.issues:
                for message in result.issues:
                    issues.append(ScanIssue(data_file, message, is_hard=result.hard_failure))
                if result.hard_failure or not allow_partial:
                    continue

            date_categories.append(category)

        if date_categories:
            index.available_dates.append(date_str)
            index.by_date[date_str] = sorted(set(date_categories))
            for category in date_categories:
                if category not in index.categories:
                    index.categories.append(category)

    index.available_dates.sort()
    index.categories.sort()
    index.last_updated = datetime.now(UTC)
    return index, issues


def refresh_data_index(
    base_dir: Path,
    *,
    categories_filter: set[str] | None,
    failure_patterns: Iterable[str],
    validate_content: bool,
    allow_partial: bool,
    write: bool = True,
) -> tuple[DataIndex, list[ScanIssue]]:
    index, issues = rebuild_index(
        base_dir,
        categories_filter=categories_filter,
        failure_patterns=failure_patterns,
        validate_content=validate_content,
        allow_partial=allow_partial,
    )
    if write:
        write_json_atomic(base_dir / "index.json", index.model_dump(mode="json"))
    return index, issues


def render_issue_report(issues: list[ScanIssue]) -> str:
    if not issues:
        return ""

    lines = [f"Found {len(issues)} issues:"]
    for issue in issues:
        lines.append(f"- {issue.path.as_posix()}: {issue.message}")
    return "\n".join(lines)
