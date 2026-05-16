"""
Example: Multi-User Scenario Testing

This example demonstrates different user personas accessing the API
and verifies proper tenant isolation and role-based access control.
"""

import asyncio
from typing import Any

from mira_kontext_testing_bot.client import KontextClient
from mira_kontext_testing_bot.config import load_env_file
from mira_kontext_testing_bot.models import Principal, Project, Session


async def admin_user_scenario(client: KontextClient) -> dict[str, Any]:
    """Admin user can ingest content and query across all sources."""
    print("\n--- Admin User Scenario ---")

    # Admin ingests confidential content
    result = await client.ingest_record(
        content="Confidential strategic plan for 2026",
        source_system="internal-docs",
        source_object_type="strategy",
        source_object_id="strategic-plan-2026",
        title="Strategic Plan 2026",
        metadata={
            "confidentiality": "restricted",
            "acl": {
                "permission_status": "known",
                "allowed_roles": ["admin"],
                "denied_roles": ["external_partner"],
            },
        },
    )
    print(f"Admin ingested: {result.status}")

    # Query as admin
    query_result = await client.query(
        query="strategic plan",
        principal=Principal(external_id="admin@company.com", roles=["admin"]),
        limit=5,
    )
    print(f"Admin query returned {len(query_result.items)} items")

    return {
        "role": "admin",
        "can_ingest": True,
        "query_results": len(query_result.items),
    }


async def external_partner_scenario(client: KontextClient) -> dict[str, Any]:
    """External partner has restricted access."""
    print("\n--- External Partner Scenario ---")

    # Partner queries for strategic content (should be filtered)
    query_result = await client.query(
        query="strategic plan",
        principal=Principal(
            external_id="partner@external.com",
            roles=["external_partner"],
        ),
        limit=5,
    )

    denied = sum(query_result.permission_counters.values())
    print(f"Partner query returned {len(query_result.items)} items")
    print(f"Items filtered by permissions: {denied}")

    return {
        "role": "external_partner",
        "query_results": len(query_result.items),
        "filtered_items": denied,
    }


async def analyst_user_scenario(client: KontextClient) -> dict[str, Any]:
    """Analyst user queries data and stores findings in memory."""
    print("\n--- Analyst User Scenario ---")

    # Create project-specific context
    project_id = "supply-chain-analysis"
    project = Project(external_id=project_id, title="Supply Chain Analysis")
    session = Session(
        external_id="analysis-session-1",
        title="Analysis Session 1",
        project_external_id=project_id,
    )
    principal = Principal(
        external_id="analyst@company.com",
        display_name="Data Analyst",
        roles=["analyst"],
    )

    # Store analysis notes in memory
    await client.write_memory_message(
        message="Starting analysis of supplier risk data for Q2",
        role="user",
        project=project,
        session=session,
        principal=principal,
    )

    # Query for relevant context
    query_result = await client.query(
        query="supplier risk Q2",
        principal=principal,
        limit=5,
        content_kinds=["source_record"],
    )
    print(f"Analyst found {len(query_result.items)} relevant sources")

    # Store findings
    await client.write_memory_message(
        message=f"Found {len(query_result.items)} relevant sources about supplier risk",
        role="assistant",
        project=project,
        session=session,
        principal=principal,
        metadata={"audit_id": str(query_result.audit_id)},
    )

    # Retrieve conversation memory
    recent = await client.get_recent_memory(
        project_external_id=project_id,
        session_external_id=session.external_id,
        limit=10,
    )
    print(f"Analyst has {len(recent)} messages in conversation memory")

    return {
        "role": "analyst",
        "project": project_id,
        "sources_found": len(query_result.items),
        "memory_messages": len(recent),
    }


async def multi_session_conversation(client: KontextClient) -> dict[str, Any]:
    """Test isolation between multiple sessions for the same user."""
    print("\n--- Multi-Session Conversation Scenario ---")

    project = Project(external_id="multi-session-test", title="Multi-Session Test")
    principal = Principal(external_id="test-user", display_name="Test User")

    # Create two sessions
    session_a = Session(
        external_id="session-a",
        title="Topic A Discussion",
        project_external_id=project.external_id,
    )
    session_b = Session(
        external_id="session-b",
        title="Topic B Discussion",
        project_external_id=project.external_id,
    )

    # Write to session A
    await client.write_memory_message(
        message="Discussion about Topic A: project planning",
        role="user",
        project=project,
        session=session_a,
        principal=principal,
    )

    # Write to session B
    await client.write_memory_message(
        message="Discussion about Topic B: budget review",
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

    # Check isolation
    a_contents = [m.content for m in recent_a]
    b_contents = [m.content for m in recent_b]

    a_has_b = any("Topic B" in c for c in a_contents)
    b_has_a = any("Topic A" in c in b_contents)

    print(f"Session A contains {len(recent_a)} messages")
    print(f"Session B contains {len(recent_b)} messages")
    print(f"Cross-contamination: {a_has_b or b_has_a}")

    return {
        "session_a_count": len(recent_a),
        "session_b_count": len(recent_b),
        "isolated": not (a_has_b or b_has_a),
    }


async def main():
    """Run all user scenarios."""
    load_env_file()

    async with KontextClient() as client:
        print("=" * 50)
        print("Multi-User Scenario Testing")
        print("=" * 50)

        # Run each scenario
        results = {
            "admin": await admin_user_scenario(client),
            "partner": await external_partner_scenario(client),
            "analyst": await analyst_user_scenario(client),
            "multi_session": await multi_session_conversation(client),
        }

        # Summary
        print("\n" + "=" * 50)
        print("SCENARIO SUMMARY")
        print("=" * 50)

        for scenario_name, data in results.items():
            print(f"\n{scenario_name}:")
            for key, value in data.items():
                print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
