import os
import time
import json
from datetime import datetime, timedelta, timezone
import pytz
import arxiv
from dotenv import load_dotenv
from loguru import logger

from paper_type import RawPaper, Paper, DailyData
from langfuse_llm import LLM


def get_arxiv_papers(
    category: str, date_str: str, max_results: int = 1000
) -> list[RawPaper]:
    """
    获取指定日期和分类的所有论文

    参数:
    - category: 分类，例如 'cs.AI'，如果为 None 或空字符串则不限制分类
    - date_str: 日期字符串，格式为 'YYYY-MM-DD'
    - max_results: 最大结果数，默认1000

    返回:
    - 论文列表，每个元素包含论文的元数据
    """
    # 将日期字符串转换为datetime对象
    date = datetime.strptime(date_str, "%Y-%m-%d")

    # 构建日期范围（当天的00:00到23:59:59）UTC
    start_date = f"{date.strftime('%Y%m%d')}000000"
    end_date = f"{date.strftime('%Y%m%d')}235959"

    # 构建查询字符串
    if category:
        query = f"cat:{category} AND submittedDate:[{start_date} TO {end_date}]"
    else:
        query = f"submittedDate:[{start_date} TO {end_date}]"

    logger.info(f"执行查询: {query}")

    # 创建客户端，设置合理的延迟以避免API限制
    client = arxiv.Client(delay_seconds=3.0, num_retries=3)

    # 创建搜索对象
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    # 获取结果
    try:
        results = list(client.results(search))
        logger.info(f"API 返回了 {len(results)} 篇论文")
    except Exception as e:
        logger.error(f"查询出错: {e}")
        return []

    # 提取需要的元数据
    papers: list[RawPaper] = []
    for paper in results:
        # 确保日期是 UTC 时区
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

        # 创建 RawPaper 对象
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


def get_papers_for_date_range(
    category: str, start_date_str: str, end_date_str: str | None = None
) -> list[RawPaper]:
    """获取日期范围内的所有论文"""
    if end_date_str is None:
        end_date_str = start_date_str

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

    all_papers: list[RawPaper] = []
    current_date = start_date

    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        logger.info(f"\n获取 {date_str} 的论文...")

        papers = get_arxiv_papers(category, date_str)
        if papers:
            all_papers.extend(papers)
            # 保存当天的数据
            save_papers_to_json(papers, category, date_str)

        # 前进到下一天
        current_date += timedelta(days=1)

        # 避免过快请求
        if current_date <= end_date:
            logger.info("等待3秒后继续...")
            time.sleep(3)

    return all_papers


def process_papers(
    llm: LLM, papers: list[RawPaper]
) -> tuple[list[Paper], list[RawPaper]]:
    """
    处理论文数据，将 RawPaper 转换为 Paper，并添加中文标题和摘要
    """

    processed_papers: list[Paper] = []
    failed_papers: list[RawPaper] = []
    logger.info(f"共 {len(papers)} 篇论文待处理...")
    if not papers:
        logger.warning("没有论文需要处理")
        return [[], []]

    logger.info(f"开始处理 {len(papers)} 篇论文...")
    for i, paper in enumerate(papers):
        try:
            logger.info(f"正在处理第 {i + 1}/{len(papers)} 篇论文 (ID: {paper.arxiv_id})...")

            # 翻译标题
            title_zh = llm.translate_title(paper.title, paper.abstract)

            # 生成中文摘要
            tldr_zh = llm.tldr(paper.title, paper.abstract)

            # 创建 Paper 对象
            processed_paper = Paper(
                arxiv_id=paper.arxiv_id,
                title=paper.title,
                title_zh=title_zh,
                authors=paper.authors,
                abstract=paper.abstract,
                tldr_zh=tldr_zh,
                categories=paper.categories,
                primary_category=paper.primary_category,
                comment=paper.comment,
                pdf_url=paper.pdf_url,
                published_date=paper.published_date,
                updated_date=paper.updated_date,
            )
            processed_papers.append(processed_paper)

            # 每处理5篇论文休息一下，避免API限制
            if (i + 1) % 5 == 0 and i + 1 < len(papers):
                logger.info("API休息2秒...")
                time.sleep(2)

        except Exception as e:
            logger.error(f"处理论文 {paper.arxiv_id} 时出错: {str(e)}", exc_info=True)
            failed_papers.append(paper)
            continue

    logger.success(
        f"共成功处理 {len(processed_papers)}/{len(papers)} 篇论文, 失败 {len(failed_papers)} 篇"
    )
    if failed_papers:
        logger.warning(f"失败的论文ID: {[paper.arxiv_id for paper in failed_papers]}")
    # 返回处理后的论文列表和失败的论文列表
    return [processed_papers, failed_papers]


def save_daily_data(daily_data: DailyData) -> str:
    """保存每日论文数据到JSON文件"""
    output_dir = f"daydayarxiv_frontend/public/data/{daily_data.date}"
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output_dir}/{daily_data.category}.json"

    # Convert dataclass to dict
    data = daily_data.model_dump()

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.success(f"已保存 {len(daily_data.papers)} 篇论文到文件: {filename}")
    return filename


def save_papers_to_json(papers: list[RawPaper], category: str, date_str: str) -> str:
    """
    保存论文数据到JSON文件

    参数:
    - papers: 论文列表
    - category: 分类
    - date_str: 日期字符串

    返回:
    - 保存的文件路径
    """
    output_dir = f"daydayarxiv_frontend/public/data/{date_str}"
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output_dir}/{category}_raw.json"

    # Convert RawPaper objects to dict
    papers_dict = [paper.model_dump() for paper in papers]

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(papers_dict, f, ensure_ascii=False, indent=2)

    logger.success(f"已保存 {len(papers)} 篇原始论文数据到文件: {filename}")
    return filename


def export_prompt(papers: list[RawPaper]) -> str:
    """
    根据论文列表，生成纯文本prompt字符串

    参数:
    - papers: RawPaper论文列表对象

    返回:
    - 包含所有论文格式化信息的字符串
    """
    prompt_text = ""

    for i, paper in enumerate(papers, 1):
        # 获取作者列表
        authors_text = ", ".join(paper.authors)

        # 格式化论文信息
        paper_text = f"## {i}. {paper.title}\n"
        paper_text += f"> authors: {authors_text}\n" if authors_text else ""
        paper_text += (
            f"> published date: {paper.published_date}\n\n"
            if paper.published_date
            else ""
        )
        paper_text += f"### abstract\n{paper.abstract}\n\n" if paper.abstract else ""
        paper_text += f"### comment\n{paper.comment}\n\n" if paper.comment else ""

        # 添加到结果字符串
        prompt_text += paper_text

    return prompt_text


def main(target_date = datetime.now(timezone.utc) - timedelta(days=2)) -> None:
    """
    获取 UTC 时间昨天的所有论文数据，并保存为 JSON 文件
    文件位置: daydayarxiv_frontend/public/data/{date}/{category}.json
    """
    # 配置logger
    logger.remove()  # 移除默认处理程序
    logger.add(
        sys.stderr, 
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "logs/fetch_arxiv_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        level="DEBUG",
        compression="zip"
    )
    
    llm = LLM()

    
    date_str = target_date.strftime("%Y-%m-%d")
    category = "cs.AI"
    logger.info(f"获取 UTC 时间 ({date_str}) 的论文...")

    # 1. 获取原始论文数据
    raw_papers = get_arxiv_papers(category, date_str)
    if not raw_papers:
        logger.warning("未获取到论文数据")
        return

    # 2. 保存原始数据
    save_papers_to_json(raw_papers, category, date_str)

    # 3. 处理论文数据（添加中文标题和摘要）
    processed_papers, failed_papers = process_papers(llm=llm, papers=raw_papers)
    if failed_papers:
        logger.info(f"重新处理失败的论文: {[paper.arxiv_id for paper in failed_papers]}")
        time.sleep(30)
        reprocessed_papers, re_failed_papers = process_papers(llm=llm, papers=failed_papers)
        processed_papers.extend(reprocessed_papers)
        failed_papers = re_failed_papers
        
    # 4. 生成所有论文的摘要文本，用于生成每日总结
    prompt_text = export_prompt(raw_papers)

    # 5. 使用LLM生成每日总结
    logger.info("正在生成每日总结...")
    summary = llm.tldr_for_all_papers(prompt_text)

    # 6. 创建并保存每日数据
    daily_data = DailyData(
        date=date_str, category=category, summary=summary, papers=processed_papers
    )
    save_daily_data(daily_data)

    logger.success(f"总共获取并处理了 {len(processed_papers)} 篇论文")


if __name__ == "__main__":
    # Load environment variables from .env file if available
    try:
        load_dotenv()
        logger.info("Environment variables loaded from .env file")
    except ImportError:
        logger.warning("dotenv package not installed, skipping .env loading")
    
    import sys
    
    main(datetime.now(timezone.utc) - timedelta(days=3))
