from datetime import datetime

import pytest

from daydayarxiv.arxiv_client import ArxivFetchError
from daydayarxiv.llm.client import LLMCallResult
from daydayarxiv.models import DailyData, DailyStatus, Paper, RawPaper, TaskStatus
from daydayarxiv.pipeline import Pipeline, _export_prompt
from daydayarxiv.settings import Settings
from daydayarxiv.state import StateManager
from daydayarxiv.storage import OutputPaths, read_json


class DummyLLM:
    def __init__(self, *, raise_on_paper: bool = False, summary: str = "Summary") -> None:
        self.raise_on_paper = raise_on_paper
        self.summary = summary

    async def translate_title(self, title: str, abstract: str) -> str:
        if self.raise_on_paper:
            raise RuntimeError("LLM error")
        return "标题"

    async def tldr(self, title: str, abstract: str) -> str:
        if self.raise_on_paper:
            raise RuntimeError("LLM error")
        return "摘要"

    async def translate_title_with_meta(self, title: str, abstract: str) -> LLMCallResult:
        if self.raise_on_paper:
            raise RuntimeError("LLM error")
        return LLMCallResult(
            content="标题",
            provider="weak",
            used_backup=False,
            primary_failures=0,
        )

    async def tldr_with_meta(self, title: str, abstract: str) -> LLMCallResult:
        if self.raise_on_paper:
            raise RuntimeError("LLM error")
        return LLMCallResult(
            content="摘要",
            provider="weak",
            used_backup=False,
            primary_failures=0,
        )

    async def daily_summary(self, paper_text: str, date_str: str) -> str:
        return self.summary


class FlakyLLM(DummyLLM):
    def __init__(self) -> None:
        super().__init__()
        self._failed_once = False

    async def translate_title(self, title: str, abstract: str) -> str:
        if not self._failed_once:
            self._failed_once = True
            raise RuntimeError("LLM error")
        return "标题"

    async def translate_title_with_meta(self, title: str, abstract: str) -> LLMCallResult:
        if not self._failed_once:
            self._failed_once = True
            raise RuntimeError("LLM error")
        return LLMCallResult(
            content="标题",
            provider="weak",
            used_backup=False,
            primary_failures=1,
        )


def _settings(tmp_path, *, paper_max_attempts: int = 2) -> Settings:
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
        "concurrency": 2,
        "paper_max_attempts": paper_max_attempts,
        "llm": {
            "weak": base,
            "strong": {**base, "base_url": "https://strong.local"},
            "backup": {**base, "base_url": "https://backup.local"},
        },
        "langfuse": {"enabled": False},
    }
    return Settings.model_validate(data)


def _raw_paper() -> RawPaper:
    return RawPaper(
        arxiv_id="1234.5678v1",
        title="Title",
        authors=["Author"],
        abstract="Abstract",
        categories=["cs.AI"],
        primary_category="cs.AI",
        comment="",
        pdf_url="https://example.com",
        published_date="2025-01-01 00:00:00 UTC",
        updated_date="2025-01-01 00:00:00 UTC",
    )


def _raw_paper_with_title(title: str) -> RawPaper:
    return _raw_paper().model_copy(update={"title": title})


def test_pipeline_helper_no_state(tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(), manager)
    counts = pipeline._paper_status_counts()
    assert counts[TaskStatus.PENDING] == 0
    pipeline._log_progress(1)
    assert pipeline._paper_attempt_info("missing") == (0, 0)
    assert pipeline._paper_index_info("missing") == (0, 0)
    assert pipeline._backup_call_count() == 0


def test_pipeline_helper_missing_paper(tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    manager.load("2025-01-01", "cs.AI")
    pipeline = Pipeline(settings, DummyLLM(), manager)
    assert pipeline._paper_attempt_info("missing") == (0, 0)
    assert pipeline._paper_index_info("missing") == (0, 0)
    manager.register_raw_papers([_raw_paper()], max_attempts=1)
    assert pipeline._paper_index_info("missing") == (0, 1)


def test_pipeline_truncate_title():
    assert Pipeline._truncate_title("") == ""
    short = "short title"
    assert Pipeline._truncate_title(short) == short
    long_title = "x" * 200
    assert Pipeline._truncate_title(long_title, max_len=10) == "xxxxxxx..."


@pytest.mark.asyncio
async def test_pipeline_process_single_paper_logs_empty_title(tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    manager.load("2025-01-01", "cs.AI")
    paper = _raw_paper_with_title("")
    manager.register_raw_papers([paper], max_attempts=1)
    pipeline = Pipeline(settings, DummyLLM(), manager)
    result = await pipeline._process_single_paper(paper)
    assert result is not None


@pytest.mark.asyncio
async def test_pipeline_backup_calls_tracked(tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    manager.load("2025-01-01", "cs.AI")
    paper = _raw_paper()
    manager.register_raw_papers([paper], max_attempts=1)

    class BackupLLM(DummyLLM):
        async def translate_title_with_meta(self, title: str, abstract: str) -> LLMCallResult:
            return LLMCallResult(
                content="标题",
                provider="backup",
                used_backup=True,
                primary_failures=3,
            )

        async def tldr_with_meta(self, title: str, abstract: str) -> LLMCallResult:
            return LLMCallResult(
                content="摘要",
                provider="weak",
                used_backup=False,
                primary_failures=0,
            )

    pipeline = Pipeline(settings, BackupLLM(), manager)
    result = await pipeline._process_single_paper(paper)
    assert result is not None
    assert result.llm_backup_calls == 1
    assert manager.current_state is not None
    assert manager.current_state.llm_backup_calls == 1


@pytest.mark.asyncio
async def test_pipeline_backup_calls_logged_for_date(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))

    class BackupLLM(DummyLLM):
        async def translate_title_with_meta(self, title: str, abstract: str) -> LLMCallResult:
            return LLMCallResult(
                content="标题",
                provider="backup",
                used_backup=True,
                primary_failures=3,
            )

        async def tldr_with_meta(self, title: str, abstract: str) -> LLMCallResult:
            return LLMCallResult(
                content="摘要",
                provider="weak",
                used_backup=False,
                primary_failures=0,
            )

    async def _fetch(*_args, **_kwargs):
        return [_raw_paper()]

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    pipeline = Pipeline(settings, BackupLLM(), manager)
    ok = await pipeline.run_for_date(
        date_str="2025-01-01",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is True
    assert manager.current_state is not None
    assert manager.current_state.llm_backup_calls == 1


@pytest.mark.asyncio
async def test_pipeline_no_papers(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        return []

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-01",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_pipeline_fetch_failure_marks_failed(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        raise ArxivFetchError("boom")

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-01",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is False
    output = read_json(OutputPaths(settings.data_dir).daily_path("2025-01-01", "cs.AI"))
    assert output["processing_status"] == "failed"
    assert output["daily_data_saved"] is False


@pytest.mark.asyncio
async def test_pipeline_no_papers_index_failure(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        return []

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    def _raise_index(*_args, **_kwargs):
        raise RuntimeError("index error")

    monkeypatch.setattr("daydayarxiv.pipeline.update_data_index", _raise_index)

    ok = await pipeline.run_for_date(
        date_str="2025-01-01",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is False


def test_export_prompt_includes_fields():
    paper = _raw_paper().model_copy(update={"comment": "Note"})
    prompt = _export_prompt([paper])
    assert "authors:" in prompt
    assert "published date:" in prompt
    assert "abstract" in prompt
    assert "comment" in prompt


@pytest.mark.asyncio
async def test_pipeline_force_resets(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        return []

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-02",
        category="cs.AI",
        max_results=10,
        force=True,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_pipeline_incomplete_existing(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    output_paths = OutputPaths(settings.data_dir)
    daily = DailyData(
        date="2025-01-01",
        category="cs.AI",
        summary="生成失败",
        papers=[],
        papers_count=0,
        summary_generated=True,
        daily_data_saved=True,
        last_update=datetime.now(),
    )
    output_paths.ensure_dir("2025-01-01")
    from daydayarxiv.storage import write_json_atomic

    write_json_atomic(output_paths.daily_path("2025-01-01", "cs.AI"), daily.model_dump(mode="json"))

    manager = StateManager(output_paths)
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        return []

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-01",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_pipeline_failed_papers(monkeypatch, tmp_path):
    settings = _settings(tmp_path, paper_max_attempts=1)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(raise_on_paper=True), manager)

    async def _fetch(*_args, **_kwargs):
        return [_raw_paper()]

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-03",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_pipeline_incomplete_processing(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        return [_raw_paper()]

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)
    monkeypatch.setattr(Pipeline, "_process_papers", _noop)

    ok = await pipeline.run_for_date(
        date_str="2025-01-07",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_pipeline_retries_within_run(monkeypatch, tmp_path):
    settings = _settings(tmp_path, paper_max_attempts=2)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, FlakyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        return [_raw_paper()]

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-06",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is True
    output = read_json(OutputPaths(settings.data_dir).daily_path("2025-01-06", "cs.AI"))
    assert output["papers"][0]["attempts"] == 2


@pytest.mark.asyncio
async def test_pipeline_loads_existing_raw(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    output_paths = OutputPaths(settings.data_dir)
    manager = StateManager(output_paths)
    pipeline = Pipeline(settings, DummyLLM(), manager)

    raw_path = output_paths.raw_path("2025-01-04", "cs.AI")
    from daydayarxiv.storage import write_json_atomic

    write_json_atomic(raw_path, [_raw_paper().model_dump(mode="json")])

    async def _fetch(*_args, **_kwargs):
        raise AssertionError("fetch_papers should not be called")

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-04",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is True
    output = read_json(output_paths.daily_path("2025-01-04", "cs.AI"))
    assert output["papers"][0]["title_zh"] == "标题"


@pytest.mark.asyncio
async def test_pipeline_refetch_on_bad_raw(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    output_paths = OutputPaths(settings.data_dir)
    manager = StateManager(output_paths)
    pipeline = Pipeline(settings, DummyLLM(), manager)

    raw_path = output_paths.raw_path("2025-01-05", "cs.AI")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("not-json", encoding="utf-8")

    called = {"count": 0}

    async def _fetch(*_args, **_kwargs):
        called["count"] += 1
        return [_raw_paper()]

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-05",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is True
    assert called["count"] == 1


@pytest.mark.asyncio
async def test_pipeline_success(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        return [_raw_paper()]

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-01",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is True
    output = read_json(OutputPaths(settings.data_dir).daily_path("2025-01-01", "cs.AI"))
    assert output["papers"][0]["title_zh"] == "标题"


@pytest.mark.asyncio
async def test_pipeline_index_update_failure(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        return [_raw_paper()]

    def _raise_index(*_args, **_kwargs):
        raise RuntimeError("index error")

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)
    monkeypatch.setattr("daydayarxiv.pipeline.update_data_index", _raise_index)

    ok = await pipeline.run_for_date(
        date_str="2025-01-08",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_pipeline_failure_on_llm(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(raise_on_paper=True), manager)

    async def _fetch(*_args, **_kwargs):
        return [_raw_paper()]

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-01",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_pipeline_invalid_summary(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(summary="生成失败"), manager)

    async def _fetch(*_args, **_kwargs):
        return [_raw_paper()]

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-01",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_pipeline_skip_existing(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    output_paths = OutputPaths(settings.data_dir)
    daily = DailyData(
        date="2025-01-01",
        category="cs.AI",
        summary="Summary",
        papers=[
            Paper(
                arxiv_id="id",
                title="Title",
                title_zh="标题",
                authors=["Author"],
                abstract="Abstract",
                tldr_zh="摘要",
                categories=["cs.AI"],
                primary_category="cs.AI",
                comment="",
                pdf_url="https://example.com",
                published_date="2025-01-01 00:00:00 UTC",
                updated_date="2025-01-01 00:00:00 UTC",
                processing_status=TaskStatus.COMPLETED,
            )
        ],
        papers_count=1,
        summary_generated=True,
        daily_data_saved=True,
        processing_status=DailyStatus.COMPLETED,
        last_update=datetime.now(),
    )
    output_paths.ensure_dir("2025-01-01")
    from daydayarxiv.storage import write_json_atomic

    write_json_atomic(output_paths.daily_path("2025-01-01", "cs.AI"), daily.model_dump(mode="json"))

    manager = StateManager(output_paths)
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        raise AssertionError("fetch_papers should not be called")

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-01",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_pipeline_existing_complete_index_update_failure(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    output_paths = OutputPaths(settings.data_dir)
    daily = DailyData(
        date="2025-01-02",
        category="cs.AI",
        summary="Summary",
        papers=[
            Paper(
                arxiv_id="id",
                title="Title",
                title_zh="标题",
                authors=["Author"],
                abstract="Abstract",
                tldr_zh="摘要",
                categories=["cs.AI"],
                primary_category="cs.AI",
                comment="",
                pdf_url="https://example.com",
                published_date="2025-01-02 00:00:00 UTC",
                updated_date="2025-01-02 00:00:00 UTC",
                processing_status=TaskStatus.COMPLETED,
            )
        ],
        papers_count=1,
        summary_generated=True,
        daily_data_saved=True,
        last_update=datetime.now(),
    )
    output_paths.ensure_dir("2025-01-02")
    from daydayarxiv.storage import write_json_atomic

    write_json_atomic(output_paths.daily_path("2025-01-02", "cs.AI"), daily.model_dump(mode="json"))

    manager = StateManager(output_paths)
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        raise AssertionError("fetch_papers should not be called")

    def _raise_index(*_args, **_kwargs):
        raise RuntimeError("index error")

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)
    monkeypatch.setattr("daydayarxiv.pipeline.update_data_index", _raise_index)

    ok = await pipeline.run_for_date(
        date_str="2025-01-02",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is False
    output = read_json(output_paths.daily_path("2025-01-02", "cs.AI"))
    assert output["processing_status"] == "failed"


@pytest.mark.asyncio
async def test_pipeline_existing_complete_marks_success(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    output_paths = OutputPaths(settings.data_dir)
    daily = DailyData(
        date="2025-01-02",
        category="cs.AI",
        summary="Summary",
        papers=[
            Paper(
                arxiv_id="id",
                title="Title",
                title_zh="标题",
                authors=["Author"],
                abstract="Abstract",
                tldr_zh="摘要",
                categories=["cs.AI"],
                primary_category="cs.AI",
                comment="",
                pdf_url="https://example.com",
                published_date="2025-01-02 00:00:00 UTC",
                updated_date="2025-01-02 00:00:00 UTC",
                processing_status=TaskStatus.COMPLETED,
            )
        ],
        papers_count=1,
        summary_generated=True,
        daily_data_saved=True,
        last_update=datetime.now(),
    )
    output_paths.ensure_dir("2025-01-02")
    from daydayarxiv.storage import write_json_atomic

    write_json_atomic(output_paths.daily_path("2025-01-02", "cs.AI"), daily.model_dump(mode="json"))

    manager = StateManager(output_paths)
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        raise AssertionError("fetch_papers should not be called")

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-02",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is True
    output = read_json(output_paths.daily_path("2025-01-02", "cs.AI"))
    assert output["processing_status"] == "completed"


@pytest.mark.asyncio
async def test_pipeline_resets_failed_papers(monkeypatch, tmp_path):
    settings = _settings(tmp_path, paper_max_attempts=1)
    output_paths = OutputPaths(settings.data_dir)
    daily = DailyData(
        date="2025-01-03",
        category="cs.AI",
        summary="",
        papers=[
            Paper(
                arxiv_id="id",
                title="Title",
                title_zh="",
                authors=["Author"],
                abstract="Abstract",
                tldr_zh="",
                categories=["cs.AI"],
                primary_category="cs.AI",
                comment="",
                pdf_url="https://example.com",
                published_date="2025-01-03 00:00:00 UTC",
                updated_date="2025-01-03 00:00:00 UTC",
                processing_status=TaskStatus.FAILED,
                attempts=1,
                max_attempts=1,
            )
        ],
        papers_count=1,
        summary_generated=False,
        daily_data_saved=False,
        last_update=datetime.now(),
    )
    output_paths.ensure_dir("2025-01-03")
    from daydayarxiv.storage import write_json_atomic

    write_json_atomic(output_paths.daily_path("2025-01-03", "cs.AI"), daily.model_dump(mode="json"))

    manager = StateManager(output_paths)
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        return []

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)

    ok = await pipeline.run_for_date(
        date_str="2025-01-03",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_pipeline_load_raw_exception(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _raise(*_args, **_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(Pipeline, "_load_or_fetch_raw", _raise)

    ok = await pipeline.run_for_date(
        date_str="2025-01-04",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_pipeline_process_exception(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        return [_raw_paper()]

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)
    monkeypatch.setattr(Pipeline, "_process_papers", _raise)

    ok = await pipeline.run_for_date(
        date_str="2025-01-05",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_pipeline_summary_exception(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    manager = StateManager(OutputPaths(settings.data_dir))
    pipeline = Pipeline(settings, DummyLLM(), manager)

    async def _fetch(*_args, **_kwargs):
        return [_raw_paper()]

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("daydayarxiv.pipeline.fetch_papers", _fetch)
    monkeypatch.setattr(Pipeline, "_generate_summary", _raise)

    ok = await pipeline.run_for_date(
        date_str="2025-01-06",
        category="cs.AI",
        max_results=10,
        force=False,
    )
    assert ok is False
