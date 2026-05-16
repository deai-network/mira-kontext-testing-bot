"""Memory management for the testing bot."""

from __future__ import annotations

from typing import Any

from .client import KontextClient
from .models import MemoryMessage, QueryResult
from .session import ChatContext


class MemoryManager:
    """Manages conversation memory using the Kontext API."""

    def __init__(self, client: KontextClient) -> None:
        self.client = client

    async def store_message(
        self,
        context: ChatContext,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store a message in conversation memory."""
        msg_metadata = metadata or {}
        msg_metadata["stored_by"] = "testing_bot"

        return await self.client.write_memory_message(
            message=content,
            role=role,
            project=context.project,
            session=context.session,
            principal=context.principal,
            metadata=msg_metadata,
        )

    async def retrieve_recent(
        self,
        context: ChatContext,
        limit: int = 10,
    ) -> list[MemoryMessage]:
        """Retrieve recent messages from memory."""
        return await self.client.get_recent_memory(
            project_external_id=context.project.external_id,
            session_external_id=context.session.external_id,
            principal_external_id=context.principal.external_id,
            limit=limit,
        )

    async def search_memory(
        self,
        query: str,
        context: ChatContext,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """Search conversation memory semantically."""
        return await self.client.search_memory(
            query=query,
            project_external_id=context.project.external_id,
            session_external_id=context.session.external_id,
            principal_external_id=context.principal.external_id,
            limit=limit,
        )

    async def query_with_memory(
        self,
        query: str,
        context: ChatContext,
        limit: int = 8,
        content_kinds: list[str] | None = None,
    ) -> QueryResult:
        """Execute a context query including conversation memory."""
        kinds = content_kinds or ["source_record", "conversation_message"]

        return await self.client.query(
            query=query,
            principal=context.principal,
            limit=limit,
            content_kinds=kinds,
            source_collections=context.source_collections_for_query,
            memory=context.to_api_format(),
        )

    async def build_context_pack(
        self,
        query: str,
        context: ChatContext,
        include_memory: bool = True,
        include_sources: bool = True,
        memory_limit: int = 5,
        source_limit: int = 5,
    ) -> dict[str, Any]:
        """Build a comprehensive context pack for the query."""
        result: dict[str, Any] = {
            "query": query,
            "project_id": context.project.external_id,
            "session_id": context.session.external_id,
            "memory_items": [],
            "source_items": [],
            "combined_context": "",
        }

        if include_memory:
            # Get recent conversation context
            recent = await self.retrieve_recent(context, limit=memory_limit)
            result["memory_items"] = [
                {"role": msg.role, "content": msg.content} for msg in recent
            ]

        if include_sources:
            # Query for relevant sources
            query_result = await self.query_with_memory(
                query=query,
                context=context,
                limit=source_limit,
                content_kinds=["source_record"],
            )
            result["source_items"] = [
                {
                    "title": item.title,
                    "snippet": item.snippet,
                    "short_id": item.short_id,
                    "citations": item.citations,
                }
                for item in query_result.items
            ]
            result["audit_id"] = str(query_result.audit_id)

        # Build combined context string
        context_parts: list[str] = []

        if result["source_items"]:
            context_parts.append("## Relevant Sources")
            for i, item in enumerate(result["source_items"], 1):
                context_parts.append(f"{i}. {item['title'] or 'Untitled'}")
                context_parts.append(f"   {item['snippet']}")
                if item["citations"]:
                    citation = item["citations"][0]
                    if isinstance(citation, dict):
                        source_system = citation.get("source_system", "unknown")
                    else:
                        source_system = "unknown"
                    context_parts.append(f"   [Source: {source_system}]")

        if result["memory_items"]:
            context_parts.append("\n## Conversation History")
            for msg in result["memory_items"]:
                role_label = msg["role"].capitalize()
                context_parts.append(f"{role_label}: {msg['content']}")

        result["combined_context"] = "\n".join(context_parts)

        return result

    def format_context_for_display(self, context_pack: dict[str, Any]) -> str:
        """Format a context pack for display in chat."""
        lines: list[str] = []

        if context_pack["source_items"]:
            lines.append("[Retrieved Sources]")
            for i, item in enumerate(context_pack["source_items"], 1):
                title = item.get("title") or "Untitled"
                snippet = item.get("snippet", "")[:150]
                if len(item.get("snippet", "")) > 150:
                    snippet += "..."
                lines.append(f"  {i}. {title}")
                lines.append(f"     {snippet}")
            lines.append("")

        if context_pack["memory_items"]:
            lines.append(f"[Memory: {len(context_pack['memory_items'])} recent messages]")
            lines.append("")

        return "\n".join(lines)
