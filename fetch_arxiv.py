"""
arXiv paper fetcher and processor with task persistence

This script fetches papers from arXiv for specified categories and dates, processes
them using LLM for translation and summarization, and saves the results to JSON files.
It includes state persistence to handle interruptions and resume processing.
"""
import os
import re
import sys
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pytz
import arxiv
from loguru import logger
from dotenv import load_dotenv

from langfuse_llm import AsyncLLM
from task_manager import TaskManager, TaskStatus
from paper_type import RawPaper, Paper, DailyData


def setup_logger(log_level: str = "INFO") -> None:
    """Configure the logger

    Args:
        log_level: Log level (INFO, DEBUG, etc.)
    """
    # Remove default handlers
    logger.remove()

    # Add stderr handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=log_level,
    )

    # Add file handler with rotation
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger.add(
        log_dir / "fetch_arxiv_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        level="DEBUG",
        compression="zip",
    )


def normalize_date_format(date_str: str) -> str:
    """
    Ensure date string is in YYYY-MM-DD format.
    Converts various date formats to the required format.

    Args:
        date_str: Input date string

    Returns:
        Date string in YYYY-MM-DD format

    Raises:
        ValueError: If date cannot be parsed into a valid format
    """
    # Try to parse the provided string as a date
    date_formats = [
        "%Y-%m-%d",  # 2025-03-01
        "%Y-%m-%d",  # 2025-03-1 (already standardized by datetime)
        "%Y%m%d",  # 20250301
        "%d/%m/%Y",  # 01/03/2025
        "%m/%d/%Y",  # 03/01/2025
        "%d-%m-%Y",  # 01-03-2025
        "%m-%d-%Y",  # 03-01-2025
        "%Y/%m/%d",  # 2025/03/01
        "%b %d %Y",  # Mar 01 2025
        "%d %b %Y",  # 01 Mar 2025
        "%B %d %Y",  # March 01 2025
        "%d %B %Y",  # 01 March 2025
    ]

    # Handle shortened date formats like 2025-3-1
    if re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", date_str):
        result = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", date_str)
        if not result:
            raise ValueError(f"Invalid date format: {date_str}")
        year, month, day = result.groups()

        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    # Try each format
    for date_format in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, date_format)
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # If we get here, none of the formats matched
    raise ValueError(f"Date string '{date_str}' does not match any supported date format")


async def get_arxiv_papers(category: str, date_str: str, max_results: int = 1000) -> List[RawPaper]:
    """
    Get arXiv papers for a specific category and date

    Args:
        category: Category code (e.g., "cs.AI")
        date_str: Date string in YYYY-MM-DD format
        max_results: Maximum number of results to return

    Returns:
        List of RawPaper objects
    """
    # Ensure date is in correct format
    try:
        date_str = normalize_date_format(date_str)
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return []

    # Convert date string to datetime
    date = datetime.strptime(date_str, "%Y-%m-%d")

    # Build date range (from 00:00 to 23:59:59 UTC on the specified date)
    start_date = f"{date.strftime('%Y%m%d')}000000"
    end_date = f"{date.strftime('%Y%m%d')}235959"

    # Build query string
    if category:
        query = f"cat:{category} AND submittedDate:[{start_date} TO {end_date}]"
    else:
        query = f"submittedDate:[{start_date} TO {end_date}]"

    logger.info(f"Executing query: {query}")

    # Create client with reasonable delay to avoid API rate limits
    client = arxiv.Client(delay_seconds=3.0, num_retries=3)

    # Create search object
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    # Get results with retry logic
    retry_delays = [5, 10, 15]  # Wait times in seconds before each retry
    max_retries = len(retry_delays)
    retry_count = 0
    results = []
    
    while retry_count <= max_retries:
        try:
            results = list(client.results(search))
            logger.info(f"API returned {len(results)} papers")
            break  # Success, exit the loop
        except Exception as e:
            if retry_count < max_retries:
                delay = retry_delays[retry_count]
                retry_count += 1
                logger.warning(f"Query error: {e}. Retrying in {delay}s (attempt {retry_count}/{max_retries})")
                await asyncio.sleep(delay)
            else:
                logger.error(f"Query error after {max_retries} retries: {e}")
                return []
    
    if not results:
        logger.error("Query returned no results after all retries")
        return []

    # Extract metadata
    papers: List[RawPaper] = []
    for paper in results:
        # Ensure dates are in UTC
        published_date = (
            paper.published.replace(tzinfo=pytz.UTC)
            if paper.published.tzinfo is None
            else paper.published.astimezone(pytz.UTC)
        )
        updated_date = (
            paper.updated.replace(tzinfo=pytz.UTC)
            if paper.updated.tzinfo is None
            else paper.updated.astimezone(pytz.UTC)
        )

        # Create RawPaper object
        raw_paper = RawPaper(
            title=paper.title,
            authors=[author.name for author in paper.authors],
            abstract=paper.summary,
            categories=paper.categories,
            primary_category=paper.primary_category,
            comment=paper.comment if paper.comment else "",
            arxiv_id=paper.entry_id.split("/")[-1],
            pdf_url=paper.pdf_url,
            published_date=published_date.strftime("%Y-%m-%d %H:%M:%S %Z"),
            updated_date=updated_date.strftime("%Y-%m-%d %H:%M:%S %Z"),
        )
        papers.append(raw_paper)

    return papers


async def process_single_paper(llm: AsyncLLM, paper: RawPaper, task_manager: TaskManager) -> Optional[Paper]:
    """
    Process a single paper using LLM for translation and summarization

    Args:
        llm: The LLM client
        paper: Raw paper to process
        task_manager: Task manager for state tracking

    Returns:
        Processed Paper object, or None if processing failed
    """
    arxiv_id = paper.arxiv_id
    try:
        logger.info(f"Processing paper [{arxiv_id}]: {paper.title}")

        # Update task status to in progress
        task_manager.update_paper_task(arxiv_id=arxiv_id, status=TaskStatus.IN_PROGRESS)

        # Process the paper (translate title and generate TLDR)
        title_zh_task = llm.translate_title(paper.title, paper.abstract)
        tldr_zh_task = llm.tldr(paper.title, paper.abstract)

        # Wait for both tasks to complete
        title_zh, tldr_zh = await asyncio.gather(title_zh_task, tldr_zh_task)

        logger.success(f"Completed paper [{arxiv_id}]: {paper.title}")

        # Create processed Paper object with task status
        processed_paper = Paper(
            arxiv_id=arxiv_id,
            title=paper.title,
            title_zh=title_zh if title_zh else "翻译失败",
            authors=paper.authors,
            abstract=paper.abstract,
            tldr_zh=tldr_zh if tldr_zh else "tldr 生成失败",
            categories=paper.categories,
            primary_category=paper.primary_category,
            comment=paper.comment,
            pdf_url=paper.pdf_url if paper.pdf_url else f"https://arxiv.org/pdf/{arxiv_id}",
            published_date=paper.published_date,
            updated_date=paper.updated_date,
            processing_status=TaskStatus.COMPLETED,
            attempts=0,  # Will be updated by task_manager
            completed_steps=["translation", "tldr"],
            last_update=datetime.now()
        )

        # Mark task as completed
        task_manager.update_paper_task(
            arxiv_id=arxiv_id,
            status=TaskStatus.COMPLETED,
            result=processed_paper.model_dump(),
        )

        return processed_paper

    except Exception as e:
        error_msg = f"Error processing paper [{arxiv_id}]: {str(e)}"
        logger.error(error_msg)

        # Mark task as failed
        task_manager.update_paper_task(arxiv_id=arxiv_id, status=TaskStatus.FAILED, error=error_msg)

        return None


async def process_papers_batch(
    llm: AsyncLLM,
    papers: Dict[str, RawPaper],
    task_manager: TaskManager,
    batch_size: int = 5,
    concurrency_limit: int = 3,
) -> Tuple[List[Paper], List[RawPaper]]:
    """
    Process papers in batches with concurrency control

    Args:
        llm: The LLM client
        papers: Dict of RawPaper objects keyed by arxiv_id
        task_manager: Task manager for state tracking
        batch_size: Number of papers to process per batch
        concurrency_limit: Maximum number of concurrent processing tasks

    Returns:
        Tuple of (processed papers, failed papers)
    """
    # Get paper IDs that need processing
    pending_ids = task_manager.get_pending_papers()

    # Only process papers that exist in our papers dict
    pending_ids = [pid for pid in pending_ids if pid in papers]

    logger.info(f"Processing {len(pending_ids)} papers in batches")

    processed_papers: List[Paper] = []
    failed_papers: List[RawPaper] = []

    total_papers = len(pending_ids)
    completed_count = 0

    # Process in batches
    for i in range(0, len(pending_ids), batch_size):
        batch_ids = pending_ids[i : i + batch_size]
        completed_count += len(batch_ids)
        progress = completed_count / total_papers * 100

        logger.info(
            f"Processing batch {i // batch_size + 1}/{(len(pending_ids) + batch_size - 1) // batch_size} "
            f"({len(batch_ids)} papers) - Overall progress: {progress:.1f}%"
        )

        # Create semaphore for concurrency limit
        semaphore = asyncio.Semaphore(concurrency_limit)

        async def process_with_semaphore(paper_id: str) -> Optional[Paper]:
            async with semaphore:
                return await process_single_paper(llm, papers[paper_id], task_manager)

        # Process batch with concurrency limit
        tasks = [process_with_semaphore(paper_id) for paper_id in batch_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        for paper_id, result in zip(batch_ids, results):
            if isinstance(result, Exception):
                logger.error(f"Paper {paper_id} failed with exception: {result}")
                failed_papers.append(papers[paper_id])
            elif isinstance(result, Paper):
                processed_papers.append(result)
            else:
                failed_papers.append(papers[paper_id])

    # Check for any papers that were marked as failed in the task manager
    failed_ids = task_manager.get_failed_papers()
    for paper_id in failed_ids:
        if paper_id in papers and not any(p.arxiv_id == paper_id for p in failed_papers):
            failed_papers.append(papers[paper_id])

    logger.success(
        f"Processed {len(processed_papers)}/{len(papers)} papers "
        f"({len(processed_papers) / len(papers):.1%} complete), "
        f"failed: {len(failed_papers)}"
    )

    return processed_papers, failed_papers


def export_raw_papers(papers: List[RawPaper], category: str, date_str: str) -> str:
    """
    Save raw papers data to JSON file

    Args:
        papers: List of RawPaper objects
        category: Category string (e.g., "cs.AI")
        date_str: Date string in YYYY-MM-DD format

    Returns:
        Path to the saved file
    """
    # Ensure date is in correct format
    date_str = normalize_date_format(date_str)

    output_dir = Path(f"daydayarxiv_frontend/public/data/{date_str}")
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"{category}_raw.json"

    # Convert to dict
    papers_dict = [paper.model_dump() for paper in papers]

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(papers_dict, f, ensure_ascii=False, indent=2)

    logger.success(f"Saved {len(papers)} raw papers to {filename}")
    return str(filename)


def save_daily_data(daily_data: DailyData) -> str:
    """
    Save daily data to JSON file

    Args:
        daily_data: DailyData object

    Returns:
        Path to the saved file
    """
    # Ensure date is in correct format
    daily_data.date = normalize_date_format(daily_data.date)

    output_dir = Path(f"daydayarxiv_frontend/public/data/{daily_data.date}")
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"{daily_data.category}.json"

    # Update the last_update timestamp
    daily_data.last_update = datetime.now()

    # Convert to dict
    data = daily_data.model_dump(mode="json")

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.success(f"Saved {len(daily_data.papers)} processed papers to {filename}")
    return str(filename)


def cleanup_empty_data_dir(date_str: str, category: str) -> None:
    """
    Clean up any data directory or files that were created for a date with no papers

    Args:
        date_str: Date string in YYYY-MM-DD format
        category: Category string (e.g. cs.AI)
    """
    # Ensure date is in correct format
    try:
        date_str = normalize_date_format(date_str)
    except ValueError:
        logger.error(f"Invalid date format for cleanup: {date_str}")
        return

    output_dir = Path(f"daydayarxiv_frontend/public/data/{date_str}")

    # Check for and remove category files
    raw_file = output_dir / f"{category}_raw.json"
    data_file = output_dir / f"{category}.json"

    if raw_file.exists():
        raw_file.unlink()
        logger.debug(f"Removed file {raw_file}")

    if data_file.exists():
        data_file.unlink()
        logger.debug(f"Removed file {data_file}")

    # Remove directory if it's empty
    try:
        # List directory contents (will be empty list if no files)
        contents = list(output_dir.iterdir())
        if not contents and output_dir.exists():
            output_dir.rmdir()
            logger.debug(f"Removed empty directory {output_dir}")
    except Exception as e:
        logger.debug(f"Error while cleaning up directory {output_dir}: {e}")


def export_prompt(papers: List[RawPaper]) -> str:
    """
    Generate prompt text for paper list

    Args:
        papers: List of RawPaper objects

    Returns:
        Formatted prompt text
    """
    prompt_text = ""

    for i, paper in enumerate(papers, 1):
        # Format authors
        authors_text = ", ".join(paper.authors)

        # Format paper info
        paper_text = f"## {i}. {paper.title}\n"
        paper_text += f"> authors: {authors_text}\n" if authors_text else ""
        paper_text += f"> published date: {paper.published_date}\n\n" if paper.published_date else ""
        paper_text += f"### abstract\n{paper.abstract}\n\n" if paper.abstract else ""
        paper_text += f"### comment\n{paper.comment}\n\n" if paper.comment else ""

        # Add to result
        prompt_text += paper_text

    return prompt_text


async def run_day_pipeline(
    llm: AsyncLLM,
    task_manager: TaskManager,
    date_str: str,
    category: str = "cs.AI",
    max_results: int = 1000,
    force_refresh: bool = False,
) -> bool:
    """
    Run the full pipeline for a specific date

    Args:
        llm: The LLM client
        task_manager: Task manager for state tracking
        date_str: Date string in YYYY-MM-DD format
        category: Category to fetch papers for
        max_results: Maximum number of papers to fetch
        force_refresh: Force refreshing data even if it exists

    Returns:
        True if pipeline completed successfully, False otherwise
    """
    # Ensure date is in correct format
    try:
        date_str = normalize_date_format(date_str)
        logger.info(f"=== Processing {category} papers for {date_str} ===")
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        print(f"\nError: Invalid date format '{date_str}'. Please use YYYY-MM-DD format.")
        return False

    try:
        # Load or create state
        state = task_manager.load_state(date_str, category)

        # Check if pipeline was already completed AND whether any papers need processing
        if state.daily_data_saved and not force_refresh:
            # Enhanced check for papers needing processing: in_progress, pending, or failed but retriable
            unfinished_papers = [
                paper.arxiv_id 
                for paper in state.papers
                if (paper.processing_status in [TaskStatus.IN_PROGRESS, TaskStatus.PENDING, TaskStatus.RETRYING]) or
                   (paper.processing_status == TaskStatus.FAILED and paper.attempts < paper.max_attempts)
            ]

            if not unfinished_papers:
                # Validate completion status
                completion_status = verify_pipeline_completion(state)
                if completion_status["is_complete"]:
                    logger.info(f"Pipeline for {date_str} was already completed successfully. Use --force to rerun.")
                    return True
                else:
                    logger.warning(f"Pipeline marked as complete but has issues: {completion_status['issues']}")
                    if not force_refresh:
                        logger.info("Continuing with processing to resolve issues...")
            else:
                logger.info(f"Found {len(unfinished_papers)} papers that need processing from previous run:")
                for status in [TaskStatus.IN_PROGRESS, TaskStatus.PENDING, TaskStatus.RETRYING, TaskStatus.FAILED]:
                    count = len([p for p in state.papers if p.processing_status == status])
                    if count > 0:
                        logger.info(f"  - {status.value}: {count} papers")
                # Continue with processing these papers

        # 1. Fetch raw papers if not already done
        raw_papers: List[RawPaper] = []
        if not state.raw_papers_fetched or force_refresh:
            raw_papers = await get_arxiv_papers(category, date_str, max_results)
            if not raw_papers:
                logger.warning(f"No papers found for {category} on {date_str}")
                # Clean up any created directories or files
                cleanup_empty_data_dir(date_str, category)
                # Mark pipeline as completed to avoid repeated processing
                task_manager.update_pipeline_status(
                    raw_papers_fetched=True,
                    summary_generated=True,
                    daily_data_saved=True,
                )
                print(f"\nNo papers were found for category '{category}' on {date_str}.")
                print("No data files will be created for this date.")
                return True

            # Save raw papers
            export_raw_papers(raw_papers, category, date_str)

            # Register papers in the task manager
            task_manager.register_raw_papers([paper.model_dump() for paper in raw_papers])
            task_manager.update_pipeline_status(raw_papers_fetched=True)
        else:
            # Load raw papers from file
            raw_file = Path(f"daydayarxiv_frontend/public/data/{date_str}/{category}_raw.json")
            if raw_file.exists():
                with open(raw_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)

                # Check for empty file (no papers)
                if not raw_data:
                    logger.info(f"Empty raw file found for {category} on {date_str}, cleaning up")
                    cleanup_empty_data_dir(date_str, category)
                    print(f"\nNo papers were found for category '{category}' on {date_str}.")
                    print("Cleaning up any empty files.")
                    return True

                raw_papers = [RawPaper.model_validate(p) for p in raw_data]
                logger.info(f"Loaded {len(raw_papers)} raw papers from {raw_file}")
                
                # Ensure all raw papers are registered in the task manager
                if not state.raw_papers_fetched:
                    task_manager.register_raw_papers([paper.model_dump() for paper in raw_papers])
                    task_manager.update_pipeline_status(raw_papers_fetched=True)
            else:
                logger.error(f"Raw paper file {raw_file} not found")
                raw_papers = await get_arxiv_papers(category, date_str, max_results)
                if not raw_papers:
                    logger.warning(f"No papers found for {category} on {date_str}")
                    # Make sure we don't leave any empty directories
                    cleanup_empty_data_dir(date_str, category)
                    task_manager.update_pipeline_status(
                        raw_papers_fetched=True,
                        summary_generated=True,
                        daily_data_saved=True,
                    )
                    print(f"\nNo papers were found for category '{category}' on {date_str}.")
                    print("No data files will be created for this date.")
                    return True
                export_raw_papers(raw_papers, category, date_str)
                task_manager.register_raw_papers([paper.model_dump() for paper in raw_papers])

        # Create a lookup dict for papers by ID
        paper_dict = {paper.arxiv_id: paper for paper in raw_papers}

        # 2. Process papers if there are any pending
        processed_papers: List[Paper] = []
        failed_papers: List[RawPaper] = []

        # Get list of papers that need processing
        pending_papers = task_manager.get_pending_papers()

        # Get completed papers from state
        completed_papers = [p for p in state.papers if p.processing_status == TaskStatus.COMPLETED]
        if completed_papers:
            processed_papers.extend(completed_papers)
            logger.info(f"Found {len(completed_papers)} already processed papers in state")

        # Process papers that need processing
        if pending_papers or force_refresh:
            logger.info(f"Found {len(pending_papers)} papers that need processing")
            # Process pending papers
            new_processed, new_failed = await process_papers_batch(
                llm=llm,
                papers=paper_dict,
                task_manager=task_manager,
                batch_size=10,
                concurrency_limit=5,
            )

            # Extend lists
            if new_processed:
                # Filter out duplicates
                processed_ids = {p.arxiv_id for p in processed_papers}
                processed_papers.extend([p for p in new_processed if p.arxiv_id not in processed_ids])

            if new_failed:
                # Filter out duplicates
                failed_ids = {p.arxiv_id for p in failed_papers}
                failed_papers.extend([p for p in new_failed if p.arxiv_id not in failed_ids])

        # Retry failed papers if not in completed/processed
        if failed_papers and not force_refresh:
            logger.info(f"Retrying {len(failed_papers)} failed papers with increased timeout")
            # Create a new LLM client with longer timeouts for retries
            retry_llm = AsyncLLM(
                model=llm.model,
                model_strong=llm.model_strong,
                rpm=llm.rate_limiter.rpm // 2,  # Lower RPM
                max_retries=5,  # More retries
                retry_delay=5,  # Longer delay
            )

            # Create dict of failed papers
            failed_dict = {paper.arxiv_id: paper for paper in failed_papers}

            # Log detailed info about retry attempts
            for paper_id, paper in failed_dict.items():
                paper_state = next((p for p in state.papers if p.arxiv_id == paper_id), None)
                if paper_state:
                    logger.info(f"Retrying paper {paper_id}: attempts={paper_state.attempts}/{paper_state.max_attempts}, error={paper_state.error}")
                else:
                    logger.info(f"Retrying paper {paper_id} (no state info available)")

            # Retry processing
            retry_processed, retry_failed = await process_papers_batch(
                llm=retry_llm,
                papers=failed_dict,
                task_manager=task_manager,
                batch_size=5,
                concurrency_limit=2,
            )

            # Add retry results
            if retry_processed:
                # Filter out duplicates
                processed_ids = {p.arxiv_id for p in processed_papers}
                processed_papers.extend([p for p in retry_processed if p.arxiv_id not in processed_ids])

                # Remove successfully retried papers from failed list
                retry_success_ids = {p.arxiv_id for p in retry_processed}
                failed_papers = [p for p in failed_papers if p.arxiv_id not in retry_success_ids]
                
                logger.success(f"Successfully recovered {len(retry_processed)} previously failed papers")

        # 3. Generate daily summary if we have processed papers
        summary = ""
        if not state.summary_generated or force_refresh:
            logger.info("Generating daily summary...")

            # Generate prompt text from raw papers (we want full abstract text)
            prompt_text = export_prompt(raw_papers)

            # Generate summary
            summary = await llm.tldr_for_all_papers(prompt_text, date_str=date_str)
            task_manager.update_pipeline_status(summary_generated=True)
        else:
            # Use existing summary from state
            summary = state.summary
            logger.info("Using existing summary from state")

        # 4. Create and save daily data
        # Update the DailyData with the processed papers and summary
        state.summary = summary if summary else "快报生成失败。"
        state.papers = processed_papers  # Update with the complete list of processed papers
        
        # Save the updated state
        save_daily_data(state)
        task_manager.update_pipeline_status(daily_data_saved=True)

        # Check if we've processed all papers and log detailed completion information
        unfinished_count = sum(
            1 for paper in state.papers
            if paper.processing_status not in [TaskStatus.COMPLETED, TaskStatus.FAILED]
        )
        failed_count = sum(
            1 for paper in state.papers
            if paper.processing_status == TaskStatus.FAILED
        )

        if unfinished_count > 0:
            logger.warning(
                f"Pipeline completed for {date_str} but {unfinished_count} papers remain unprocessed. "
                f"Run again to process remaining papers."
            )
        elif failed_count > 0:
            logger.warning(
                f"Pipeline completed for {date_str} with {failed_count} permanently failed papers "
                f"(exceeded max retry attempts)."
            )
        else:
            logger.success(
                f"Pipeline completed for {date_str}: "
                f"Processed {len(processed_papers)}/{len(raw_papers)} papers "
                f"({len(processed_papers) / len(raw_papers):.1%})"
            )

        return True

    except Exception as e:
        logger.error(f"Error in pipeline for {date_str}: {str(e)}", exc_info=True)
        # Clean up any partially created files on error
        cleanup_empty_data_dir(date_str, category)
        return False

def verify_pipeline_completion(state: DailyData) -> dict:
    """
    Verify that a pipeline is truly complete by checking detailed status
    
    Args:
        state: The DailyData object to verify
        
    Returns:
        Dict with 'is_complete' boolean and 'issues' list
    """
    issues = []
    
    # Check for papers that should be processed but aren't
    total_papers = state.papers_count
    processed_count = sum(1 for p in state.papers if p.processing_status == TaskStatus.COMPLETED)
    failed_count = sum(1 for p in state.papers if p.processing_status == TaskStatus.FAILED)
    
    # Check if processed + failed count matches the expected count
    if processed_count + failed_count != total_papers:
        issues.append(f"Paper count mismatch: {processed_count} processed + {failed_count} failed != {total_papers} total")
    
    # Check for papers with missing required fields
    for paper in state.papers:
        if paper.processing_status == TaskStatus.COMPLETED:
            # Check if all required fields are populated
            if not paper.title_zh:
                issues.append(f"Paper {paper.arxiv_id} marked as completed but missing title_zh")
            if not paper.tldr_zh and "tldr" in paper.completed_steps:
                issues.append(f"Paper {paper.arxiv_id} marked as completed but missing tldr_zh")
    
    # Check for missing summary if we have papers
    if processed_count > 0 and state.summary_generated and not state.summary:
        issues.append("Summary marked as generated but is empty")
    
    # Result is complete if no issues found
    return {
        "is_complete": len(issues) == 0,
        "issues": issues
    }

async def main() -> int:
    """Main entry point"""
    # Setup argument parser
    parser = argparse.ArgumentParser(description="Fetch and process arXiv papers for a specific date or date range")

    # Date arguments
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        "--date",
        type=str,
        help="Single date to process (YYYY-MM-DD format)",
    )
    date_group.add_argument(
        "--start-date",
        type=str,
        help="Start date for date range (YYYY-MM-DD format)",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        help="End date for date range (YYYY-MM-DD format, inclusive). Required if --start-date is specified.",
    )

    # Other options
    parser.add_argument(
        "--category",
        type=str,
        default="cs.AI",
        help="arXiv category to fetch (default: cs.AI)",
    )
    parser.add_argument(
        "--rpm",
        type=int,
        default=os.getenv("RPM", 10),
        help="Maximum API requests per minute (default: 10)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=1000,
        help="Maximum number of papers to fetch (default: 1000)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force refreshing data even if it exists",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level (default: INFO)",
    )

    # Parse arguments
    args = parser.parse_args()

    # Configure logger
    setup_logger(args.log_level)

    # Load environment variables
    try:
        load_dotenv()
        logger.info("Environment variables loaded from .env file")
    except ImportError:
        logger.warning("dotenv package not installed, skipping .env loading")

    # Determine date(s) to process
    dates_to_process = []

    if args.date:
        # Process single date
        try:
            # Normalize date format
            normalized_date = normalize_date_format(args.date)
            dates_to_process = [normalized_date]
            if normalized_date != args.date:
                logger.info(f"Normalized date from {args.date} to {normalized_date}")
        except ValueError:
            logger.error(f"Invalid date format: {args.date}, expected YYYY-MM-DD")
            return 1

    elif args.start_date:
        # Process date range
        if not args.end_date:
            logger.error("--end-date is required when using --start-date")
            return 1

        try:
            # Normalize date formats
            start_date_str = normalize_date_format(args.start_date)
            end_date_str = normalize_date_format(args.end_date)

            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

            if start_date_str != args.start_date:
                logger.info(f"Normalized start date from {args.start_date} to {start_date_str}")

            if end_date_str != args.end_date:
                logger.info(f"Normalized end date from {args.end_date} to {end_date_str}")

            if end_date < start_date:
                logger.error("End date must be after start date")
                return 1

            # Generate list of dates
            current_date = start_date
            while current_date <= end_date:
                dates_to_process.append(current_date.strftime("%Y-%m-%d"))
                current_date += timedelta(days=1)

        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            return 1

    else:
        # Default to 2 days ago (UTC)
        default_date = datetime.now(timezone.utc)
        dates_to_process = [default_date.strftime("%Y-%m-%d")]

    # Initialize LLM client with rate limiting
    llm = AsyncLLM(
        rpm=args.rpm,
        # Use environment variables for both models' configs,
        # we can override RPM from command line for the weak model
        rpm_strong=int(os.getenv("LLM_RPM_STRONG", 10)),
    )

    # Initialize task manager
    task_manager = TaskManager()

    # Process each date
    success_count = 0
    for date_str in dates_to_process:
        try:
            logger.info(f"Processing date: {date_str}")
            success = await run_day_pipeline(
                llm=llm,
                task_manager=task_manager,
                date_str=date_str,
                category=args.category,
                max_results=args.max_results,
                force_refresh=args.force,
            )
            if success:
                success_count += 1

            # Small delay between dates
            if len(dates_to_process) > 1 and date_str != dates_to_process[-1]:
                logger.info("Waiting 5 seconds before processing next date...")
                await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Error processing date {date_str}: {str(e)}", exc_info=True)

    # Log final status
    if success_count == len(dates_to_process):
        logger.success(f"All {len(dates_to_process)} date(s) processed successfully")
        return 0
    elif success_count > 0:
        logger.warning(f"Completed {success_count}/{len(dates_to_process)} date(s) successfully")
        return 0
    else:
        logger.error(f"Failed to process any of the {len(dates_to_process)} date(s)")
        return 1


if __name__ == "__main__":
    logger.info(
        f"UTC time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}, Local time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    logger.info("Starting arXiv paper fetcher")
    logger.info("Loading environment variables")
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.warning("Process interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.critical(f"Unhandled exception: {str(e)}", exc_info=True)
        sys.exit(1)
