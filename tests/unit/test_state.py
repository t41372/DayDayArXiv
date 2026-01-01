from daydayarxiv.models import RawPaper, TaskStatus
from daydayarxiv.state import StateManager
from daydayarxiv.storage import OutputPaths


def _raw_paper(arxiv_id: str) -> RawPaper:
    return RawPaper(
        arxiv_id=arxiv_id,
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


def test_state_lifecycle(tmp_path):
    paths = OutputPaths(tmp_path)
    manager = StateManager(paths)
    state = manager.load("2025-01-01", "cs.AI")
    assert state.date == "2025-01-01"

    manager.register_raw_papers([_raw_paper("id1"), _raw_paper("id2")], max_attempts=2)
    assert manager.current_state is not None
    assert manager.current_state.papers_count == 2

    manager.update_paper("id1", status=TaskStatus.IN_PROGRESS)
    paper = next(p for p in manager.current_state.papers if p.arxiv_id == "id1")
    assert paper.attempts == 1

    manager.update_paper("id1", status=TaskStatus.FAILED)
    pending = manager.pending_paper_ids()
    assert "id1" in pending

    manager.update_paper("id1", status=TaskStatus.IN_PROGRESS)
    manager.update_paper("id1", status=TaskStatus.FAILED)
    manager.update_paper("id1", status=TaskStatus.IN_PROGRESS)
    manager.update_paper("id1", status=TaskStatus.FAILED)

    failed = manager.failed_papers()
    assert any(p.arxiv_id == "id1" for p in failed)


def test_state_reset(tmp_path):
    paths = OutputPaths(tmp_path)
    manager = StateManager(paths)
    manager.load("2025-01-01", "cs.AI")
    manager.reset("2025-01-02", "cs.AI")
    assert manager.current_state is not None
    assert manager.current_state.date == "2025-01-02"


def test_state_no_current_state(tmp_path):
    manager = StateManager(OutputPaths(tmp_path))
    manager.save()
    manager.register_raw_papers([_raw_paper("id1")], max_attempts=1)
    manager.update_paper("id1", status=TaskStatus.COMPLETED)
    assert manager.pending_paper_ids() == []
    assert manager.completed_papers() == []
    assert manager.failed_papers() == []
    manager._recalculate_counts()


def test_state_update_placeholder(tmp_path):
    manager = StateManager(OutputPaths(tmp_path))
    manager.load("2025-01-01", "cs.AI")
    manager.update_paper("missing", status=TaskStatus.IN_PROGRESS, step_completed="translation")
    assert manager.current_state is not None
    paper = next(p for p in manager.current_state.papers if p.arxiv_id == "missing")
    assert "translation" in paper.completed_steps


def test_state_register_skips_duplicates(tmp_path):
    manager = StateManager(OutputPaths(tmp_path))
    manager.load("2025-01-01", "cs.AI")
    raw = _raw_paper("id1")
    manager.register_raw_papers([raw, raw], max_attempts=1)
    manager.register_raw_papers([raw], max_attempts=1)
    assert manager.current_state is not None
    assert len(manager.current_state.papers) == 1
