"""Command-line interface for DayDayArXiv."""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import typer
from dotenv import dotenv_values
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from daydayarxiv.index_refresh import (
    ScanIssue,
    is_valid_date_str,
    load_failure_patterns,
    refresh_data_index,
    resolve_data_dir,
)
from daydayarxiv.llm.client import LLMClient
from daydayarxiv.logging import configure_logging
from daydayarxiv.pipeline import Pipeline
from daydayarxiv.settings import Settings, load_settings
from daydayarxiv.state import StateManager
from daydayarxiv.storage import OutputPaths
from daydayarxiv.utils import (
    build_date_range,
    default_date_list,
    ensure_unique_dates,
    normalize_date_format,
)

app = typer.Typer(add_completion=False, help="DayDayArXiv CLI")
CONSOLE = Console()

RUN_DATE_OPTION = typer.Option(None, help="Single date to process (YYYY-MM-DD)")
RUN_START_DATE_OPTION = typer.Option(None, help="Start date for date range (YYYY-MM-DD)")
RUN_END_DATE_OPTION = typer.Option(None, help="End date for date range (YYYY-MM-DD)")
RUN_CATEGORY_OPTION = typer.Option(None, help="arXiv category (default from settings)")
RUN_MAX_RESULTS_OPTION = typer.Option(None, help="Maximum number of papers to fetch")
RUN_FORCE_OPTION = typer.Option(None, "--force/--no-force", help="Force refresh existing data")
RUN_FAIL_ON_ERROR_OPTION = typer.Option(
    None, "--fail-on-error/--no-fail-on-error", help="Exit non-zero when any date fails"
)
RUN_LOG_LEVEL_OPTION = typer.Option(None, help="Override log level")

REFRESH_DATA_DIR_OPTION = typer.Option(
    None, help="Base data directory containing date folders (default: settings/env)"
)
REFRESH_CATEGORY_OPTION = typer.Option(
    None, help="Restrict to specific categories (repeatable)."
)
REFRESH_NO_CONTENT_VALIDATION_OPTION = typer.Option(
    False, "--no-content-validation", help="Skip summary/content validation checks."
)
REFRESH_DRY_RUN_OPTION = typer.Option(
    False, "--dry-run", help="Do not write index.json; only report findings."
)
REFRESH_FAIL_ON_ISSUES_OPTION = typer.Option(
    False, "--fail-on-issues", help="Exit non-zero if invalid files are found."
)
REFRESH_ALLOW_PARTIAL_OPTION = typer.Option(
    False, "--allow-partial", help="Include partially valid data in index while warning."
)


@dataclass(frozen=True)
class RunConfig:
    dates: list[str]
    category: str
    max_results: int
    force: bool


@dataclass(frozen=True)
class RunArgs:
    date: str | None
    start_date: str | None
    end_date: str | None
    category: str | None
    max_results: int | None
    force: bool | None
    fail_on_error: bool | None
    log_level: str | None


def _resolve_dates(args: RunArgs) -> list[str]:
    env_file = {
        key: value for key, value in dotenv_values(".env").items() if key and value is not None
    }
    env = {**env_file, **os.environ}
    date = args.date or env.get("DDARXIV_DATE")
    start_date = args.start_date or env.get("DDARXIV_START_DATE")
    end_date = args.end_date or env.get("DDARXIV_END_DATE")

    if date:
        return [normalize_date_format(date)]
    if start_date:
        if not end_date:
            raise SystemExit("--end-date is required when using --start-date")
        return build_date_range(start_date, end_date)
    return default_date_list()


def _build_run_config(args: RunArgs, settings: Settings) -> RunConfig:
    dates = ensure_unique_dates(_resolve_dates(args))
    category = args.category or settings.category
    max_results = args.max_results if args.max_results is not None else settings.max_results
    force = args.force if args.force is not None else settings.force
    return RunConfig(dates=dates, category=category, max_results=max_results, force=force)


def _apply_cli_overrides(args: RunArgs, settings: Settings) -> Settings:
    updates: dict[str, object] = {}
    if args.log_level:
        updates["log_level"] = args.log_level
    if args.category:
        updates["category"] = args.category
    if args.max_results is not None:
        updates["max_results"] = args.max_results
    if args.force is not None:
        updates["force"] = args.force
    if args.fail_on_error is not None:
        updates["fail_on_error"] = args.fail_on_error
    if updates:
        return settings.model_copy(update=updates)
    return settings


def _collect_reprocess_targets(issues: list[ScanIssue]) -> list[tuple[str, str]]:
    targets: set[tuple[str, str]] = set()
    for issue in issues:
        path = getattr(issue, "path", None)
        if not isinstance(path, Path):
            continue
        date_str = path.parent.name
        category = path.stem
        if not is_valid_date_str(date_str) or not category:
            continue
        targets.add((date_str, category))
    return sorted(targets)


def _build_issue_table(issues: list[ScanIssue]) -> Table:
    table = Table(title="Detected Issues", show_lines=True)
    table.add_column("Severity", style="bold")
    table.add_column("File", overflow="fold")
    table.add_column("Issue", overflow="fold")
    for issue in issues:
        severity = "HARD" if issue.is_hard else "SOFT"
        style = "red" if issue.is_hard else "yellow"
        table.add_row(severity, issue.path.as_posix(), issue.message, style=style)
    return table


def _build_command_block(targets: list[tuple[str, str]]) -> Text:
    text = Text()
    for index, (date_str, category) in enumerate(targets):
        if index:
            text.append("\n")
        text.append(f"uv run daydayarxiv --date {date_str} --category {category} --force")
    return text


def _run_refresh_index(
    *,
    data_dir: Path | None,
    category: list[str] | None,
    no_content_validation: bool,
    dry_run: bool,
    fail_on_issues: bool,
    allow_partial: bool,
) -> int:
    resolved_dir = resolve_data_dir(data_dir)
    categories_filter = set(category) if category else None
    failure_patterns = load_failure_patterns()
    index, issues = refresh_data_index(
        resolved_dir,
        categories_filter=categories_filter,
        failure_patterns=failure_patterns,
        validate_content=not no_content_validation,
        allow_partial=allow_partial,
        write=not dry_run,
    )

    if issues:
        CONSOLE.print(
            Panel(
                "Some daily data files look incomplete or invalid.",
                title="WARNING",
                border_style="yellow",
            )
        )
        CONSOLE.print(_build_issue_table(issues))
        targets = _collect_reprocess_targets(issues)
        if targets:
            CONSOLE.print(
                Panel(
                    _build_command_block(targets),
                    title="Suggested Reprocess Commands",
                    border_style="cyan",
                )
            )

    if issues and fail_on_issues:
        return 1

    if not dry_run:
        output_path = resolved_dir / "index.json"
        CONSOLE.print(
            f"[green]Index updated:[/green] {output_path.as_posix()} "
            f"({len(index.available_dates)} dates)"
        )
    return 0


def _run_pipeline(args: RunArgs) -> int:
    settings = load_settings()
    settings = _apply_cli_overrides(args, settings)
    configure_logging(settings.log_level, settings.log_dir)

    run_config = _build_run_config(args, settings)
    if len(run_config.dates) == 1:
        logger.info(f"Dates to process: {run_config.dates[0]} (1 day)")
    else:
        logger.info(
            "Date range: "
            f"{run_config.dates[0]} -> {run_config.dates[-1]} "
            f"({len(run_config.dates)} days)"
        )
        logger.info(f"Dates to process: {', '.join(run_config.dates)}")

    llm = LLMClient(
        weak=settings.llm.weak,
        strong=settings.llm.strong,
        backup=settings.llm.backup,
        langfuse=settings.langfuse,
        failure_patterns=settings.failure_patterns,
    )

    state_manager = StateManager(
        OutputPaths(settings.data_dir),
        save_interval_s=settings.state_save_interval_s,
    )
    pipeline = Pipeline(settings, llm, state_manager)

    async def _run() -> int:
        success_count = 0
        total_days = len(run_config.dates)
        for index, date_str in enumerate(run_config.dates, start=1):
            logger.info(f"Processing date {date_str} ({index}/{total_days})")
            try:
                ok = await pipeline.run_for_date(
                    date_str=date_str,
                    category=run_config.category,
                    max_results=run_config.max_results,
                    force=run_config.force,
                )
                if ok:
                    success_count += 1
                else:
                    logger.error(f"Date {date_str} failed; marked for retry")
            except Exception as exc:
                logger.error(f"Error processing {date_str}: {exc}")
            if date_str != run_config.dates[-1]:
                await asyncio.sleep(1)

        if success_count == len(run_config.dates):
            logger.success("All dates processed successfully")
            return 0
        if success_count > 0:
            logger.warning(f"Completed {success_count}/{len(run_config.dates)} dates")
        else:
            logger.error("All dates failed")
        return 1 if settings.fail_on_error else 0

    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return 130


@app.command()
def run(
    date: str | None = RUN_DATE_OPTION,
    start_date: str | None = RUN_START_DATE_OPTION,
    end_date: str | None = RUN_END_DATE_OPTION,
    category: str | None = RUN_CATEGORY_OPTION,
    max_results: int | None = RUN_MAX_RESULTS_OPTION,
    force: bool | None = RUN_FORCE_OPTION,
    fail_on_error: bool | None = RUN_FAIL_ON_ERROR_OPTION,
    log_level: str | None = RUN_LOG_LEVEL_OPTION,
) -> int:
    args = RunArgs(
        date=date,
        start_date=start_date,
        end_date=end_date,
        category=category,
        max_results=max_results,
        force=force,
        fail_on_error=fail_on_error,
        log_level=log_level,
    )
    return _run_pipeline(args)


@app.command("refresh-index")
def refresh_index(
    data_dir: Path | None = REFRESH_DATA_DIR_OPTION,
    category: list[str] | None = REFRESH_CATEGORY_OPTION,
    no_content_validation: bool = REFRESH_NO_CONTENT_VALIDATION_OPTION,
    dry_run: bool = REFRESH_DRY_RUN_OPTION,
    fail_on_issues: bool = REFRESH_FAIL_ON_ISSUES_OPTION,
    allow_partial: bool = REFRESH_ALLOW_PARTIAL_OPTION,
) -> int:
    return _run_refresh_index(
        data_dir=data_dir,
        category=category,
        no_content_validation=no_content_validation,
        dry_run=dry_run,
        fail_on_issues=fail_on_issues,
        allow_partial=allow_partial,
    )


def main() -> int:
    command = typer.main.get_command(app)
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        argv = ["run", *argv]
    result = command.main(args=argv, prog_name="daydayarxiv", standalone_mode=False)
    return result if isinstance(result, int) else 0
