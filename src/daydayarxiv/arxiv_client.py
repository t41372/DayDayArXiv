"""Async wrapper around the arxiv library."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime

import arxiv
from loguru import logger

from daydayarxiv.models import RawPaper


class ArxivFetchError(RuntimeError):
    """Raised when arXiv fetch fails after retries."""


async def fetch_papers(
    *,
    category: str,
    date_str: str,
    max_results: int,
    delay_seconds: float = 3.0,
    retries: Iterable[int] | None = None,
) -> list[RawPaper]:
    """Fetch arXiv papers for a given date and category."""
    retry_delays = list(retries or [5, 10, 15])
    date = datetime.strptime(date_str, "%Y-%m-%d")
    start_date = f"{date.strftime('%Y%m%d')}000000"
    end_date = f"{date.strftime('%Y%m%d')}235959"
    query = f"submittedDate:[{start_date} TO {end_date}]"
    if category:
        query = f"cat:{category} AND {query}"

    client = arxiv.Client(delay_seconds=delay_seconds, num_retries=3)
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    logger.info(f"Executing query: {query}")

    attempt = 0
    while True:
        try:
            results = await asyncio.to_thread(lambda: list(client.results(search)))
            logger.info(f"API returned {len(results)} papers")
            break
        except Exception as exc:  # pragma: no cover - exercised in tests with mocks
            if attempt >= len(retry_delays):
                message = f"Query error after retries: {exc}"
                logger.error(message)
                raise ArxivFetchError(message) from exc
            delay = retry_delays[attempt]
            attempt += 1
            logger.warning(
                f"Query error: {exc}. Retrying in {delay}s (attempt {attempt}/{len(retry_delays)})"
            )
            await asyncio.sleep(delay)

    papers: list[RawPaper] = []
    for paper in results:
        published = paper.published
        updated = paper.updated
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        raw_paper = RawPaper(
            title=paper.title,
            authors=[author.name for author in paper.authors],
            abstract=paper.summary,
            categories=paper.categories,
            primary_category=paper.primary_category,
            comment=paper.comment or "",
            arxiv_id=paper.entry_id.split("/")[-1],
            pdf_url=paper.pdf_url,
            published_date=published.strftime("%Y-%m-%d %H:%M:%S %Z"),
            updated_date=updated.strftime("%Y-%m-%d %H:%M:%S %Z"),
        )
        papers.append(raw_paper)

    return papers
