"""
Task management system for persistent state tracking and recovery.

This module provides functionality to track and persist the state of long-running
tasks, specifically paper processing, to enable recovery after interruptions.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from loguru import logger
from pydantic import BaseModel

from paper_type import Paper, DailyData, TaskStatus


class TaskManager:
    """Manages task state persistence directly in output JSON files"""

    def __init__(self, output_dir: str = "daydayarxiv_frontend/public/data"):
        """Initialize the task manager

        Args:
            output_dir: Base directory for output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.current_state: Optional[DailyData] = None

    def get_output_file_path(self, date: str, category: str) -> Path:
        """Get the path to the output file for a given date and category"""
        date_dir = self.output_dir / date
        date_dir.mkdir(parents=True, exist_ok=True)
        return date_dir / f"{category}.json"
    
    def get_raw_file_path(self, date: str, category: str) -> Path:
        """Get the path to the raw file for a given date and category"""
        date_dir = self.output_dir / date
        date_dir.mkdir(parents=True, exist_ok=True)
        return date_dir / f"{category}_raw.json"

    def create_pipeline_state(self, date: str, category: str) -> DailyData:
        """Create a new pipeline state

        Args:
            date: Date string in YYYY-MM-DD format
            category: Category string (e.g. cs.AI)

        Returns:
            A new DailyData object
        """
        state = DailyData(
            date=date,
            category=category,
            summary="",
            papers=[],
            last_update=datetime.now()
        )
        self.current_state = state
        self.save_state()
        return state

    def load_state(self, date: str, category: str) -> DailyData:
        """Load pipeline state from output file or create a new one if not exists

        Args:
            date: Date string in YYYY-MM-DD format
            category: Category string (e.g. cs.AI)

        Returns:
            The loaded or newly created DailyData
        """
        output_file = self.get_output_file_path(date, category)

        if output_file.exists():
            try:
                with open(output_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                state = DailyData.model_validate(data)
                logger.info(f"Loaded existing pipeline state from {output_file}")
                self.current_state = state
                return state
            except Exception as e:
                logger.error(f"Error loading pipeline state from {output_file}: {e}")

        # Create new state if file doesn't exist or loading failed
        logger.info(f"Creating new pipeline state for {date}, {category}")
        return self.create_pipeline_state(date, category)

    def save_state(self) -> None:
        """Save the current pipeline state to output file"""
        if not self.current_state:
            logger.error("No current state to save")
            return

        output_file = self.get_output_file_path(self.current_state.date, self.current_state.category)

        try:
            # Update the last_update timestamp
            self.current_state.last_update = datetime.now()
            
            # Convert to JSON using model_dump
            state_dict = self.current_state.model_dump(mode="json")

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(state_dict, f, ensure_ascii=False, indent=2)

            logger.debug(f"Saved pipeline state to {output_file}")
        except Exception as e:
            logger.error(f"Error saving pipeline state to {output_file}: {e}")

    def update_paper_task(
        self,
        arxiv_id: str,
        status: Optional[TaskStatus] = None,
        error: Optional[str] = None,
        step_completed: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update the status of a paper task

        Args:
            arxiv_id: The arXiv ID of the paper
            status: New status (if changing)
            error: Error message (if failed)
            step_completed: Name of a completed processing step
            result: Task result data (if completed)
        """
        if not self.current_state:
            logger.error("No current state")
            return

        # Find paper if it exists
        paper_index = next((i for i, p in enumerate(self.current_state.papers) if p.arxiv_id == arxiv_id), None)
        
        # Create paper if it doesn't exist
        if paper_index is None:
            new_paper = Paper(
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
                last_update=datetime.now()
            )
            self.current_state.papers.append(new_paper)
            paper = new_paper
        else:
            paper = self.current_state.papers[paper_index]

        # Update fields
        if status:
            prev_status = paper.processing_status
            paper.processing_status = status
            
            # Track attempt counts and status changes
            if status == TaskStatus.IN_PROGRESS:
                if prev_status != TaskStatus.IN_PROGRESS:  # Only increment if newly starting
                    paper.attempts += 1
                    logger.debug(f"Paper {arxiv_id}: Attempt {paper.attempts}/{paper.max_attempts}")
            elif status == TaskStatus.COMPLETED and prev_status != TaskStatus.COMPLETED:
                self.current_state.processed_papers_count += 1
                logger.debug(f"Paper {arxiv_id}: Completed successfully on attempt {paper.attempts}")
            elif status == TaskStatus.FAILED and prev_status != TaskStatus.FAILED:
                self.current_state.failed_papers_count += 1
                if paper.attempts >= paper.max_attempts:
                    logger.warning(f"Paper {arxiv_id}: Failed permanently after {paper.attempts} attempts")
                else:
                    logger.warning(f"Paper {arxiv_id}: Failed on attempt {paper.attempts}, will retry later")

        if error:
            paper.error = error
            logger.debug(f"Paper {arxiv_id}: Error: {error}")

        if step_completed and step_completed not in paper.completed_steps:
            paper.completed_steps.append(step_completed)
            logger.debug(f"Paper {arxiv_id}: Completed step '{step_completed}'")

        if result:
            # Update all fields from result
            for key, value in result.items():
                if hasattr(paper, key):
                    setattr(paper, key, value)

        # Always update the timestamp
        paper.last_update = datetime.now()
        self.current_state.last_update = datetime.now()

        # Save the state after each update
        self.save_state()

    def get_pending_papers(self) -> List[str]:
        """Get list of papers that are pending processing or failed but can be retried

        Returns:
            List of arXiv IDs that need processing
        """
        if not self.current_state:
            return []

        pending = []
        for paper in self.current_state.papers:
            if paper.processing_status == TaskStatus.PENDING:
                pending.append(paper.arxiv_id)
            # Include papers that were in progress (process was interrupted)
            elif paper.processing_status == TaskStatus.IN_PROGRESS:
                logger.info(f"Paper {paper.arxiv_id} was in progress but interrupted. Requeuing for processing.")
                pending.append(paper.arxiv_id)
            # Include papers marked as retrying
            elif paper.processing_status == TaskStatus.RETRYING:
                pending.append(paper.arxiv_id)
            # Include failed papers that haven't exceeded max attempts
            elif paper.processing_status == TaskStatus.FAILED and paper.attempts < paper.max_attempts:
                logger.info(f"Paper {paper.arxiv_id} failed but has {paper.attempts}/{paper.max_attempts} attempts. Will retry.")
                # Update status to RETRYING
                paper.processing_status = TaskStatus.RETRYING
                self.save_state()
                pending.append(paper.arxiv_id)

        return pending

    def get_failed_papers(self) -> List[str]:
        """Get list of papers that have failed processing

        Returns:
            List of arXiv IDs that failed processing
        """
        if not self.current_state:
            return []

        return [
            paper.arxiv_id
            for paper in self.current_state.papers
            if paper.processing_status == TaskStatus.FAILED and paper.attempts >= paper.max_attempts
        ]

    def register_raw_papers(self, papers: List[dict]) -> None:
        """Register a list of raw papers in the pipeline state

        Args:
            papers: List of raw papers with arxiv_id
        """
        if not self.current_state:
            logger.error("No current state")
            return

        self.current_state.papers_count = len(papers)
        self.current_state.raw_papers_fetched = True

        # Initialize or update papers
        for paper_data in papers:
            arxiv_id = paper_data.get('arxiv_id')
            if not arxiv_id:
                continue
                
            # Check if paper already exists
            existing = next((p for p in self.current_state.papers if p.arxiv_id == arxiv_id), None)
            
            if not existing:
                # Create a minimal Paper object with just the arxiv_id and pending status
                new_paper = Paper(
                    arxiv_id=arxiv_id,
                    title=paper_data.get('title', ''),
                    title_zh='',
                    authors=paper_data.get('authors', []),
                    abstract=paper_data.get('abstract', ''),
                    tldr_zh='',
                    categories=paper_data.get('categories', []),
                    primary_category=paper_data.get('primary_category', ''),
                    comment=paper_data.get('comment', ''),
                    pdf_url=paper_data.get('pdf_url', f"https://arxiv.org/pdf/{arxiv_id}"),
                    published_date=paper_data.get('published_date', ''),
                    updated_date=paper_data.get('updated_date', ''),
                    processing_status=TaskStatus.PENDING,
                    attempts=0,
                    last_update=datetime.now()
                )
                self.current_state.papers.append(new_paper)

        self.save_state()

    def update_pipeline_status(
        self,
        raw_papers_fetched: Optional[bool] = None,
        summary_generated: Optional[bool] = None,
        daily_data_saved: Optional[bool] = None,
    ) -> None:
        """Update the overall status of the pipeline

        Args:
            raw_papers_fetched: Whether raw papers have been fetched
            summary_generated: Whether summary has been generated
            daily_data_saved: Whether daily data has been saved
        """
        if not self.current_state:
            logger.error("No current state")
            return

        if raw_papers_fetched is not None:
            self.current_state.raw_papers_fetched = raw_papers_fetched

        if summary_generated is not None:
            self.current_state.summary_generated = summary_generated

        if daily_data_saved is not None:
            self.current_state.daily_data_saved = daily_data_saved

        self.current_state.last_update = datetime.now()
        self.save_state()
