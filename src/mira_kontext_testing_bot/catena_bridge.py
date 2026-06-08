"""Orchestration between Catena AI chat and Kontext conversation memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catena_client import CatenaChatResult, CatenaClient, CatenaUser
from .client import KontextClient
from .config import get_settings
from .models import Principal
from .session import ChatContext


@dataclass(frozen=True)
class MemoryContextPreview:
    """Recent Kontext memory loaded before a Catena chat turn."""

    recent_messages: list[dict[str, str]]
    search_hits: list[dict[str, Any]]


@dataclass(frozen=True)
class IntegratedTurnResult:
    """Outcome of one user message routed through Catena with Kontext memory."""

    catena: CatenaChatResult
    thread_id: str
    memory_preview: MemoryContextPreview
    kontext_user_stored: dict[str, Any]
    kontext_assistant_stored: dict[str, Any]


class CatenaMemoryBridge:
    """Persist conversation memory in Kontext while using Catena for answers."""

    def __init__(self, catena: CatenaClient, kontext: KontextClient) -> None:
        self.catena = catena
        self.kontext = kontext
        self.settings = get_settings()
        self._catena_user: CatenaUser | None = None

    async def resolve_catena_user(self) -> CatenaUser:
        if self._catena_user is None:
            self._catena_user = await self.catena.me()
        return self._catena_user

    def principal_from_catena_user(self, user: CatenaUser) -> Principal:
        roles = ["admin"] if user.is_admin else ["user"]
        return Principal(
            external_id=f"catena:user:{user.id}",
            display_name=user.display_name,
            email=user.email,
            roles=roles,
            metadata={"catena_user_id": user.id, "company_name": user.company_name},
        )

    async def sync_context_from_catena(self, context: ChatContext) -> ChatContext:
        """Align Kontext principal (and optionally project title) with Catena /auth/me."""
        user = await self.resolve_catena_user()
        context.principal = self.principal_from_catena_user(user)
        if user.company_name and not context.project.title:
            context.project.title = user.company_name
        return context

    async def load_memory_preview(
        self,
        context: ChatContext,
        query: str,
        *,
        recent_limit: int = 10,
        search_limit: int = 5,
        include_search: bool = True,
    ) -> MemoryContextPreview:
        recent = await self.kontext.get_recent_memory(
            project_external_id=context.project.external_id,
            session_external_id=context.session.external_id,
            principal_external_id=context.principal.external_id,
            limit=recent_limit,
        )
        recent_payload = [{"role": msg.role, "content": msg.content} for msg in recent]

        search_hits: list[dict[str, Any]] = []
        if include_search and self.settings.catena_memory_search_before_chat:
            search_hits = await self.kontext.search_memory(
                query=query,
                project_external_id=context.project.external_id,
                session_external_id=context.session.external_id,
                principal_external_id=context.principal.external_id,
                limit=search_limit,
            )

        return MemoryContextPreview(
            recent_messages=recent_payload,
            search_hits=search_hits,
        )

    async def run_turn(
        self,
        context: ChatContext,
        message: str,
        *,
        flow_id: str | None = None,
    ) -> IntegratedTurnResult:
        """Store user message, call Catena, store assistant reply in Kontext."""
        await self.sync_context_from_catena(context)

        memory_preview = await self.load_memory_preview(context, message)

        user_record = await self.kontext.write_memory_message(
            message=message,
            role="user",
            project=context.project,
            session=context.session,
            principal=context.principal,
            metadata={
                "source_system": "catena",
                "integration": "catena-kontext-harness",
            },
        )

        thread_id = context.session.external_id
        catena_result = await self.catena.chat(
            message,
            thread_id=thread_id,
            flow_id=flow_id,
        )

        if catena_result.thread_id and catena_result.thread_id != thread_id:
            context.session.external_id = catena_result.thread_id
            thread_id = catena_result.thread_id

        assistant_record = await self.kontext.write_memory_message(
            message=catena_result.text,
            role="assistant",
            project=context.project,
            session=context.session,
            principal=context.principal,
            metadata={
                "source_system": "catena",
                "flow_type": catena_result.flow_type,
                "catena_thread_id": catena_result.thread_id,
            },
        )

        return IntegratedTurnResult(
            catena=catena_result,
            thread_id=thread_id,
            memory_preview=memory_preview,
            kontext_user_stored=user_record,
            kontext_assistant_stored=assistant_record,
        )
