"""REPL bootstrap for mira-kontext-testing-bot."""

from pprint import pprint
from uuid import uuid4

from repl_toolkit import NAMESPACE_RESULT_KEY, ReplConfig, ReplLoader


def build_config() -> ReplConfig:
    """Build REPL configuration for the Testing Bot."""

    config = ReplConfig(
        name="Testing Bot REPL",
        description="Interactive shell for testing mira-kontext-api",
        banner_color="green",
        imports={
            "asyncio": (None, None),
            "uuid": (None, ["UUID", "uuid4"]),
            "mira_kontext_testing_bot.config": ("bot_config", ["get_settings", "load_env_file"]),
            "mira_kontext_testing_bot.client": (None, ["KontextClient"]),
            "mira_kontext_testing_bot.models": (
                None,
                [
                    "Project",
                    "Session",
                    "Principal",
                    "Message",
                    "ContextItem",
                    "QueryResult",
                    "IngestResult",
                ],
            ),
            "mira_kontext_testing_bot.session": ("session_mgr", ["get_session_manager"]),
            "mira_kontext_testing_bot.memory_manager": ("MemoryManager", None),
        },
    )

    from mira_kontext_testing_bot.config import get_settings, load_env_file

    load_env_file()
    settings = get_settings()
    print(f"[repl] Loaded settings for API: {settings.kontext_api_url}")

    async def init_client() -> object:
        from mira_kontext_testing_bot.client import KontextClient

        client = KontextClient()
        await client.connect()
        health = await client.health_check()
        ready = await client.ready_check()
        print(f"[repl] API Health: {health}")
        print(f"[repl] API Ready: {ready}")
        return {
            NAMESPACE_RESULT_KEY: client,
            "client": client,
        }

    async def get_client() -> object:
        """Get the API client, initializing it first if needed."""

        return await config.namespace["init_client"]()

    async def quick_query(query: str, limit: int = 5) -> object:
        """Run a query and print compact results."""

        from mira_kontext_testing_bot.models import Principal

        client = await get_client()
        result = await client.query(
            query=query,
            principal=Principal(external_id="repl-user", roles=["tester"]),
            limit=limit,
        )
        print(f"\nQuery: '{query}'")
        print(f"Found {len(result.items)} items")
        for index, item in enumerate(result.items, 1):
            print(f"  {index}. {item.title or 'Untitled'} (score: {item.score:.3f})")
            snippet = item.snippet[:100] + "..." if len(item.snippet) > 100 else item.snippet
            print(f"     {snippet}")
        return result

    async def quick_ingest(
        content: str,
        title: str = "REPL Ingest",
        source_id: str | None = None,
    ) -> object:
        """Ingest content and print the created IDs."""

        client = await get_client()
        sid = source_id or f"repl-{uuid4().hex[:8]}"
        result = await client.ingest_record(
            content=content,
            source_system="repl",
            source_object_type="note",
            source_object_id=sid,
            title=title,
        )
        print(f"Ingested: {result.status}")
        print(f"  Content ID: {result.content_item_id}")
        print(f"  Source ID: {result.source_record_id}")
        return result

    def create_session(project_id: str = "repl-project", session_id: str | None = None) -> object:
        """Create a new project/session context."""

        from mira_kontext_testing_bot.models import Principal
        from mira_kontext_testing_bot.session import get_session_manager

        manager = get_session_manager()
        project = manager.create_project(external_id=project_id, title=f"Project {project_id}")
        session = manager.create_session(
            project=project,
            external_id=session_id or f"session-{uuid4().hex[:8]}",
        )
        principal = Principal(
            external_id=settings.bot_principal_id,
            display_name=settings.bot_display_name,
        )
        context = manager.create_context(project, session, principal)

        print("Created session:")
        print(f"  Project: {project_id}")
        print(f"  Session: {session.external_id}")
        return context

    async def write_message(context: object, message: str, role: str = "user") -> object:
        """Write a message to conversation memory."""

        from mira_kontext_testing_bot.memory_manager import MemoryManager

        client = await get_client()
        memory_manager = MemoryManager(client)
        result = await memory_manager.store_message(
            context=context,
            role=role,
            content=message,
        )
        print(f"Stored message: {result.get('message_id')}")
        return result

    config.async_init["init_client"] = (
        "Initialize Kontext API client and verify connectivity",
        init_client,
    )
    config.helpers = {
        "get_client": get_client,
        "quick_query": quick_query,
        "quick_ingest": quick_ingest,
        "create_session": create_session,
        "write_message": write_message,
        "pprint": pprint,
        "uuid4": uuid4,
        "settings": settings,
    }
    config.suggested_probes = [
        "await init_client()",
        "ctx = create_session('my-project')",
        "await write_message(ctx, 'Hello from REPL')",
        "await quick_query('Project Atlas')",
        "await quick_ingest('Test content', 'Test Title')",
        "sources = await client.list_sources()",
    ]
    return config


if __name__ == "__main__":
    ReplLoader(build_config()).launch()
