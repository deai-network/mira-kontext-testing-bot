"""Tests for chat intent routing."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest
from rich.console import Console

from mira_kontext_testing_bot.chat_interface import ChatInterface
from mira_kontext_testing_bot.intent_classifier import IntentDecision
from mira_kontext_testing_bot.models import IngestResult, Principal, Project, QueryResult, Session
from mira_kontext_testing_bot.session import ChatContext
from mira_kontext_testing_bot.web_fetcher import WebFetchError


@dataclass
class FakeMemoryManager:
    stored_messages: list[tuple[str, str]]

    async def store_message(
        self,
        context: ChatContext,
        role: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.stored_messages.append((role, content))
        return {}

    async def build_context_pack(
        self,
        query: str,
        context: ChatContext,
        include_memory: bool = True,
        include_sources: bool = True,
    ) -> dict[str, object]:
        return {
            "query": query,
            "memory_items": [],
            "source_items": [],
            "combined_context": "",
        }


class FakeClient:
    def __init__(self) -> None:
        self.ingests: list[dict[str, object]] = []
        self.list_sources_calls: list[Principal] = []
        self.query_calls: list[dict[str, object]] = []
        self.source_collections_supported: bool | None = True

    async def ingest_record(self, **kwargs: object) -> IngestResult:
        self.ingests.append(kwargs)
        return IngestResult(
            content_item_id=uuid4(),
            source_record_id=uuid4(),
            checksum="abc123",
            status="created",
        )

    async def list_sources(self, principal: Principal | None = None) -> list[dict[str, object]]:
        if principal is not None:
            self.list_sources_calls.append(principal)
        return [
            {
                "source_system": "test",
                "source_object_type": "note",
                "source_object_id": "source-1",
                "source_version": None,
            }
        ]

    async def query(self, **kwargs: object) -> QueryResult:
        self.query_calls.append(kwargs)
        return QueryResult(
            audit_id=uuid4(),
            items=[],
            permission_counters={},
        )


class FakeClassifier:
    def __init__(self, decision: IntentDecision) -> None:
        self.decision = decision
        self.messages: list[str] = []

    async def classify(self, message: str) -> IntentDecision:
        self.messages.append(message)
        return self.decision


class FakeWebFetcher:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail

    def is_configured(self) -> bool:
        return True

    async def search_and_ingest(
        self,
        query: str,
        client: object,
        context: ChatContext,
        max_results: int = 3,
    ) -> list[dict[str, object]]:
        self.calls.append(query)
        if self.fail:
            raise WebFetchError("Firecrawl search failed: rate limited")
        return [
            {
                "title": "P&G Supply Chain Overview",
                "url": "https://example.com/pg",
                "ingest_status": "created",
                "content_length": 1200,
            }
        ]


def _interface(decision: IntentDecision, *, mode: str = "full") -> tuple[ChatInterface, FakeClient]:
    interface = ChatInterface()
    interface.console = Console(record=True)
    project = Project(external_id="project-a")
    session = Session(external_id="session-a", project_external_id="project-a")
    principal = Principal(external_id="t1", display_name="T1")
    interface.current_context = ChatContext(
        project=project,
        session=session,
        principal=principal,
        mode=mode,  # type: ignore[arg-type]
        private_source_collection_external_id="user-t1-private" if mode == "memory_only" else None,
    )
    client = FakeClient()
    interface.client = client  # type: ignore[assignment]
    interface.memory_manager = FakeMemoryManager(stored_messages=[])  # type: ignore[assignment]
    interface.intent_classifier = FakeClassifier(decision)  # type: ignore[assignment]
    return interface, client


def test_interactive_ingest_blank_collection_uses_private_default_payload() -> None:
    interface, _ = _interface(IntentDecision(intent="chat"))

    collection_external_id, target_label = interface._resolve_ingest_collection("")

    assert collection_external_id is None
    assert target_label == "user-t1-private (private default)"


def test_interactive_ingest_named_collection_passes_collection_id() -> None:
    interface, _ = _interface(IntentDecision(intent="chat"))

    collection_external_id, target_label = interface._resolve_ingest_collection("bmw_rd_patents")

    assert collection_external_id == "bmw_rd_patents"
    assert target_label == "bmw_rd_patents"


@pytest.mark.asyncio
async def test_chat_ingest_intent_writes_to_private_default_without_collection_id() -> None:
    interface, client = _interface(
        IntentDecision(
            intent="ingest_source",
            confidence=0.96,
            title="Supply chain dataset",
            content="Full supply chain dataset",
            source_system="chat",
            source_object_type="note",
            source_object_id="supply-chain-dataset",
        )
    )

    await interface.handle_chat_message("please ingest this: Full supply chain dataset")

    assert len(client.ingests) == 1
    ingest = client.ingests[0]
    assert ingest["principal"] == interface.current_context.principal
    assert ingest["collection_external_id"] is None
    assert ingest["content"] == "Full supply chain dataset"


@pytest.mark.asyncio
async def test_chat_ingest_intent_uses_named_collection_when_classifier_provides_one() -> None:
    interface, client = _interface(
        IntentDecision(
            intent="ingest_source",
            confidence=0.96,
            title="Department dataset",
            content="Department source text",
            collection_external_id="bmw_rd_patents",
        )
    )

    await interface.handle_chat_message("store this in bmw_rd_patents: Department source text")

    assert client.ingests[0]["collection_external_id"] == "bmw_rd_patents"


@pytest.mark.asyncio
async def test_blank_user_ingest_intent_still_writes_private_default() -> None:
    interface, client = _interface(
        IntentDecision(
            intent="ingest_source",
            confidence=0.95,
            title="Private note",
            content="Private text",
        ),
        mode="memory_only",
    )

    await interface.handle_chat_message("save this private text")

    assert client.ingests[0]["collection_external_id"] is None


@pytest.mark.asyncio
async def test_non_explicit_ingest_prediction_falls_back_to_chat() -> None:
    interface, client = _interface(
        IntentDecision(
            intent="ingest_source",
            confidence=0.97,
            title="Draft",
            content="Draft content",
        )
    )
    interface.llm = object()

    async def fake_generate_response(message: str, context_pack: dict[str, object]) -> str:
        return "chat response"

    interface._generate_response = fake_generate_response  # type: ignore[method-assign]

    await interface.handle_chat_message("draft a dataset I could ingest later")

    assert client.ingests == []


@pytest.mark.asyncio
async def test_list_sources_intent_routes_to_existing_client_method() -> None:
    interface, client = _interface(IntentDecision(intent="list_sources", confidence=0.9))

    await interface.handle_chat_message("show my sources")

    assert client.list_sources_calls == [interface.current_context.principal]


@pytest.mark.asyncio
async def test_blank_user_query_sources_intent_is_scoped_to_private_collection() -> None:
    interface, client = _interface(
        IntentDecision(intent="query_sources", confidence=0.95, query="supply chain"),
        mode="memory_only",
    )

    await interface.handle_chat_message("can we do supply chain analysis?")

    assert client.query_calls[0]["source_collections"] == ["user-t1-private"]


@pytest.mark.asyncio
async def test_web_search_intent_routes_to_existing_web_fetch_flow() -> None:
    interface, _ = _interface(
        IntentDecision(intent="web_search", confidence=0.96, query="p&g supply chain")
    )
    fake_fetcher = FakeWebFetcher()
    interface.web_fetcher = fake_fetcher  # type: ignore[assignment]

    await interface.handle_chat_message("please research p&g supply chain online")

    assert fake_fetcher.calls == ["p&g supply chain"]


@pytest.mark.asyncio
async def test_blank_user_web_search_intent_ingests_into_private_context() -> None:
    interface, _ = _interface(
        IntentDecision(intent="web_search", confidence=0.96, query="p&g supply chain"),
        mode="memory_only",
    )
    fake_fetcher = FakeWebFetcher()
    interface.web_fetcher = fake_fetcher  # type: ignore[assignment]

    await interface.handle_chat_message("please research p&g supply chain online")

    assert fake_fetcher.calls == ["p&g supply chain"]
    assert interface.current_context is not None
    assert interface.current_context.metadata["last_web_search"]["query"] == "p&g supply chain"


@pytest.mark.asyncio
async def test_store_this_info_after_web_search_reports_already_ingested() -> None:
    interface, _ = _interface(IntentDecision(intent="chat", confidence=0.0))
    assert interface.current_context is not None
    interface.current_context.metadata["last_web_search"] = {
        "query": "p&g supply chain",
        "succeeded_count": 1,
        "failed_count": 0,
        "collection_label": "user-t1-private",
        "results": [
            {
                "title": "P&G Supply Chain Overview",
                "url": "https://example.com/pg",
            }
        ],
    }

    await interface.handle_chat_message("can you store this info in source endpoint?")

    output = interface.console.export_text()
    assert "Already stored" in output
    assert "user-t1-private" in output


@pytest.mark.asyncio
async def test_web_search_errors_are_reported_without_crashing_chat() -> None:
    interface, _ = _interface(
        IntentDecision(intent="web_search", confidence=0.96, query="p&g supply chain")
    )
    interface.web_fetcher = FakeWebFetcher(fail=True)  # type: ignore[assignment]

    await interface.handle_chat_message("research p&g supply chain online")

    output = interface.console.export_text()
    assert "Web search failed" in output
    assert "rate limited" in output


@pytest.mark.asyncio
async def test_explicit_ingest_after_web_search_is_not_hijacked_by_store_confirmation() -> None:
    interface, client = _interface(
        IntentDecision(
            intent="ingest_source",
            confidence=0.97,
            title="New dataset",
            content="New data",
        )
    )
    assert interface.current_context is not None
    interface.current_context.metadata["last_web_search"] = {
        "query": "p&g supply chain",
        "succeeded_count": 1,
        "failed_count": 0,
        "collection_label": "user-t1-private",
        "results": [],
    }

    await interface.handle_chat_message("save this new dataset: New data")

    assert len(client.ingests) == 1
    output = interface.console.export_text()
    assert "Already stored" not in output


@pytest.mark.asyncio
async def test_blank_user_sources_fail_closed_when_source_collections_are_unsupported() -> None:
    interface, client = _interface(IntentDecision(intent="chat", confidence=0.0), mode="memory_only")
    client.source_collections_supported = False

    await interface.handle_sources()

    assert client.list_sources_calls == []
    output = interface.console.export_text()
    assert "source collection isolation" in output
