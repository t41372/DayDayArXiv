"""Pipeline state management stored alongside output JSON."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from loguru import logger

from daydayarxiv.models import DailyData, Paper, RawPaper, TaskStatus
from daydayarxiv.storage import OutputPaths, read_json, write_json_atomic


class StateManager:
    """Manage pipeline state persisted in the output JSON file."""

    def __init__(self, paths: OutputPaths) -> None:
        self.paths = paths
        self.current_state: DailyData | None = None

    def load(self, date: str, category: str) -> DailyData:
        output_file = self.paths.daily_path(date, category)
        if output_file.exists():
            try:
                data = read_json(output_file)
                state = DailyData.model_validate(data)
                self.current_state = state
                logger.info(f"Loaded pipeline state from {output_file}")
                return state
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(f"Failed to load state from {output_file}: {exc}")

        logger.info(f"Creating new pipeline state for {date}, {category}")
        state = DailyData(
            date=date,
            category=category,
            summary="",
            papers=[],
            last_update=datetime.now(),
        )
        self.current_state = state
        self.save()
        return state

    def reset(self, date: str, category: str) -> DailyData:
        """Force a new state, overwriting existing output file on next save."""
        state = DailyData(
            date=date,
            category=category,
            summary="",
            papers=[],
            last_update=datetime.now(),
        )
        self.current_state = state
        self.save()
        return state

    def save(self) -> None:
        if not self.current_state:
            logger.error("No state to save")
            return

        self.current_state.last_update = datetime.now()
        self._recalculate_counts()
        output_file = self.paths.daily_path(self.current_state.date, self.current_state.category)
        write_json_atomic(output_file, self.current_state.model_dump(mode="json"))

    def register_raw_papers(self, raw_papers: Iterable[RawPaper], max_attempts: int) -> None:
        if not self.current_state:
            logger.error("No current state")
            return

        for raw in raw_papers:
            existing = next((p for p in self.current_state.papers if p.arxiv_id == raw.arxiv_id), None)
            if existing:
                continue
            paper = Paper(
                arxiv_id=raw.arxiv_id,
                title=raw.title,
                title_zh="",
                authors=raw.authors,
                abstract=raw.abstract,
                tldr_zh="",
                categories=raw.categories,
                primary_category=raw.primary_category,
                comment=raw.comment,
                pdf_url=raw.pdf_url or f"https://arxiv.org/pdf/{raw.arxiv_id}",
                published_date=raw.published_date,
                updated_date=raw.updated_date,
                processing_status=TaskStatus.PENDING,
                attempts=0,
                max_attempts=max_attempts,
                last_update=datetime.now(),
            )
            self.current_state.papers.append(paper)

        self.current_state.papers_count = len(self.current_state.papers)
        self.current_state.raw_papers_fetched = True
        self.save()

    def update_paper(
        self,
        arxiv_id: str,
        *,
        status: TaskStatus | None = None,
        error: str | None = None,
        result: dict[str, Any] | None = None,
        step_completed: str | None = None,
    ) -> None:
        if not self.current_state:
            logger.error("No current state")
            return

        paper = next((p for p in self.current_state.papers if p.arxiv_id == arxiv_id), None)
        if paper is None:
            logger.warning(f"Paper {arxiv_id} not registered; creating placeholder")
            paper = Paper(
                arxiv_id=arxiv_id,
                title="",
                title_zh="",
                authors=[],
                abstract="",
                tldr_zh="",
                categories=[],
                primary_category="",
                comment="",
                pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
                published_date="",
                updated_date="",
                processing_status=TaskStatus.PENDING,
                attempts=0,
                last_update=datetime.now(),
            )
            self.current_state.papers.append(paper)

        if status:
            if status == TaskStatus.IN_PROGRESS and paper.processing_status != TaskStatus.IN_PROGRESS:
                paper.attempts += 1
            paper.processing_status = status

        if error is not None:
            paper.error = error

        if step_completed and step_completed not in paper.completed_steps:
            paper.completed_steps.append(step_completed)

        if result:
            for key, value in result.items():
                if hasattr(paper, key):
                    setattr(paper, key, value)

        paper.last_update = datetime.now()
        self.save()

    def pending_paper_ids(self) -> list[str]:
        if not self.current_state:
            return []

        pending: list[str] = []
        for paper in self.current_state.papers:
            if paper.processing_status in {TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.RETRYING}:
                pending.append(paper.arxiv_id)
            elif paper.processing_status == TaskStatus.FAILED and paper.attempts < paper.max_attempts:
                paper.processing_status = TaskStatus.RETRYING
                pending.append(paper.arxiv_id)
        if pending:
            self.save()
        return pending

    def completed_papers(self) -> list[Paper]:
        if not self.current_state:
            return []
        return [p for p in self.current_state.papers if p.processing_status == TaskStatus.COMPLETED]

    def failed_papers(self) -> list[Paper]:
        if not self.current_state:
            return []
        return [
            p
            for p in self.current_state.papers
            if p.processing_status == TaskStatus.FAILED and p.attempts >= p.max_attempts
        ]

    def _recalculate_counts(self) -> None:
        if not self.current_state:
            return
        self.current_state.papers_count = len(self.current_state.papers)
        completed = sum(1 for p in self.current_state.papers if p.processing_status == TaskStatus.COMPLETED)
        failed = sum(
            1
            for p in self.current_state.papers
            if p.processing_status == TaskStatus.FAILED and p.attempts >= p.max_attempts
        )
        self.current_state.processed_papers_count = completed
        self.current_state.failed_papers_count = failed
