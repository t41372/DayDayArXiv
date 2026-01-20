from datetime import datetime

import pytest

from daydayarxiv.arxiv_client import ArxivFetchError, fetch_papers


class DummyAuthor:
    def __init__(self, name: str) -> None:
        self.name = name


class DummyPaper:
    def __init__(self) -> None:
        self.title = "Title"
        self.authors = [DummyAuthor("Author")]
        self.summary = "Abstract"
        self.categories = ["cs.AI"]
        self.primary_category = "cs.AI"
        self.comment = ""
        self.entry_id = "http://arxiv.org/abs/1234.5678v1"
        self.pdf_url = "http://arxiv.org/pdf/1234.5678v1"
        self.published = datetime(2025, 1, 1, 0, 0, 0)
        self.updated = datetime(2025, 1, 1, 0, 0, 0)


class DummyClient:
    def __init__(self, *args, **kwargs):
        pass

    def results(self, search):
        return [DummyPaper()]


class ErrorClient:
    def __init__(self, *args, **kwargs):
        pass

    def results(self, search):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_fetch_papers(monkeypatch):
    monkeypatch.setattr("daydayarxiv.arxiv_client.arxiv.Client", DummyClient)
    papers = await fetch_papers(category="cs.AI", date_str="2025-01-01", max_results=10)
    assert len(papers) == 1
    assert papers[0].arxiv_id == "1234.5678v1"
    assert papers[0].title == "Title"


@pytest.mark.asyncio
async def test_fetch_papers_raises(monkeypatch):
    monkeypatch.setattr("daydayarxiv.arxiv_client.arxiv.Client", ErrorClient)

    async def _sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("daydayarxiv.arxiv_client.asyncio.sleep", _sleep)

    with pytest.raises(ArxivFetchError):
        await fetch_papers(
            category="cs.AI",
            date_str="2025-01-01",
            max_results=10,
            retries=[0],
        )
