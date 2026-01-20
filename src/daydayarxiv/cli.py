"""Command-line interface for DayDayArXiv."""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass

from loguru import logger
from dotenv import dotenv_values

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


@dataclass(frozen=True)
class RunConfig:
    dates: list[str]
    category: str
    max_results: int
    force: bool


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and process arXiv papers")
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument("--date", type=str, help="Single date to process (YYYY-MM-DD)")
    date_group.add_argument("--start-date", type=str, help="Start date for date range (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date for date range (YYYY-MM-DD)")

    parser.add_argument("--category", type=str, help="arXiv category (default from settings)")
    parser.add_argument("--max-results", type=int, help="Maximum number of papers to fetch")
    parser.add_argument(
        "--force",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Force refresh existing data",
    )
    parser.add_argument(
        "--fail-on-error",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Exit non-zero when any date fails",
    )
    parser.add_argument("--log-level", type=str, help="Override log level")

    return parser.parse_args()


def _resolve_dates(args: argparse.Namespace) -> list[str]:
    env_file = {key: value for key, value in dotenv_values(".env").items() if key and value is not None}
    env = {**env_file, **os.environ}
    env_date = env.get("DDARXIV_DATE")
    env_start = env.get("DDARXIV_START_DATE")
    env_end = env.get("DDARXIV_END_DATE")

    if not args.date and env_date:
        args.date = env_date
    if not args.start_date and env_start:
        args.start_date = env_start
    if not args.end_date and env_end:
        args.end_date = env_end

    if args.date:
        return [normalize_date_format(args.date)]
    if args.start_date:
        if not args.end_date:
            raise SystemExit("--end-date is required when using --start-date")
        return build_date_range(args.start_date, args.end_date)
    return default_date_list()


def _build_run_config(args: argparse.Namespace, settings: Settings) -> RunConfig:
    dates = ensure_unique_dates(_resolve_dates(args))
    category = args.category or settings.category
    max_results = args.max_results if args.max_results is not None else settings.max_results
    force = args.force if args.force is not None else settings.force
    return RunConfig(dates=dates, category=category, max_results=max_results, force=force)


def _apply_cli_overrides(args: argparse.Namespace, settings: Settings) -> Settings:
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


def main() -> int:
    args = _parse_args()
    settings = load_settings()
    settings = _apply_cli_overrides(args, settings)
    configure_logging(settings.log_level, settings.log_dir)

    run_config = _build_run_config(args, settings)
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
        for date_str in run_config.dates:
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
