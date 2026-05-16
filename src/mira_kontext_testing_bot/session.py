"""Chat session management for the testing bot."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from .config import get_settings
from .models import Message, Principal, Project, Session

IsolationMode = Literal["full", "memory_only"]


@dataclass
class ChatContext:
    """Current chat context including project, session, and history."""

    project: Project
    session: Session
    principal: Principal
    messages: list[Message] = field(default_factory=lambda: [])
    metadata: dict[str, Any] = field(default_factory=lambda: {})
    mode: IsolationMode = "full"
    source_collection_external_ids: list[str] | None = None
    private_source_collection_external_id: str | None = None

    @property
    def allows_sources(self) -> bool:
        """Whether this context may query source records through API policy."""
        return self.mode == "full"

    def add_message(self, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        """Add a message to the conversation history."""
        self.messages.append(
            Message(
                role=role,  # type: ignore[arg-type]
                content=content,
                metadata=metadata or {},
            )
        )

    def get_recent_context(self, window: int = 10) -> list[Message]:
        """Get the most recent messages for context window."""
        return self.messages[-window:] if self.messages else []

    def to_api_format(self) -> dict[str, Any]:
        """Convert to API memory filter format."""
        return {
            "project_external_id": self.project.external_id,
            "session_external_id": self.session.external_id,
            "principal_external_id": self.principal.external_id,
        }

    @property
    def source_collections_for_query(self) -> list[str] | None:
        """Collection scope to pass to query endpoints."""
        return self.source_collection_external_ids


class SessionManager:
    """Manages chat sessions and their context."""

    def __init__(self) -> None:
        self._active_sessions: dict[str, ChatContext] = {}
        self._known_users: dict[str, Principal] = {}
        self._default_context: ChatContext | None = None

    def _generate_session_id(self, project_id: str) -> str:
        """Generate a unique session ID."""
        timestamp = int(time.time())
        random_suffix = uuid.uuid4().hex[:8]
        return f"{project_id}-session-{timestamp}-{random_suffix}"

    def get_or_create_default_context(self) -> ChatContext:
        """Get or create the default chat context."""
        if self._default_context is None:
            settings = get_settings()

            project = Project(
                external_id=settings.default_project_id,
                title=settings.default_project_title,
            )

            session = Session(
                external_id=settings.default_session_id,
                title=settings.default_session_title,
                project_external_id=project.external_id,
            )

            principal = self.create_principal(
                external_id=settings.bot_principal_id,
                display_name=settings.bot_display_name,
                roles=settings.bot_roles,
            )

            self._default_context = ChatContext(
                project=project,
                session=session,
                principal=principal,
            )

        return self._default_context

    def create_project(
        self,
        external_id: str,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Project:
        """Create a new project."""
        return Project(
            external_id=external_id,
            title=title or external_id,
            metadata=metadata or {},
        )

    def create_session(
        self,
        project: Project,
        external_id: str | None = None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """Create a new session within a project."""
        session_id = external_id or self._generate_session_id(project.external_id)
        return Session(
            external_id=session_id,
            title=title or session_id,
            project_external_id=project.external_id,
            metadata=metadata or {},
        )

    def create_principal(
        self,
        external_id: str,
        display_name: str | None = None,
        email: str | None = None,
        roles: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Principal:
        """Create or update a known user principal."""
        existing = self._known_users.get(external_id)
        principal = Principal(
            external_id=external_id,
            display_name=display_name or (existing.display_name if existing else None),
            email=email or (existing.email if existing else None),
            roles=roles if roles is not None else (existing.roles if existing else []),
            metadata=metadata or (existing.metadata if existing else {}),
        )
        self._known_users[external_id] = principal
        return principal

    def create_context(
        self,
        project: Project,
        session: Session,
        principal: Principal | None = None,
        *,
        mode: IsolationMode = "full",
        source_collection_external_ids: list[str] | None = None,
        private_source_collection_external_id: str | None = None,
    ) -> ChatContext:
        """Create a new chat context."""
        if principal is None:
            settings = get_settings()
            principal = Principal(
                external_id=settings.bot_principal_id,
                display_name=settings.bot_display_name,
                roles=settings.bot_roles,
            )

        self._known_users[principal.external_id] = principal
        context = ChatContext(
            project=project,
            session=session,
            principal=principal,
            mode=mode,
            source_collection_external_ids=source_collection_external_ids,
            private_source_collection_external_id=private_source_collection_external_id,
        )

        # Store in active sessions
        self._active_sessions[session.external_id] = context
        return context

    def create_blank_context_for_user(
        self,
        project: Project,
        principal: Principal,
        *,
        session_title: str | None = None,
    ) -> ChatContext:
        """Create a fresh session for a user with no local memory history."""
        session = self.create_session(
            project=project,
            title=session_title or f"Blank session for {principal.external_id}",
            metadata={"blank_memory": True},
        )
        private_collection_id = self.private_collection_external_id(principal)
        return self.create_context(
            project=project,
            session=session,
            principal=principal,
            mode="memory_only",
            source_collection_external_ids=[private_collection_id],
            private_source_collection_external_id=private_collection_id,
        )

    def private_collection_external_id(self, principal: Principal) -> str:
        """Match the API's deterministic private collection id for a principal."""
        normalized = "".join(
            character.lower() if character.isalnum() or character in {"_", "-"} else "-"
            for character in principal.external_id
        ).strip("-")
        return f"user-{normalized or 'principal'}-private"

    def get_context(self, session_id: str) -> ChatContext | None:
        """Retrieve an active chat context by session ID."""
        return self._active_sessions.get(session_id)

    def list_active_sessions(self) -> list[tuple[str, str, str, str]]:
        """List active sessions with (session_id, project_id, title, user_id)."""
        return [
            (
                session_id,
                ctx.project.external_id,
                ctx.session.title or session_id,
                ctx.principal.external_id,
            )
            for session_id, ctx in self._active_sessions.items()
        ]

    def list_users(self) -> list[tuple[str, str, str]]:
        """List known users with (external_id, display_name, roles)."""
        return [
            (
                user.external_id,
                user.display_name or "",
                ", ".join(user.roles),
            )
            for user in self._known_users.values()
        ]

    def clear_context(self, session_id: str) -> bool:
        """Clear a specific session context."""
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
            return True
        return False

    def clear_all_contexts(self) -> None:
        """Clear all session contexts."""
        self._active_sessions.clear()
        self._default_context = None

    def get_conversation_history(self, session_id: str) -> list[Message]:
        """Get conversation history for a session."""
        context = self.get_context(session_id)
        if context:
            return list(context.messages)
        return []


# Global session manager instance
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get or create the global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
