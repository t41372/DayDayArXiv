"""Pydantic models for data and pipeline state."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class TaskStatus(str, Enum):
    """Possible statuses for a paper processing task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class DailyStatus(str, Enum):
    """Possible statuses for a daily pipeline run."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NO_PAPERS = "no_papers"


class RawPaper(BaseModel):
    """Raw paper metadata fetched from arXiv."""

    model_config = ConfigDict(extra="ignore")

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    primary_category: str
    comment: str
    pdf_url: str | None
    published_date: str
    updated_date: str


class Paper(BaseModel):
    """Processed paper data stored for the frontend."""

    model_config = ConfigDict(extra="ignore")

    arxiv_id: str
    title: str
    title_zh: str
    authors: list[str]
    abstract: str
    tldr_zh: str
    categories: list[str]
    primary_category: str
    comment: str
    pdf_url: str
    published_date: str
    updated_date: str

    processing_status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    error: str | None = None
    completed_steps: list[str] = Field(default_factory=list)
    llm_backup_calls: int = 0
    last_update: datetime | None = None

    @field_serializer("last_update")
    def _serialize_last_update(self, value: datetime | None) -> str | None:
        return value.isoformat() if value else None


class DailyData(BaseModel):
    """Daily output data and pipeline state."""

    model_config = ConfigDict(extra="ignore")

    date: str
    category: str
    summary: str
    papers: list[Paper]

    processing_status: DailyStatus = DailyStatus.PENDING
    error: str | None = None

    raw_papers_fetched: bool = False
    papers_count: int = 0
    processed_papers_count: int = 0
    failed_papers_count: int = 0
    llm_backup_calls: int = 0
    summary_generated: bool = False
    daily_data_saved: bool = False
    last_update: datetime | None = None

    @field_serializer("last_update")
    def _serialize_last_update(self, value: datetime | None) -> str | None:
        return value.isoformat() if value else None


class DataIndex(BaseModel):
    """Index of available daily data files."""

    model_config = ConfigDict(extra="ignore")

    available_dates: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    by_date: dict[str, list[str]] = Field(default_factory=dict)
    last_updated: datetime | None = None

    @field_serializer("last_updated")
    def _serialize_last_updated(self, value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    def touch(self) -> None:
        self.last_updated = datetime.now(UTC)
