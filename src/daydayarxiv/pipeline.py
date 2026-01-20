"""Main pipeline orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import datetime

from loguru import logger

from daydayarxiv.arxiv_client import ArxivFetchError, fetch_papers
from daydayarxiv.llm.client import LLMClient
from daydayarxiv.models import DailyData, DailyStatus, Paper, RawPaper, TaskStatus
from daydayarxiv.settings import Settings
from daydayarxiv.state import StateManager
from daydayarxiv.storage import read_json, update_data_index, write_json_atomic
from daydayarxiv.utils import normalize_date_format
from daydayarxiv.validation import validate_daily_data


def _export_prompt(papers: Iterable[RawPaper]) -> str:
    prompt_text = ""
    for idx, paper in enumerate(papers, 1):
        authors_text = ", ".join(paper.authors)
        paper_text = f"## {idx}. {paper.title}\n"
        if authors_text:
            paper_text += f"> authors: {authors_text}\n"
        if paper.published_date:
            paper_text += f"> published date: {paper.published_date}\n\n"
        if paper.abstract:
            paper_text += f"### abstract\n{paper.abstract}\n\n"
        if paper.comment:
            paper_text += f"### comment\n{paper.comment}\n\n"
        prompt_text += paper_text
    return prompt_text


def _build_summary_for_no_papers(date_str: str, category: str) -> str:
    return f"在 {date_str} 没有发现 {category} 分类下的新论文。"


class Pipeline:
    def __init__(self, settings: Settings, llm: LLMClient, state_manager: StateManager) -> None:
        self.settings = settings
        self.llm = llm
        self.state_manager = state_manager
        self.paths = state_manager.paths

    async def run_for_date(
        self,
        *,
        date_str: str,
        category: str,
        max_results: int,
        force: bool,
    ) -> bool:
        date_str = normalize_date_format(date_str)
        logger.info(f"=== Processing {category} papers for {date_str} ===")

        if force:
            state = self.state_manager.reset(date_str, category)
        else:
            state = self.state_manager.load(date_str, category)

        if state.daily_data_saved and not force:
            issues = validate_daily_data(state, self.settings.failure_patterns)
            if not issues:
                if state.processing_status in {DailyStatus.COMPLETED, DailyStatus.NO_PAPERS}:
                    logger.info("Existing data is complete; skipping.")
                    return True
                logger.warning("Existing data complete but not marked successful; retrying index update.")
                try:
                    update_data_index(self.paths, date_str, category)
                except Exception as exc:
                    self._mark_daily_failure(state, f"Failed to update data index: {exc}", retain_data=True)
                    return False
                state.processing_status = DailyStatus.COMPLETED
                state.error = None
                self.state_manager.save()
                return True
            logger.warning(f"Existing data incomplete: {issues}")

        if not force and not state.daily_data_saved:
            reset_count = self.state_manager.reset_failed_papers()
            if reset_count:
                logger.info(f"Reset {reset_count} failed papers for retry")

        state.processing_status = DailyStatus.IN_PROGRESS
        state.error = None
        self.state_manager.save()

        try:
            raw_papers = await self._load_or_fetch_raw(date_str, category, max_results, force)
        except ArxivFetchError as exc:
            self._mark_daily_failure(state, f"arXiv fetch failed: {exc}")
            return False
        except Exception as exc:
            self._mark_daily_failure(state, f"Failed to load raw papers: {exc}")
            return False

        if not raw_papers:
            state.summary = _build_summary_for_no_papers(date_str, category)
            state.summary_generated = True
            state.daily_data_saved = True
            state.raw_papers_fetched = True
            state.papers_count = 0
            state.processed_papers_count = 0
            state.failed_papers_count = 0
            state.papers = []
            state.processing_status = DailyStatus.NO_PAPERS
            state.error = None
            self.state_manager.save()
            try:
                update_data_index(self.paths, date_str, category)
            except Exception as exc:
                self._mark_daily_failure(state, f"Failed to update data index: {exc}", retain_data=True)
                return False
            logger.info("No papers found; saved empty daily data.")
            return True

        self.state_manager.register_raw_papers(raw_papers, max_attempts=self.settings.paper_max_attempts)
        paper_lookup = {paper.arxiv_id: paper for paper in raw_papers}

        try:
            await self._process_papers(paper_lookup)
        except Exception as exc:
            self._mark_daily_failure(state, f"Processing error: {exc}")
            return False

        completed_papers = self.state_manager.completed_papers()
        failed_papers = self.state_manager.failed_papers()

        if failed_papers:
            self._mark_daily_failure(state, f"{len(failed_papers)} papers failed; summary skipped")
            return False

        if len(completed_papers) != len(raw_papers):
            self._mark_daily_failure(
                state,
                f"Incomplete processing: {len(completed_papers)}/{len(raw_papers)} completed",
            )
            return False

        try:
            summary = await self._generate_summary(raw_papers, date_str)
        except Exception as exc:
            self._mark_daily_failure(state, f"Summary generation failed: {exc}")
            return False

        state.summary = summary
        state.summary_generated = True
        state.papers = completed_papers
        self.state_manager.save()

        issues = validate_daily_data(state, self.settings.failure_patterns)
        if issues:
            self._mark_daily_failure(state, f"Validation failed: {issues}")
            return False

        state.daily_data_saved = True
        state.processing_status = DailyStatus.COMPLETED
        state.error = None
        self.state_manager.save()
        try:
            update_data_index(self.paths, date_str, category)
        except Exception as exc:
            self._mark_daily_failure(state, f"Failed to update data index: {exc}", retain_data=True)
            return False
        logger.success(f"Pipeline completed for {date_str}")
        return True

    async def _load_or_fetch_raw(
        self,
        date_str: str,
        category: str,
        max_results: int,
        force: bool,
    ) -> list[RawPaper]:
        raw_path = self.paths.raw_path(date_str, category)
        if raw_path.exists() and not force:
            try:
                raw_data = read_json(raw_path)
                return [RawPaper.model_validate(item) for item in raw_data]
            except Exception as exc:
                logger.warning(f"Failed to read cached raw data {raw_path}: {exc}. Refetching.")

        papers = await fetch_papers(
            category=category,
            date_str=date_str,
            max_results=max_results,
        )
        write_json_atomic(raw_path, [paper.model_dump() for paper in papers])
        return papers

    async def _process_papers(self, papers: dict[str, RawPaper]) -> None:
        semaphore = asyncio.Semaphore(self.settings.concurrency)

        async def handle_paper(arxiv_id: str) -> Paper | None:
            async with semaphore:
                raw = papers[arxiv_id]
                return await self._process_single_paper(raw)

        while True:
            pending_ids = self.state_manager.pending_paper_ids()
            if not pending_ids:
                return
            batch_size = (
                self.settings.batch_size if self.settings.batch_size > 0 else len(pending_ids) or 1
            )
            logger.info(f"Processing {len(pending_ids)} papers")
            for start in range(0, len(pending_ids), batch_size):
                batch = pending_ids[start : start + batch_size]
                tasks = [handle_paper(paper_id) for paper_id in batch]
                await asyncio.gather(*tasks, return_exceptions=False)

    async def _process_single_paper(self, paper: RawPaper) -> Paper | None:
        arxiv_id = paper.arxiv_id
        self.state_manager.update_paper(arxiv_id, status=TaskStatus.IN_PROGRESS)

        try:
            title_task = self.llm.translate_title(paper.title, paper.abstract)
            tldr_task = self.llm.tldr(paper.title, paper.abstract)
            title_zh, tldr_zh = await asyncio.gather(title_task, tldr_task)

            result = {
                "title": paper.title,
                "title_zh": title_zh,
                "authors": paper.authors,
                "abstract": paper.abstract,
                "tldr_zh": tldr_zh,
                "categories": paper.categories,
                "primary_category": paper.primary_category,
                "comment": paper.comment,
                "pdf_url": paper.pdf_url or f"https://arxiv.org/pdf/{arxiv_id}",
                "published_date": paper.published_date,
                "updated_date": paper.updated_date,
                "completed_steps": ["translation", "tldr"],
                "last_update": datetime.now(),
            }

            self.state_manager.update_paper(arxiv_id, status=TaskStatus.COMPLETED, result=result)
            return Paper.model_validate({"arxiv_id": arxiv_id, **result, "processing_status": TaskStatus.COMPLETED})
        except Exception as exc:
            logger.error(f"Failed processing paper {arxiv_id}: {exc}")
            self.state_manager.update_paper(arxiv_id, status=TaskStatus.FAILED, error=str(exc))
            return None

    async def _generate_summary(self, raw_papers: list[RawPaper], date_str: str) -> str:
        prompt_text = _export_prompt(raw_papers)
        return await self.llm.daily_summary(prompt_text, date_str)

    def _mark_daily_failure(self, state: DailyData, message: str, *, retain_data: bool = False) -> None:
        state.processing_status = DailyStatus.FAILED
        state.error = message
        if not retain_data:
            state.daily_data_saved = False
            state.summary_generated = False
        self.state_manager.save()
