"""Test runner for comprehensive API testing scenarios."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Awaitable, Callable
from uuid import uuid4

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .client import KontextClient
from .config import get_settings
from .models import Principal, Project, ScenarioOutcome, Session, SuiteOutcome
from .session import ChatContext, get_session_manager

if TYPE_CHECKING:
    from .client import KontextClient


TestFunc = Callable[[KontextClient, Console], Awaitable[dict[str, Any]]]


class TestScenarios:
    """Collection of test scenarios for the Kontext API."""

    @staticmethod
    async def health_check(client: KontextClient, console: Console) -> dict[str, Any]:
        """Test basic health and readiness endpoints."""
        health = await client.health_check()
        ready = await client.ready_check()

        assert health.get("status") == "ok", f"Health check failed: {health}"
        assert ready.get("status") == "ok", f"Ready check failed: {ready}"

        return {"health": health, "ready": ready}

    @staticmethod
    async def ingestion_cycle(client: KontextClient, console: Console) -> dict[str, Any]:
        """Test full ingestion cycle: create, update, and verify."""
        test_id = f"test-{uuid4().hex[:8]}"

        # Create initial record
        result_create = await client.ingest_record(
            content="Test content for ingestion cycle",
            source_system="test-suite",
            source_object_type="test-record",
            source_object_id=test_id,
            title="Test Record",
            metadata={"test_run": True, "cycle": "create"},
        )
        assert result_create.status == "created", f"Expected 'created', got {result_create.status}"

        # Re-ingest same content (should be unchanged)
        result_unchanged = await client.ingest_record(
            content="Test content for ingestion cycle",
            source_system="test-suite",
            source_object_type="test-record",
            source_object_id=test_id,
            title="Test Record",
        )
        assert (
            result_unchanged.status == "unchanged"
        ), f"Expected 'unchanged', got {result_unchanged.status}"

        # Update content (should update)
        result_update = await client.ingest_record(
            content="Updated test content for ingestion cycle",
            source_system="test-suite",
            source_object_type="test-record",
            source_object_id=test_id,
            title="Test Record (Updated)",
        )
        assert result_update.status == "updated", f"Expected 'updated', got {result_update.status}"

        # Verify in sources list
        sources = await client.list_sources()
        test_sources = [s for s in sources if s.get("source_object_id") == test_id]
        assert len(test_sources) >= 1, "Ingested source not found in sources list"

        return {
            "test_id": test_id,
            "create": result_create.status,
            "unchanged": result_unchanged.status,
            "update": result_update.status,
            "sources_found": len(test_sources),
        }

    @staticmethod
    async def memory_write_and_retrieve(client: KontextClient, console: Console) -> dict[str, Any]:
        """Test conversation memory write and retrieve operations."""
        session_mgr = get_session_manager()
        settings = get_settings()

        # Create test context
        project = session_mgr.create_project(
            external_id=f"test-project-{uuid4().hex[:8]}",
            title="Test Project",
        )
        session = session_mgr.create_session(
            project=project,
            external_id=f"test-session-{uuid4().hex[:8]}",
            title="Test Session",
        )
        principal = Principal(
            external_id=settings.bot_principal_id,
            display_name=settings.bot_display_name,
        )
        context = session_mgr.create_context(project, session, principal)

        # Write messages
        messages_to_write = [
            ("user", "Hello, this is a test message"),
            ("assistant", "I received your test message"),
            ("user", "Can you remember this conversation?"),
        ]

        written_ids: list[str] = []
        for role, content in messages_to_write:
            result = await client.write_memory_message(
                message=content,
                role=role,
                project=context.project,
                session=context.session,
                principal=context.principal,
                metadata={"test": True},
            )
            written_ids.append(str(result.get("message_id")))

        # Retrieve recent memory
        recent = await client.get_recent_memory(
            project_external_id=project.external_id,
            session_external_id=session.external_id,
            limit=10,
        )

        # Verify all messages are retrievable
        retrieved_contents = [msg.content for msg in recent]
        for _, content in messages_to_write:
            assert any(
                content in retrieved for retrieved in retrieved_contents
            ), f"Message not found: {content}"

        return {
            "project_id": project.external_id,
            "session_id": session.external_id,
            "written": len(written_ids),
            "retrieved": len(recent),
            "message_ids": written_ids,
        }

    @staticmethod
    async def memory_search(client: KontextClient, console: Console) -> dict[str, Any]:
        """Test semantic search in conversation memory."""
        session_mgr = get_session_manager()
        settings = get_settings()

        project = session_mgr.create_project(
            external_id=f"search-test-{uuid4().hex[:8]}",
            title="Search Test Project",
        )
        session = session_mgr.create_session(
            project=project,
            external_id=f"search-session-{uuid4().hex[:8]}",
            title="Search Session",
        )
        principal = Principal(
            external_id=settings.bot_principal_id,
            display_name=settings.bot_display_name,
        )
        context = session_mgr.create_context(project, session, principal)

        # Write specific content for search
        test_content = "The quick brown fox jumps over the lazy dog. Unique keyword: XYZZY123"
        await client.write_memory_message(
            message=test_content,
            role="user",
            project=context.project,
            session=context.session,
            principal=context.principal,
        )

        # Search for the unique keyword
        results = await client.search_memory(
            query="XYZZY123",
            project_external_id=project.external_id,
            session_external_id=session.external_id,
            limit=5,
        )

        # Verify search found our message
        found_content = any(
            "XYZZY123" in (item.get("content", "")) for item in results
        )
        assert found_content, "Semantic search did not find the test message"

        return {
            "query": "XYZZY123",
            "results_count": len(results),
            "found_content": found_content,
        }

    @staticmethod
    async def query_with_context(client: KontextClient, console: Console) -> dict[str, Any]:
        """Test context query with sources and memory."""
        settings = get_settings()
        test_id = f"query-test-{uuid4().hex[:8]}"

        # First, ingest some content
        await client.ingest_record(
            content=f"Project Atlas is a critical initiative. Test ID: {test_id}",
            source_system="test-docs",
            source_object_type="document",
            source_object_id=f"doc-{test_id}",
            title="Project Atlas Overview",
            metadata={"project": "Atlas", "test_id": test_id},
        )

        # Query for the content
        result = await client.query(
            query="What is Project Atlas?",
            principal=Principal(
                external_id=settings.bot_principal_id,
                roles=["tester"],
            ),
            limit=5,
            content_kinds=["source_record"],
        )

        assert result.audit_id, "Query did not return an audit ID"
        assert isinstance(result.items, list), "Query did not return items list"

        # Verify we got the Project Atlas content
        atlas_found = any(
            "Project Atlas" in (item.title or "") or "Project Atlas" in item.snippet
            for item in result.items
        )

        return {
            "audit_id": str(result.audit_id),
            "items_returned": len(result.items),
            "atlas_found": atlas_found,
            "permission_counters": result.permission_counters,
        }

    @staticmethod
    async def document_retrieval(client: KontextClient, console: Console) -> dict[str, Any]:
        """Test document retrieval by short ID."""
        # Ingest content first
        test_id = f"doc-test-{uuid4().hex[:8]}"
        ingest_result = await client.ingest_record(
            content=f"Document content for retrieval test: {test_id}",
            source_system="test-docs",
            source_object_type="document",
            source_object_id=f"doc-{test_id}",
            title="Retrieval Test Document",
        )

        # We need the short_id from the content item
        # For now, query for it
        query_result = await client.query(
            query=test_id,
            principal=Principal(external_id="test", roles=["tester"]),
            limit=1,
        )

        assert query_result.items, "No items found for document retrieval test"
        short_id = query_result.items[0].short_id

        # Retrieve the document
        doc = await client.get_document(short_id)
        assert doc is not None, f"Document not found: {short_id}"
        assert test_id in (doc.get("body", "")), "Retrieved document does not contain expected content"

        return {
            "short_id": short_id,
            "content_item_id": str(doc.get("content_item_id")),
            "found_content": test_id in (doc.get("body", "")),
        }

    @staticmethod
    async def audit_logging(client: KontextClient, console: Console) -> dict[str, Any]:
        """Test that audit events are properly recorded."""
        settings = get_settings()

        # Perform a query that should be audited
        query_text = f"Audit test query {uuid4().hex[:8]}"
        result = await client.query(
            query=query_text,
            principal=Principal(
                external_id=settings.bot_principal_id,
                roles=["tester"],
            ),
            limit=3,
        )

        audit_id = str(result.audit_id)

        # Retrieve the audit record
        audit = await client.get_audit(audit_id)
        assert audit is not None, f"Audit record not found: {audit_id}"
        assert (
            audit.get("query") == query_text
        ), f"Audit query mismatch: {audit.get('query')} != {query_text}"

        return {
            "audit_id": audit_id,
            "query": audit.get("query"),
            "filters": audit.get("filters"),
            "principal": audit.get("principal"),
        }

    @staticmethod
    async def role_aware_filtering(client: KontextClient, console: Console) -> dict[str, Any]:
        """Test role-based access control on content."""
        test_id = f"role-test-{uuid4().hex[:8]}"

        # Ingest restricted content
        await client.ingest_record(
            content=f"Restricted content for role test: {test_id}",
            source_system="test-confidential",
            source_object_type="restricted-doc",
            source_object_id=f"restricted-{test_id}",
            title="Restricted Document",
            metadata={
                "confidentiality": "restricted",
                "acl": {
                    "permission_status": "known",
                    "allowed_roles": ["admin"],
                    "denied_roles": ["external_partner"],
                },
            },
        )

        # Query as tester role (should be denied)
        result = await client.query(
            query=test_id,
            principal=Principal(external_id="tester", roles=["external_partner"]),
            limit=5,
        )

        # The item might be found but should be filtered by permissions
        denied_count = (
            result.permission_counters.get("denied_role", 0)
            + result.permission_counters.get("denied_unknown_restricted_acl", 0)
        )

        return {
            "test_id": test_id,
            "items_found": len(result.items),
            "denied_count": denied_count,
            "permission_counters": result.permission_counters,
        }

    @staticmethod
    async def multi_session_isolation(client: KontextClient, console: Console) -> dict[str, Any]:
        """Test that sessions are properly isolated."""
        session_mgr = get_session_manager()
        settings = get_settings()
        test_marker = f"isolation-{uuid4().hex[:8]}"

        # Create two sessions
        project = session_mgr.create_project(external_id=f"iso-project-{test_marker}")
        session_a = session_mgr.create_session(project, external_id=f"session-a-{test_marker}")
        session_b = session_mgr.create_session(project, external_id=f"session-b-{test_marker}")
        principal = Principal(external_id=settings.bot_principal_id)

        # Write to session A
        await client.write_memory_message(
            message=f"Message in session A: {test_marker}",
            role="user",
            project=project,
            session=session_a,
            principal=principal,
        )

        # Write to session B
        await client.write_memory_message(
            message=f"Message in session B: {test_marker}",
            role="user",
            project=project,
            session=session_b,
            principal=principal,
        )

        # Retrieve from session A
        recent_a = await client.get_recent_memory(
            session_external_id=session_a.external_id,
            limit=5,
        )

        # Retrieve from session B
        recent_b = await client.get_recent_memory(
            session_external_id=session_b.external_id,
            limit=5,
        )

        # Verify isolation
        session_a_contents = [m.content for m in recent_a]
        session_b_contents = [m.content for m in recent_b]

        a_has_b = any("session B" in c for c in session_a_contents)
        b_has_a = any("session A" in c for c in session_b_contents)

        return {
            "session_a_messages": len(recent_a),
            "session_b_messages": len(recent_b),
            "cross_contamination": a_has_b or b_has_a,
            "isolated": not (a_has_b or b_has_a),
        }

    @staticmethod
    async def source_scope_filtering(client: KontextClient, console: Console) -> dict[str, Any]:
        """Test source scope filtering in queries."""
        test_id = f"scope-test-{uuid4().hex[:8]}"

        # Ingest from different source systems
        await client.ingest_record(
            content=f"SAP data: {test_id}",
            source_system="sap",
            source_object_type="record",
            source_object_id=f"sap-{test_id}",
            title="SAP Record",
        )

        await client.ingest_record(
            content=f"Salesforce data: {test_id}",
            source_system="salesforce",
            source_object_type="record",
            source_object_id=f"sf-{test_id}",
            title="Salesforce Record",
        )

        # Query with source scope filter
        result = await client.query(
            query=test_id,
            principal=Principal(external_id="test", roles=["tester"]),
            source_scope=[{"source_system": "sap"}],
            limit=5,
        )

        # Verify only SAP results
        all_sap = all(
            any(c.get("source_system") == "sap" for c in item.citations)
            for item in result.items
        )

        return {
            "test_id": test_id,
            "items_returned": len(result.items),
            "all_sap": all_sap,
        }


async def run_test_scenario(
    name: str,
    test_func: TestFunc,
    client: KontextClient,
    console: Console,
) -> ScenarioOutcome:
    """Run a single test scenario and capture results."""
    start = time.perf_counter()
    error: str | None = None
    details: dict[str, Any] = {}

    try:
        console.print(f"[dim]Running {name}...[/dim]")
        details = await test_func(client, console)
        passed = True
    except AssertionError as exc:
        passed = False
        error = f"Assertion failed: {exc}"
    except Exception as exc:
        passed = False
        error = f"{type(exc).__name__}: {exc}"

    duration = (time.perf_counter() - start) * 1000

    return ScenarioOutcome(
        scenario_name=name,
        passed=passed,
        duration_ms=duration,
        error_message=error,
        details=details,
    )


async def run_test_suite(
    console: Console,
    client: KontextClient | None,
    suite_name: str = "full",
) -> None:
    """Run a test suite and display results."""
    if client is None:
        console.print("[red]Not connected to API. Cannot run tests.[/red]")
        return

    # Define available test suites
    suites: dict[str, list[tuple[str, TestFunc]]] = {
        "health": [
            ("Health Check", TestScenarios.health_check),
        ],
        "ingest": [
            ("Ingestion Cycle", TestScenarios.ingestion_cycle),
            ("Source Scope Filtering", TestScenarios.source_scope_filtering),
        ],
        "memory": [
            ("Memory Write/Retrieve", TestScenarios.memory_write_and_retrieve),
            ("Memory Search", TestScenarios.memory_search),
            ("Multi-Session Isolation", TestScenarios.multi_session_isolation),
        ],
        "query": [
            ("Query with Context", TestScenarios.query_with_context),
            ("Document Retrieval", TestScenarios.document_retrieval),
            ("Role-Aware Filtering", TestScenarios.role_aware_filtering),
        ],
        "audit": [
            ("Audit Logging", TestScenarios.audit_logging),
        ],
        "full": [],
    }

    # Build full suite from all tests
    suites["full"] = (
        suites["health"]
        + suites["ingest"]
        + suites["memory"]
        + suites["query"]
        + suites["audit"]
    )

    if suite_name not in suites:
        console.print(f"[red]Unknown test suite: {suite_name}[/red]")
        console.print(f"Available: {', '.join(suites.keys())}")
        return

    test_cases = suites[suite_name]

    console.print(Panel(f"[bold]Running {suite_name.upper()} Test Suite[/bold]", border_style="blue"))

    results: list[ScenarioOutcome] = []
    start_time = time.perf_counter()

    for name, test_func in test_cases:
        result = await run_test_scenario(name, test_func, client, console)
        results.append(result)

        status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        console.print(f"  {status} {name} ({result.duration_ms:.1f}ms)")
        if result.error_message:
            console.print(f"    [dim red]{result.error_message}[/dim red]")

    total_duration = (time.perf_counter() - start_time) * 1000

    suite_result = SuiteOutcome(
        suite_name=suite_name,
        results=results,
        total=len(results),
        passed=sum(1 for r in results if r.passed),
        failed=sum(1 for r in results if not r.passed),
        duration_ms=total_duration,
    )

    # Display summary
    console.print("")
    summary_table = Table(title="Test Suite Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="white")

    summary_table.add_row("Total Tests", str(suite_result.total))
    summary_table.add_row("Passed", f"[green]{suite_result.passed}[/green]")
    summary_table.add_row("Failed", f"[red]{suite_result.failed}[/red]" if suite_result.failed > 0 else "0")
    summary_table.add_row("Success Rate", f"{suite_result.success_rate:.1f}%")
    summary_table.add_row("Total Duration", f"{suite_result.duration_ms:.1f}ms")

    console.print(summary_table)

    if suite_result.failed > 0:
        console.print("\n[yellow]Failed Tests:[/yellow]")
        for result in suite_result.results:
            if not result.passed:
                console.print(f"  [red]- {result.scenario_name}[/red]")
