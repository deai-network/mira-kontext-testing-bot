"""Web fetching and ingestion for the testing bot."""

from __future__ import annotations

import warnings
from importlib import import_module
from typing import Any, cast

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
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message='Field name "json" in "ChangeTrackingData" shadows an attribute',
                    category=UserWarning,
                )
                firecrawl_module = import_module("firecrawl")
            firecrawl_app = firecrawl_module.FirecrawlApp
        except ImportError as exc:
            raise WebFetchError(
                "firecrawl-py is not installed. Run: poetry install"
            ) from exc

        self._firecrawl_app = firecrawl_app(api_key=api_key)
        return self._firecrawl_app

    def _search_firecrawl(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        """Search via Firecrawl and return normalized result URLs."""
        app = self._get_firecrawl()
        try:
            raw_response: object = app.search(query, params={"limit": max_results})
        except Exception as exc:
            raise WebFetchError(f"Firecrawl search failed for '{query}': {exc}") from exc

        raw_results: object
        if isinstance(raw_response, dict):
            response = cast(dict[str, object], raw_response)
            raw_results = response.get("data")
        else:
            raw_results = raw_response
        if not isinstance(raw_results, list):
            return []

        results: list[dict[str, str]] = []
        for raw_result in cast(list[object], raw_results)[:max_results]:
            if not isinstance(raw_result, dict):
                continue
            result = cast(dict[str, object], raw_result)
            url = str(result.get("url") or result.get("href") or "")
            if not url:
                continue
            results.append({
                "title": str(result.get("title", "")),
                "url": url,
                "snippet": str(result.get("description") or result.get("snippet") or ""),
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
            raw_result = app.scrape_url(
                url,
                params={
                    "formats": ["markdown", "html"],
                    "onlyMainContent": True,
                },
            )
        except Exception as exc:
            raise WebFetchError(f"Failed to scrape {url}: {exc}") from exc

        result = cast(dict[str, object], raw_result) if isinstance(raw_result, dict) else {}
        data = result.get("data", result)
        if not isinstance(data, dict):
            data = {"markdown": str(data)}
        page_data = cast(dict[str, object], data)

        markdown = str(page_data.get("markdown", ""))
        html = str(page_data.get("html", ""))
        raw_meta = page_data.get("metadata", {})
        meta = cast(dict[str, object], raw_meta) if isinstance(raw_meta, dict) else {}
        title = str(meta.get("title", url))

        content = markdown or html or ""
        if not content.strip():
            raise WebFetchError(f"No content extracted from {url}")

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
                "description": str(meta.get("description", "")),
            },
            source_url=url,
            principal=context.principal,
            collection_external_id=None,
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
        search_results = self._search_firecrawl(query, max_results=max_results)
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
