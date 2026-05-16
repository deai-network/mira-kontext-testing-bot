"""Pydantic models for the testing bot."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Project(BaseModel):
    """A conversation project context."""

    model_config = ConfigDict(extra="forbid")

    external_id: str
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    """A conversation session within a project."""

    model_config = ConfigDict(extra="forbid")

    external_id: str
    title: str | None = None
    project_external_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Principal(BaseModel):
    """A principal (user or agent) in the conversation."""

    model_config = ConfigDict(extra="forbid")

    external_id: str
    display_name: str | None = None
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    """A conversation message."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant", "tool"]
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatTurn(BaseModel):
    """A complete chat turn with context."""

    model_config = ConfigDict(extra="forbid")

    message: Message
    project: Project
    session: Session
    principal: Principal


class ContextItem(BaseModel):
    """A context item from the Kontext API."""

    model_config = ConfigDict(extra="forbid")

    content_item_id: UUID
    short_id: str
    title: str | None
    snippet: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=lambda: [])


class QueryResult(BaseModel):
    """Result from a context query."""

    model_config = ConfigDict(extra="forbid")

    audit_id: UUID
    items: list[ContextItem]
    permission_counters: dict[str, int] = Field(default_factory=dict)


class IngestResult(BaseModel):
    """Result from ingesting content."""

    model_config = ConfigDict(extra="forbid")

    content_item_id: UUID
    source_record_id: UUID
    checksum: str
    status: Literal["created", "updated", "unchanged"]
    entity_ids: list[UUID] = Field(default_factory=lambda: [])


class MemoryMessage(BaseModel):
    """A stored conversation message."""

    model_config = ConfigDict(extra="forbid")

    message_id: UUID
    content_item_id: UUID | None = None
    project_id: UUID | None
    session_id: UUID
    principal_id: UUID | None
    role: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ScenarioOutcome(BaseModel):
    """Result of running a test scenario."""

    model_config = ConfigDict(extra="forbid")

    scenario_name: str
    passed: bool
    duration_ms: float
    error_message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SuiteOutcome(BaseModel):
    """Complete test suite results."""

    model_config = ConfigDict(extra="forbid")

    suite_name: str
    results: list[ScenarioOutcome]
    total: int
    passed: int
    failed: int
    duration_ms: float

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100
