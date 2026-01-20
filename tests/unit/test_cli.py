import argparse
import sys

import pytest

import daydayarxiv.cli as cli
from daydayarxiv.settings import Settings


class DummyPipeline:
    def __init__(self, *_args, **_kwargs):
        pass

    async def run_for_date(self, *args, **kwargs):
        return True


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
    monkeypatch.setattr(sys, "argv", ["prog"])
    args = cli._parse_args()
    dates = cli._resolve_dates(args)
    assert dates == ["2025-01-01"]


def test_resolve_dates_env_range(monkeypatch):
    monkeypatch.setenv("DDARXIV_START_DATE", "2025-01-01")
    monkeypatch.setenv("DDARXIV_END_DATE", "2025-01-02")
    monkeypatch.setattr(sys, "argv", ["prog"])
    args = cli._parse_args()
    dates = cli._resolve_dates(args)
    assert dates == ["2025-01-01", "2025-01-02"]


def test_resolve_dates_default(monkeypatch):
    monkeypatch.delenv("DDARXIV_DATE", raising=False)
    monkeypatch.delenv("DDARXIV_START_DATE", raising=False)
    monkeypatch.delenv("DDARXIV_END_DATE", raising=False)
    monkeypatch.setattr(sys, "argv", ["prog"])
    args = cli._parse_args()
    dates = cli._resolve_dates(args)
    assert len(dates) == 1


def test_resolve_dates_missing_end_date():
    args = argparse.Namespace(date=None, start_date="2025-01-01", end_date=None)
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


def test_apply_cli_overrides(tmp_path):
    settings = _settings(tmp_path)
    args = argparse.Namespace(
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
