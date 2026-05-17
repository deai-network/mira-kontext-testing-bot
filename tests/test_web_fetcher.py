"""Tests for web search and ingestion."""

from __future__ import annotations

from uuid import uuid4

import pytest

from mira_kontext_testing_bot.models import IngestResult, Principal, Project, Session
from mira_kontext_testing_bot.session import ChatContext
from mira_kontext_testing_bot.web_fetcher import WebFetcher


class FakeFirecrawlApp:
    def __init__(self) -> None:
        self.search_calls: list[tuple[str, dict[str, object]]] = []
        self.scrape_calls: list[str] = []

    def search(self, query: str, params: dict[str, object] | None = None) -> dict[str, object]:
        self.search_calls.append((query, params or {}))
        return {
            "data": [
                {
                    "url": "https://example.com/pg-supply-chain",
                    "title": "P&G Supply Chain",
                    "description": "Manufacturing and logistics overview",
                }
            ]
        }

    def scrape_url(self, url: str, params: dict[str, object] | None = None) -> dict[str, object]:
        self.scrape_calls.append(url)
        return {
            "data": {
                "markdown": "P&G supply chain content",
                "metadata": {"title": "P&G Supply Chain"},
            }
        }


class FakeClient:
    def __init__(self) -> None:
        self.ingests: list[dict[str, object]] = []

    async def ingest_record(self, **kwargs: object) -> IngestResult:
        self.ingests.append(kwargs)
        return IngestResult(
            content_item_id=uuid4(),
            source_record_id=uuid4(),
            checksum="abc123",
            status="created",
        )


@pytest.mark.asyncio
async def test_search_and_ingest_uses_firecrawl_search_directly() -> None:
    fetcher = WebFetcher()
    fake_app = FakeFirecrawlApp()
    fetcher._firecrawl_app = fake_app
    client = FakeClient()
    context = ChatContext(
        project=Project(external_id="project-a"),
        session=Session(external_id="session-a", project_external_id="project-a"),
        principal=Principal(external_id="t1"),
        mode="memory_only",
        private_source_collection_external_id="user-t1-private",
    )

    results = await fetcher.search_and_ingest(
        "procter gamble supply chain",
        client,  # type: ignore[arg-type]
        context,
        max_results=1,
    )

    assert fake_app.search_calls == [
        ("procter gamble supply chain", {"limit": 1})
    ]
    assert fake_app.scrape_calls == ["https://example.com/pg-supply-chain"]
    assert client.ingests[0]["collection_external_id"] is None
    assert results[0]["search_title"] == "P&G Supply Chain"
