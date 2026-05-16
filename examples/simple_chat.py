"""Simple example of using the testing bot as a library."""

import asyncio

from mira_kontext_testing_bot.client import KontextClient
from mira_kontext_testing_bot.config import load_env_file
from mira_kontext_testing_bot.models import Principal, Project, Session
from mira_kontext_testing_bot.session import get_session_manager


async def simple_conversation():
    """Example of a simple conversation with the API."""
    # Load environment variables
    load_env_file()

    # Create client
    async with KontextClient() as client:
        # Check health
        health = await client.health_check()
        print(f"API Health: {health}")

        # Create a project and session
        session_mgr = get_session_manager()
        project = session_mgr.create_project(
            external_id="example-project",
            title="Example Project",
        )
        session = session_mgr.create_session(
            project=project,
            external_id="example-session",
            title="Example Session",
        )

        principal = Principal(
            external_id="example-user",
            display_name="Example User",
            roles=["tester"],
        )

        # Write some messages to memory
        messages = [
            ("user", "What is the status of Project Atlas?"),
            ("assistant", "Project Atlas is on track for delivery next month."),
            ("user", "Are there any risks I should be aware of?"),
        ]

        for role, content in messages:
            result = await client.write_memory_message(
                message=content,
                role=role,
                project=project,
                session=session,
                principal=principal,
            )
            print(f"Stored {role} message: {result['message_id']}")

        # Query for recent memory
        recent = await client.get_recent_memory(
            project_external_id=project.external_id,
            session_external_id=session.external_id,
            limit=10,
        )
        print(f"\nRetrieved {len(recent)} messages from memory:")
        for msg in recent:
            print(f"  [{msg.role}] {msg.content[:50]}...")

        # Ingest some content
        ingest_result = await client.ingest_record(
            content="Project Atlas is a strategic initiative with Q3 delivery target.",
            source_system="example-docs",
            source_object_type="project-overview",
            source_object_id="atlas-overview",
            title="Project Atlas Overview",
            metadata={"priority": "high"},
        )
        print(f"\nIngested content: {ingest_result.status}")

        # Query the context
        query_result = await client.query(
            query="What is Project Atlas?",
            principal=principal,
            limit=5,
        )
        print(f"\nQuery returned {len(query_result.items)} items:")
        for item in query_result.items:
            print(f"  - {item.title or 'Untitled'} (score: {item.score:.3f})")
            print(f"    {item.snippet[:100]}...")


if __name__ == "__main__":
    asyncio.run(simple_conversation())
