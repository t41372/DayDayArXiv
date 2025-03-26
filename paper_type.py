"""
Type definition for paper pydantic data classes.
These data structures except RawPaper are synced with the data type in frontend "types.ts" file.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Possible statuses for a task"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class RawPaper(BaseModel):
    """
    原始论文数据类，包含从arXiv获取的原始信息
    """

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
    """
    处理后的论文数据类，包含经过处理和翻译的信息
    """

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
    
    # Task tracking fields
    processing_status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    error: Optional[str] = None
    completed_steps: List[str] = Field(default_factory=list)
    last_update: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None
        }


class DailyData(BaseModel):
    """
    每日数据类，包含当天的论文信息和其他相关信息
    """

    date: str
    category: str
    summary: str
    papers: list[Paper]
    
    # Pipeline state tracking
    raw_papers_fetched: bool = False
    papers_count: int = 0
    processed_papers_count: int = 0
    failed_papers_count: int = 0
    summary_generated: bool = False
    daily_data_saved: bool = False
    last_update: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None
        }
