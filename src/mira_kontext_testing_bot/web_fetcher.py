"""Web fetching and ingestion for the testing bot."""

from __future__ import annotations

from typing import Any

from .client import KontextClient
from .config import get_settings
from .errors import BotError
from .session import ChatContext


class WebFetchError(BotError):
    """Raised when web fetching fails."""

    pass


class WebFetcher:
    """Fetches web pages via Firecrawl and ingests them into Kontext API."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._firecrawl_app: Any | None = None

    def _get_firecrawl(self) -> Any:
        """Lazy-load the FirecrawlApp."""
        if self._firecrawl_app is not None:
            return self._firecrawl_app

        api_key = self.settings.firecrawl_api_key
        if not api_key:
            raise WebFetchError(
                "Firecrawl API key not configured. Set FIRECRAWL_API_KEY in .env"
            )

        try:
            from firecrawl import FirecrawlApp
        except ImportError as exc:
            raise WebFetchError(
                "firecrawl-py is not installed. Run: poetry install"
            ) from exc

        self._firecrawl_app = FirecrawlApp(api_key=api_key)
        return self._firecrawl_app

    def _search_duckduckgo(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        """Search DuckDuckGo and return top result URLs."""
        try:
            from duckduckgo_search import DDGS
        except ImportError as exc:
            raise WebFetchError(
                "duckduckgo-search is not installed. Run: poetry install"
            ) from exc

        results: list[dict[str, str]] = []
        with DDGS() as ddgs:
            for result in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", ""),
                })
        return results

    async def fetch_url(
        self,
        url: str,
        client: KontextClient,
        context: ChatContext,
    ) -> dict[str, Any]:
        """Fetch a single URL via Firecrawl and ingest into the API."""
        app = self._get_firecrawl()

        try:
            result = app.scrape_url(
                url,
                params={
                    "formats": ["markdown", "html"],
                    "onlyMainContent": True,
                },
            )
        except Exception as exc:
            raise WebFetchError(f"Failed to scrape {url}: {exc}") from exc

        data = result.get("data", result) if isinstance(result, dict) else result
        if not isinstance(data, dict):
            data = {"markdown": str(data)}

        markdown = data.get("markdown", "")
        html = data.get("html", "")
        meta = data.get("metadata", {})
        title = meta.get("title", url)

        content = markdown or html or ""
        if not content.strip():
            raise WebFetchError(f"No content extracted from {url}")

        # Use the user's private collection for ingested web content
        collection_id = context.private_source_collection_external_id
        if collection_id is None:
            from .session import get_session_manager
            collection_id = get_session_manager().private_collection_external_id(
                context.principal
            )

        # Ingest into API
        ingest_result = await client.ingest_record(
            content=content,
            source_system="web",
            source_object_type="web_page",
            source_object_id=url,
            title=title,
            metadata={
                "fetched_url": url,
                "fetched_by": "testing_bot",
                "title": title,
                "description": meta.get("description", ""),
            },
            source_url=url,
            principal=context.principal,
            collection_external_id=collection_id,
        )

        return {
            "url": url,
            "title": title,
            "content_length": len(content),
            "ingest_status": ingest_result.status,
            "content_item_id": str(ingest_result.content_item_id),
            "short_id": None,  # populated by caller if needed
        }

    async def search_and_ingest(
        self,
        query: str,
        client: KontextClient,
        context: ChatContext,
        max_results: int = 3,
    ) -> list[dict[str, Any]]:
        """Search the web for a query, fetch top results, and ingest them."""
        search_results = self._search_duckduckgo(query, max_results=max_results)
        if not search_results:
            return []

        ingested: list[dict[str, Any]] = []
        for result in search_results:
            url = result["url"]
            if not url:
                continue
            try:
                info = await self.fetch_url(url, client, context)
                info["search_title"] = result["title"]
                info["search_snippet"] = result["snippet"]
                ingested.append(info)
            except WebFetchError as exc:
                ingested.append({
                    "url": url,
                    "error": str(exc),
                    "search_title": result["title"],
                })

        return ingested

    def is_configured(self) -> bool:
        """Check whether Firecrawl is available for use."""
        return bool(self.settings.firecrawl_api_key)
