import json
import sys
from pathlib import Path

import pytest

import daydayarxiv.cli as cli
import daydayarxiv.index_refresh as index_refresh
from daydayarxiv.models import DailyData, DailyStatus, Paper, TaskStatus
from daydayarxiv.settings import Settings


class DummyPipeline:
    def __init__(self, *_args, **_kwargs):
        pass

    async def run_for_date(self, *args, **kwargs):
        return True


def _write_daily_data(path: Path, *, date: str, category: str, summary: str = "Summary") -> None:
    paper = Paper(
        arxiv_id="2501.00001v1",
        title="Title",
        title_zh="标题",
        authors=["Alice"],
        abstract="Abstract",
        tldr_zh="摘要",
        categories=[category],
        primary_category=category,
        comment="",
        pdf_url="https://example.com/paper.pdf",
        published_date="2025-01-01 00:00:00 UTC",
        updated_date="2025-01-01 00:00:00 UTC",
        processing_status=TaskStatus.COMPLETED,
    )
    daily = DailyData(
        date=date,
        category=category,
        summary=summary,
        papers=[paper],
        processing_status=DailyStatus.COMPLETED,
        papers_count=1,
        processed_papers_count=1,
        failed_papers_count=0,
        raw_papers_fetched=True,
        summary_generated=True,
        daily_data_saved=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(daily.model_dump(mode="json"), ensure_ascii=False, indent=2)
    path.write_text(payload, encoding="utf-8")


def _settings(tmp_path, *, fail_on_error: bool = False) -> Settings:
    base = {
        "base_url": "https://weak.local",
        "api_key": "key",
        "model": "model",
        "rpm": 1000,
        "max_retries": 0,
    }
    data = {
        "data_dir": tmp_path,
        "log_dir": tmp_path / "logs",
        "category": "cs.AI",
        "fail_on_error": fail_on_error,
        "llm": {
            "weak": base,
            "strong": {**base, "base_url": "https://strong.local"},
            "backup": {**base, "base_url": "https://backup.local"},
        },
        "langfuse": {"enabled": False},
    }
    return Settings.model_validate(data)


def test_resolve_dates_env(monkeypatch):
    monkeypatch.setenv("DDARXIV_DATE", "2025-01-01")
    args = cli.RunArgs(
        date=None,
        start_date=None,
        end_date=None,
        category=None,
        max_results=None,
        force=None,
        fail_on_error=None,
        log_level=None,
    )
    dates = cli._resolve_dates(args)
    assert dates == ["2025-01-01"]


def test_resolve_dates_env_range(monkeypatch):
    monkeypatch.setenv("DDARXIV_START_DATE", "2025-01-01")
    monkeypatch.setenv("DDARXIV_END_DATE", "2025-01-02")
    args = cli.RunArgs(
        date=None,
        start_date=None,
        end_date=None,
        category=None,
        max_results=None,
        force=None,
        fail_on_error=None,
        log_level=None,
    )
    dates = cli._resolve_dates(args)
    assert dates == ["2025-01-01", "2025-01-02"]


def test_resolve_dates_default(monkeypatch):
    monkeypatch.delenv("DDARXIV_DATE", raising=False)
    monkeypatch.delenv("DDARXIV_START_DATE", raising=False)
    monkeypatch.delenv("DDARXIV_END_DATE", raising=False)
    args = cli.RunArgs(
        date=None,
        start_date=None,
        end_date=None,
        category=None,
        max_results=None,
        force=None,
        fail_on_error=None,
        log_level=None,
    )
    dates = cli._resolve_dates(args)
    assert len(dates) == 1


def test_resolve_dates_missing_end_date():
    args = cli.RunArgs(
        date=None,
        start_date="2025-01-01",
        end_date=None,
        category=None,
        max_results=None,
        force=None,
        fail_on_error=None,
        log_level=None,
    )
    with pytest.raises(SystemExit):
        cli._resolve_dates(args)


def test_main_success(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "LLMClient", lambda **_kwargs: object())
    monkeypatch.setattr(cli, "Pipeline", DummyPipeline)

    monkeypatch.setattr(sys, "argv", ["prog", "--date", "2025-01-01"])
    assert cli.main() == 0


def test_main_failure(monkeypatch, tmp_path):
    settings = _settings(tmp_path, fail_on_error=True)

    class FailingPipeline(DummyPipeline):
        async def run_for_date(self, *args, **kwargs):
            return False

    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "LLMClient", lambda **_kwargs: object())
    monkeypatch.setattr(cli, "Pipeline", FailingPipeline)

    monkeypatch.setattr(sys, "argv", ["prog", "--date", "2025-01-01"])
    assert cli.main() == 1


def test_main_exception(monkeypatch, tmp_path):
    settings = _settings(tmp_path, fail_on_error=True)

    class ErrorPipeline(DummyPipeline):
        async def run_for_date(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "LLMClient", lambda **_kwargs: object())
    monkeypatch.setattr(cli, "Pipeline", ErrorPipeline)

    monkeypatch.setattr(sys, "argv", ["prog", "--date", "2025-01-01"])
    assert cli.main() == 1


def test_main_partial_success(monkeypatch, tmp_path):
    settings = _settings(tmp_path, fail_on_error=True)
    call_state = {"count": 0, "slept": 0}

    class PartialPipeline(DummyPipeline):
        async def run_for_date(self, *args, **kwargs):
            call_state["count"] += 1
            return call_state["count"] == 1

    async def _sleep(_seconds: float) -> None:
        call_state["slept"] += 1

    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "LLMClient", lambda **_kwargs: object())
    monkeypatch.setattr(cli, "Pipeline", PartialPipeline)
    monkeypatch.setattr(cli.asyncio, "sleep", _sleep)

    monkeypatch.setattr(
        sys,
        "argv",
        ["prog", "--start-date", "2025-01-01", "--end-date", "2025-01-02"],
    )
    assert cli.main() == 1
    assert call_state["slept"] == 1


def test_main_keyboard_interrupt(monkeypatch, tmp_path):
    settings = _settings(tmp_path)

    def _raise_interrupt(coro):
        coro.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "LLMClient", lambda **_kwargs: object())
    monkeypatch.setattr(cli, "Pipeline", DummyPipeline)
    monkeypatch.setattr(cli.asyncio, "run", _raise_interrupt)

    monkeypatch.setattr(sys, "argv", ["prog", "--date", "2025-01-01"])
    assert cli.main() == 130


def test_main_refresh_index(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "load_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(cli, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "LLMClient", lambda **_kwargs: object())
    monkeypatch.setattr(cli, "Pipeline", DummyPipeline)
    monkeypatch.setattr(index_refresh, "dotenv_values", lambda _path: {})
    monkeypatch.setenv("DDARXIV_FAILURE_PATTERNS", "[]")

    data_dir = tmp_path / "data"
    _write_daily_data(data_dir / "2026-01-10" / "cs.AI.json", date="2026-01-10", category="cs.AI")

    monkeypatch.setattr(sys, "argv", ["prog", "refresh-index", "--data-dir", str(data_dir)])
    assert cli.main() == 0
    assert (data_dir / "index.json").exists()


def test_main_refresh_index_fail_on_issues(monkeypatch, tmp_path):
    monkeypatch.setattr(index_refresh, "dotenv_values", lambda _path: {})
    monkeypatch.setenv("DDARXIV_FAILURE_PATTERNS", "[\"翻译失败\"]")

    data_dir = tmp_path / "data"
    _write_daily_data(
        data_dir / "2026-01-10" / "cs.AI.json",
        date="2026-01-10",
        category="cs.AI",
        summary="翻译失败",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["prog", "refresh-index", "--data-dir", str(data_dir), "--fail-on-issues"],
    )
    assert cli.main() == 1


def test_apply_cli_overrides(tmp_path):
    settings = _settings(tmp_path)
    args = cli.RunArgs(
        log_level="DEBUG",
        category="cs.CL",
        max_results=5,
        force=True,
        fail_on_error=True,
        date=None,
        start_date=None,
        end_date=None,
    )
    updated = cli._apply_cli_overrides(args, settings)
    assert updated.log_level == "DEBUG"
    assert updated.category == "cs.CL"
    assert updated.max_results == 5
    assert updated.force is True
    assert updated.fail_on_error is True


def test_collect_reprocess_targets_filters_invalid():
    class DummyIssue:
        path = "not-a-path"

    issues = [DummyIssue()]
    assert cli._collect_reprocess_targets(issues) == []

    issues = [index_refresh.ScanIssue(Path("bad-date/cs.AI.json"), "bad")]
    assert cli._collect_reprocess_targets(issues) == []


def test_build_command_block_multiline():
    text = cli._build_command_block(
        [("2026-01-10", "cs.AI"), ("2026-01-11", "cs.AI")]
    )
    assert "\n" in text.plain
