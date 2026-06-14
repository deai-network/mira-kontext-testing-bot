"""MCP transport for the Mira Kontext API.

Calls the `query_context` tool on the Kontext MCP server (Streamable HTTP, ADR 0017)
instead of `POST /v1/query`. MCP and REST share the same `QueryService` + ACL
server-side, so results are identical — MCP is the production-parity agent path per
ADR 0005. Returns the same `QueryResult` shape as `KontextClient.query`, so it is a
drop-in for the retrieval stage.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from .config import get_settings
from .errors import ConfigurationError, KontextAPIError
from .models import ContextItem, Principal, QueryResult


class KontextMCPClient:
    """Thin MCP client exposing the same `query()` contract as the REST client.

    A fresh Streamable-HTTP session is opened per call. That is fine for an
    interactive CLI; the cost is one round-trip of session setup per query.
    """

    def __init__(
        self,
        mcp_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self.mcp_url = mcp_url or settings.mcp_url
        self.token = token or settings.kontext_token
        self.timeout = timeout or settings.request_timeout

        if not self.token:
            raise ConfigurationError("Kontext API token is required. Set KONTEXT_TOKEN env var.")

    async def query(
        self,
        query: str,
        principal: Principal | None = None,
        limit: int = 8,
        content_kinds: list[str] | None = None,
        metadata_match: dict[str, Any] | None = None,
        source_scope: list[dict[str, Any]] | None = None,
        source_collections: list[str] | None = None,
        memory: dict[str, Any] | None = None,
        group_by_entity: bool = False,
    ) -> QueryResult:
        """Execute a context query via the MCP `query_context` tool."""
        settings = get_settings()

        request: dict[str, Any] = {
            "query": query,
            "principal": {
                "external_id": (principal.external_id if principal else settings.bot_principal_id),
                "display_name": (
                    principal.display_name if principal else settings.bot_display_name
                ),
                "roles": (principal.roles if principal else settings.bot_roles),
            },
            "limit": max(1, min(limit, 20)),
            "group_by_entity": group_by_entity,
        }
        if content_kinds:
            request["content_kinds"] = content_kinds
        if metadata_match:
            request["metadata_match"] = metadata_match
        if source_scope:
            request["source_scope"] = source_scope
        if source_collections is not None:
            request["source_collections"] = source_collections
        if memory:
            request["memory"] = memory

        data = await self._call_query_context(request)
        return QueryResult(
            audit_id=UUID(data["audit_id"]),
            items=[ContextItem(**item) for item in data.get("items", [])],
            permission_counters=data.get("permission_counters", {}),
        )

    async def _call_query_context(self, request: dict[str, Any]) -> dict[str, Any]:
        # Imported lazily so the bot still starts if the `mcp` extra is absent and the
        # user is on the REST transport.
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as exc:  # pragma: no cover - depends on optional install
            raise KontextAPIError(
                "MCP transport requires the 'mcp' package. Run `poetry install` / "
                "`uv sync`, or set RETRIEVAL_TRANSPORT=rest."
            ) from exc

        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with streamablehttp_client(self.mcp_url, headers=headers) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "query_context", arguments={"request": request}
                    )
        except KontextAPIError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize transport errors
            raise KontextAPIError(f"MCP query_context failed: {exc}") from exc

        if getattr(result, "isError", False):
            raise KontextAPIError(f"MCP query_context error: {_result_text(result)}")
        return _extract_response(result)


def _extract_response(result: object) -> dict[str, Any]:
    """Pull the ContextQueryResponse dict out of a CallToolResult.

    FastMCP returns a Pydantic model as `structuredContent`; depending on SDK/version
    it may be the object directly or wrapped as `{"result": {...}}`. Fall back to
    parsing the first text content block as JSON.
    """
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        typed = cast(dict[str, Any], structured)
        if "items" in typed and "audit_id" in typed:
            return typed
        inner = typed.get("result")
        if isinstance(inner, dict):
            return cast(dict[str, Any], inner)
        return typed

    import json

    text = _result_text(result)
    if text:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return cast(dict[str, Any], parsed)
    raise KontextAPIError("MCP query_context returned no parseable response")


def _result_text(result: object) -> str:
    content = getattr(result, "content", None)
    if isinstance(content, list):
        for block in cast(list[Any], content):
            text = getattr(block, "text", None)
            if isinstance(text, str) and text:
                return text
    return ""
