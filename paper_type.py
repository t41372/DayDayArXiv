"""
Type definition for paper pydantic data classes.
These data structures except RawPaper are synced with the data type in frontend "types.ts" file.
"""

from pydantic import BaseModel


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
    pdf_url: str
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


class DailyData(BaseModel):
    """
    每日数据类，包含当天的论文信息和其他相关信息
    """

    date: str
    category: str
    summary: str
    papers: list[Paper]
