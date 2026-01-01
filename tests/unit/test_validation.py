from daydayarxiv.models import DailyData, Paper, TaskStatus
from daydayarxiv.validation import validate_daily_data


def _paper(status: TaskStatus, title_zh: str = "标题", tldr_zh: str = "摘要") -> Paper:
    return Paper(
        arxiv_id="id",
        title="title",
        title_zh=title_zh,
        authors=["a"],
        abstract="abs",
        tldr_zh=tldr_zh,
        categories=["cs.AI"],
        primary_category="cs.AI",
        comment="",
        pdf_url="https://example.com",
        published_date="2025-01-01 00:00:00 UTC",
        updated_date="2025-01-01 00:00:00 UTC",
        processing_status=status,
    )


def test_validate_daily_data_success():
    data = DailyData(
        date="2025-01-01",
        category="cs.AI",
        summary="Summary",
        papers=[_paper(TaskStatus.COMPLETED)],
        papers_count=1,
    )
    assert validate_daily_data(data, ["翻译失败"]) == []


def test_validate_daily_data_failure_patterns():
    data = DailyData(
        date="2025-01-01",
        category="cs.AI",
        summary="生成失败",
        papers=[_paper(TaskStatus.COMPLETED, title_zh="翻译失败")],
        papers_count=1,
    )
    issues = validate_daily_data(data, ["翻译失败", "生成失败"])
    assert issues


def test_validate_daily_data_invalid_tldr():
    data = DailyData(
        date="2025-01-01",
        category="cs.AI",
        summary="Summary",
        papers=[_paper(TaskStatus.COMPLETED, tldr_zh="翻译失败")],
        papers_count=1,
    )
    issues = validate_daily_data(data, ["翻译失败"])
    assert any("tldr_zh" in issue for issue in issues)


def test_validate_no_papers_summary():
    data = DailyData(
        date="2025-01-01",
        category="cs.AI",
        summary="在 2025-01-01 没有发现 cs.AI 分类下的新论文。",
        papers=[],
        papers_count=0,
    )
    assert validate_daily_data(data, ["翻译失败"]) == []


def test_validate_incomplete_paper():
    data = DailyData(
        date="2025-01-01",
        category="cs.AI",
        summary="Summary",
        papers=[_paper(TaskStatus.PENDING)],
        papers_count=1,
    )
    issues = validate_daily_data(data, ["翻译失败"])
    assert any("not completed" in issue for issue in issues)
