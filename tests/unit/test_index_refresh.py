import json
from pathlib import Path

import pytest

from daydayarxiv import index_refresh
from daydayarxiv.models import DailyData, DailyStatus, Paper, TaskStatus


def _make_paper(
    *,
    arxiv_id: str = "2501.00001v1",
    status: TaskStatus = TaskStatus.COMPLETED,
) -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title="Title",
        title_zh="标题",
        authors=["Alice"],
        abstract="Abstract",
        tldr_zh="摘要",
        categories=["cs.AI"],
        primary_category="cs.AI",
        comment="",
        pdf_url="https://example.com/paper.pdf",
        published_date="2025-01-01 00:00:00 UTC",
        updated_date="2025-01-01 00:00:00 UTC",
        processing_status=status,
        attempts=1,
        max_attempts=3,
        completed_steps=["translation", "tldr"],
    )


def _make_daily(
    *,
    date: str,
    category: str,
    summary: str = "Summary",
    papers: list[Paper] | None = None,
    status: DailyStatus = DailyStatus.COMPLETED,
    papers_count: int | None = None,
    processed_papers_count: int | None = None,
    failed_papers_count: int = 0,
) -> DailyData:
    if papers is None:
        papers = [_make_paper()]
    count = papers_count if papers_count is not None else len(papers)
    processed = (
        processed_papers_count if processed_papers_count is not None else len(papers)
    )
    return DailyData(
        date=date,
        category=category,
        summary=summary,
        papers=papers,
        processing_status=status,
        raw_papers_fetched=True,
        papers_count=count,
        processed_papers_count=processed,
        failed_papers_count=failed_papers_count,
        summary_generated=True,
        daily_data_saved=True,
    )


def _write_daily(path: Path, daily: DailyData) -> None:
    payload = json.dumps(daily.model_dump(mode="json"), ensure_ascii=False, indent=2)
    path.write_text(payload, encoding="utf-8")


def test_load_failure_patterns_default(monkeypatch):
    monkeypatch.setattr(index_refresh, "dotenv_values", lambda _path: {})
    monkeypatch.delenv("DDARXIV_FAILURE_PATTERNS", raising=False)
    assert index_refresh.load_failure_patterns() == list(index_refresh.DEFAULT_FAILURE_PATTERNS)


def test_load_failure_patterns_json(monkeypatch):
    monkeypatch.setattr(index_refresh, "dotenv_values", lambda _path: {})
    monkeypatch.setenv("DDARXIV_FAILURE_PATTERNS", "[\"a\", \"b\"]")
    assert index_refresh.load_failure_patterns() == ["a", "b"]


def test_load_failure_patterns_csv(monkeypatch):
    monkeypatch.setattr(index_refresh, "dotenv_values", lambda _path: {})
    monkeypatch.setenv("DDARXIV_FAILURE_PATTERNS", "x, y")
    assert index_refresh.load_failure_patterns() == ["x", "y"]


def test_resolve_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(index_refresh, "dotenv_values", lambda _path: {})
    monkeypatch.setenv("DDARXIV_DATA_DIR", str(tmp_path))
    assert index_refresh.resolve_data_dir(None) == tmp_path
    assert index_refresh.resolve_data_dir(Path("custom")) == Path("custom")
    monkeypatch.delenv("DDARXIV_DATA_DIR", raising=False)
    assert index_refresh.resolve_data_dir(None) == index_refresh.DEFAULT_DATA_DIR


def test_is_valid_date_str():
    assert index_refresh.is_valid_date_str("2026-01-10") is True
    assert index_refresh.is_valid_date_str("bad") is False
    assert index_refresh.is_valid_date_str("2026-99-99") is False


def test_validate_daily_file_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{broken", encoding="utf-8")
    result = index_refresh.validate_daily_file(
        path,
        "2026-01-10",
        "cs.AI",
        failure_patterns=[],
        validate_content=True,
    )
    assert result.issues
    assert "invalid JSON" in result.issues[0]
    assert result.hard_failure is True


def test_validate_daily_file_mismatch_and_counts(tmp_path):
    daily = _make_daily(
        date="2026-01-09",
        category="cs.CL",
        summary="翻译失败",
        status=DailyStatus.IN_PROGRESS,
        papers=[_make_paper(status=TaskStatus.PENDING)],
        papers_count=2,
        processed_papers_count=-1,
        failed_papers_count=0,
    )
    path = tmp_path / "cs.AI.json"
    _write_daily(path, daily)
    result = index_refresh.validate_daily_file(
        path,
        "2026-01-10",
        "cs.AI",
        failure_patterns=["翻译失败"],
        validate_content=True,
    )
    assert len(result.issues) >= 6
    assert result.hard_failure is True


def test_rebuild_index_with_filters_and_invalid_dates(tmp_path):
    base_dir = tmp_path / "data"
    valid_dir = base_dir / "2026-01-10"
    valid_dir.mkdir(parents=True)
    _write_daily(valid_dir / "cs.AI.json", _make_daily(date="2026-01-10", category="cs.AI"))
    _write_daily(valid_dir / "cs.CL.json", _make_daily(date="2026-01-10", category="cs.CL"))
    (valid_dir / "cs.AI_raw.json").write_text("{}", encoding="utf-8")

    (base_dir / "bad").mkdir()
    (base_dir / "2026-99-99").mkdir()
    (base_dir / "note.txt").write_text("x", encoding="utf-8")

    index, issues = index_refresh.rebuild_index(
        base_dir,
        categories_filter={"cs.AI"},
        failure_patterns=[],
        validate_content=True,
        allow_partial=False,
    )
    assert issues == []
    assert index.available_dates == ["2026-01-10"]
    assert index.categories == ["cs.AI"]
    assert index.by_date == {"2026-01-10": ["cs.AI"]}


def test_rebuild_index_allow_partial(tmp_path):
    base_dir = tmp_path / "data"
    date_dir = base_dir / "2026-01-10"
    date_dir.mkdir(parents=True)
    daily = _make_daily(
        date="2026-01-10",
        category="cs.AI",
        summary="翻译失败",
        status=DailyStatus.IN_PROGRESS,
        papers=[_make_paper(status=TaskStatus.PENDING)],
        papers_count=1,
        processed_papers_count=0,
        failed_papers_count=0,
    )
    _write_daily(date_dir / "cs.AI.json", daily)

    index, issues = index_refresh.rebuild_index(
        base_dir,
        categories_filter=None,
        failure_patterns=["翻译失败"],
        validate_content=True,
        allow_partial=False,
    )
    assert issues
    assert index.available_dates == []

    index_partial, issues_partial = index_refresh.rebuild_index(
        base_dir,
        categories_filter=None,
        failure_patterns=["翻译失败"],
        validate_content=True,
        allow_partial=True,
    )
    assert issues_partial
    assert index_partial.available_dates == ["2026-01-10"]


def test_rebuild_index_missing_dir(tmp_path):
    missing = tmp_path / "missing"
    index, issues = index_refresh.rebuild_index(
        missing,
        categories_filter=None,
        failure_patterns=[],
        validate_content=False,
        allow_partial=False,
    )
    assert index.available_dates == []
    assert issues == []


def test_refresh_data_index_writes(tmp_path):
    base_dir = tmp_path / "data"
    date_dir = base_dir / "2026-01-10"
    date_dir.mkdir(parents=True)
    _write_daily(date_dir / "cs.AI.json", _make_daily(date="2026-01-10", category="cs.AI"))

    index, issues = index_refresh.refresh_data_index(
        base_dir,
        categories_filter=None,
        failure_patterns=[],
        validate_content=True,
        allow_partial=False,
        write=True,
    )
    assert issues == []
    assert (base_dir / "index.json").exists()
    assert index.available_dates == ["2026-01-10"]


def test_refresh_data_index_dry_run(tmp_path):
    base_dir = tmp_path / "data"
    date_dir = base_dir / "2026-01-10"
    date_dir.mkdir(parents=True)
    _write_daily(date_dir / "cs.AI.json", _make_daily(date="2026-01-10", category="cs.AI"))

    index, issues = index_refresh.refresh_data_index(
        base_dir,
        categories_filter=None,
        failure_patterns=[],
        validate_content=True,
        allow_partial=False,
        write=False,
    )
    assert issues == []
    assert index.available_dates == ["2026-01-10"]
    assert not (base_dir / "index.json").exists()


def test_render_issue_report():
    assert index_refresh.render_issue_report([]) == ""
    issues = [index_refresh.ScanIssue(Path("a"), "bad")]
    report = index_refresh.render_issue_report(issues)
    assert "Found 1 issues" in report
    assert "a" in report
