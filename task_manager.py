"""
Task management system for persistent state tracking and recovery.

This module provides functionality to track and persist the state of long-running
tasks, specifically paper processing, to enable recovery after interruptions.
"""

import json
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pathlib import Path

from loguru import logger
from pydantic import BaseModel


class TaskStatus(str, Enum):
    """Possible statuses for a task"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class PaperProcessingTask(BaseModel):
    """Represents a paper processing task"""

    arxiv_id: str
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    error: Optional[str] = None
    completed_steps: List[str] = []
    result: Optional[Dict[str, Any]] = None
    last_update: datetime = datetime.now()

    class Config:
        json_encoders = {
            # Custom encoder for datetime objects
            datetime: lambda dt: dt.isoformat()
        }


class PipelineState(BaseModel):
    """Represents the overall state of a processing pipeline for a specific date"""

    date: str  # YYYY-MM-DD
    category: str
    raw_papers_fetched: bool = False
    papers_count: int = 0
    processed_papers_count: int = 0
    failed_papers_count: int = 0
    summary_generated: bool = False
    daily_data_saved: bool = False
    tasks: Dict[str, PaperProcessingTask] = {}
    last_update: datetime = datetime.now()

    class Config:
        json_encoders = {
            # Custom encoder for datetime objects
            datetime: lambda dt: dt.isoformat()
        }


class TaskManager:
    """Manages task state persistence for the paper processing pipeline"""

    def __init__(self, base_dir: str = "task_state"):
        """Initialize the task manager

        Args:
            base_dir: Base directory for task state files
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.current_state: Optional[PipelineState] = None

    def get_state_file_path(self, date: str, category: str) -> Path:
        """Get the path to the state file for a given date and category"""
        return self.base_dir / f"{date}_{category}_state.json"

    def create_pipeline_state(self, date: str, category: str) -> PipelineState:
        """Create a new pipeline state

        Args:
            date: Date string in YYYY-MM-DD format
            category: Category string (e.g. cs.AI)

        Returns:
            A new PipelineState object
        """
        state = PipelineState(date=date, category=category)
        self.current_state = state
        self.save_state()
        return state

    def load_state(self, date: str, category: str) -> PipelineState:
        """Load pipeline state from file or create a new one if not exists

        Args:
            date: Date string in YYYY-MM-DD format
            category: Category string (e.g. cs.AI)

        Returns:
            The loaded or newly created PipelineState
        """
        state_file = self.get_state_file_path(date, category)

        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                state = PipelineState.model_validate(data)
                logger.info(f"Loaded existing pipeline state from {state_file}")
                self.current_state = state
                return state
            except Exception as e:
                logger.error(f"Error loading pipeline state from {state_file}: {e}")

        # Create new state if file doesn't exist or loading failed
        logger.info(f"Creating new pipeline state for {date}, {category}")
        return self.create_pipeline_state(date, category)

    def save_state(self) -> None:
        """Save the current pipeline state to file"""
        if not self.current_state:
            logger.error("No current state to save")
            return

        state_file = self.get_state_file_path(self.current_state.date, self.current_state.category)

        try:
            # Convert to JSON using model_dump with date_format
            state_dict = self.current_state.model_dump(mode="json")

            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state_dict, f, ensure_ascii=False, indent=2)

            logger.debug(f"Saved pipeline state to {state_file}")
        except Exception as e:
            logger.error(f"Error saving pipeline state to {state_file}: {e}")

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

        # Create task if it doesn't exist
        if arxiv_id not in self.current_state.tasks:
            self.current_state.tasks[arxiv_id] = PaperProcessingTask(arxiv_id=arxiv_id)

        task = self.current_state.tasks[arxiv_id]

        # Update fields
        if status:
            task.status = status
            if status == TaskStatus.IN_PROGRESS:
                task.attempts += 1
            elif status == TaskStatus.COMPLETED:
                self.current_state.processed_papers_count += 1
            elif status == TaskStatus.FAILED:
                self.current_state.failed_papers_count += 1

        if error:
            task.error = error

        if step_completed and step_completed not in task.completed_steps:
            task.completed_steps.append(step_completed)

        if result:
            task.result = result

        # Always update the timestamp
        task.last_update = datetime.now()
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
        for arxiv_id, task in self.current_state.tasks.items():
            if task.status == TaskStatus.PENDING:
                pending.append(arxiv_id)
            # Include papers that were in progress (process was interrupted)
            elif task.status == TaskStatus.IN_PROGRESS:
                logger.info(f"Paper {arxiv_id} was in progress but interrupted. Requeuing for processing.")
                pending.append(arxiv_id)
            # Include failed papers that haven't exceeded max attempts
            elif task.status == TaskStatus.FAILED and task.attempts < task.max_attempts:
                task.status = TaskStatus.RETRYING
                pending.append(arxiv_id)

        return pending

    def get_failed_papers(self) -> List[str]:
        """Get list of papers that have failed processing

        Returns:
            List of arXiv IDs that failed processing
        """
        if not self.current_state:
            return []

        return [
            arxiv_id
            for arxiv_id, task in self.current_state.tasks.items()
            if task.status == TaskStatus.FAILED and task.attempts >= task.max_attempts
        ]

    def register_raw_papers(self, arxiv_ids: List[str]) -> None:
        """Register a list of raw papers in the pipeline state

        Args:
            arxiv_ids: List of arXiv IDs to register
        """
        if not self.current_state:
            logger.error("No current state")
            return

        self.current_state.papers_count = len(arxiv_ids)
        self.current_state.raw_papers_fetched = True

        # Initialize tasks for each paper
        for arxiv_id in arxiv_ids:
            if arxiv_id not in self.current_state.tasks:
                self.current_state.tasks[arxiv_id] = PaperProcessingTask(arxiv_id=arxiv_id)

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
