"""Interactive chat interface for the testing bot."""

from __future__ import annotations

import sys
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .client import KontextClient
from .config import get_settings
from .errors import KontextAPIError
from .llm_client import LLMClient, MockLLMClient, OllamaCloudClient
from .memory_manager import MemoryManager
from .models import Session
from .session import ChatContext, get_session_manager


class ChatInterface:
    """Interactive CLI chat interface."""

    def __init__(self) -> None:
        self.console = Console()
        self.settings = get_settings()
        self.session_manager = get_session_manager()
        self.client: KontextClient | None = None
        self.memory_manager: MemoryManager | None = None
        self.current_context: ChatContext | None = None
        self.llm: Any | None = None

    def print_banner(self) -> None:
        """Print the welcome banner."""
        banner = Panel.fit(
            "[bold blue]Mira Kontext Testing Bot[/bold blue]\n"
            "[dim]Agentic testing interface for the Kontext API[/dim]\n\n"
            "Type [bold green]/help[/bold green] for available commands",
            title="Welcome",
            border_style="blue",
        )
        self.console.print(banner)

    def print_help(self) -> None:
        """Print available commands."""
        help_text = """
## Available Commands

### Session Management
- **/user <id> [roles]** - Switch to or create a user principal
- **/blank-user <id> [roles]** - Start a fresh memory session for a user
- **/users** - List known users
- **/project <id>** - Switch to or create a project
- **/session <id>** - Switch to or create a session
- **/sessions** - List active sessions
- **/clear** - Clear current session history
- **/reset** - Reset all sessions

### Context & Memory
- **/query <text>** - Query for context without storing
- **/memory** - Show recent conversation memory
- **/search <text>** - Search conversation memory

### Data Operations
- **/ingest** - Start interactive content ingestion
- **/sources** - List ingested sources
- **/doc <short_id>** - Retrieve a document by short ID

### Testing
- **/test <suite>** - Run test scenarios (health, memory, query, ingest, full)
- **/audit <id>** - Retrieve audit record

### General
- **/status** - Check API status
- **/help** - Show this help
- **/quit** or **/exit** - Exit the bot

### Chat Input
Any text not starting with `/` is sent as a user message and stored in conversation memory.
        """
        self.console.print(Markdown(help_text))

    async def connect(self) -> bool:
        """Connect to the Kontext API."""
        try:
            self.client = KontextClient()
            await self.client.connect()

            # Check API health
            health = await self.client.health_check()
            ready = await self.client.ready_check()

            self.memory_manager = MemoryManager(self.client)
            self.current_context = self.session_manager.get_or_create_default_context()

            # Initialize LLM client based on provider
            if self.settings.llm_api_key:
                provider = self.settings.llm_provider.lower()
                if provider == "ollama":
                    self.llm = OllamaCloudClient()
                    self.console.print(f"[green]Ollama Cloud ready:[/green] {self.settings.llm_model}")
                elif provider in ("openai", "openrouter"):
                    self.llm = LLMClient()
                    self.console.print(f"[green]LLM ready:[/green] {self.settings.llm_model}")
                else:
                    self.llm = LLMClient()
                    self.console.print(f"[green]LLM ready:[/green] {self.settings.llm_model}")
            else:
                self.llm = MockLLMClient()
                self.console.print("[yellow]LLM not configured:[/yellow] Using mock responses (set LLM_API_KEY for AI)")

            self.console.print(f"[green]Connected to API:[/green] {health}")
            self.console.print(f"[green]Database ready:[/green] {ready}")
            self.console.print(
                f"[dim]Current project:[/dim] {self.current_context.project.external_id}"
            )
            self.console.print(
                f"[dim]Current session:[/dim] {self.current_context.session.external_id}"
            )
            self.console.print(
                f"[dim]Current user:[/dim] {self.current_context.principal.external_id}"
            )
            return True

        except Exception as exc:
            self.console.print(f"[red]Failed to connect:[/red] {exc}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from the API."""
        if self.client:
            await self.client.close()
            self.client = None

    async def handle_project(self, project_id: str, title: str | None = None) -> None:
        """Handle the /project command."""
        project = self.session_manager.create_project(
            external_id=project_id,
            title=title or project_id,
        )

        # Create a new session for this project
        session = self.session_manager.create_session(
            project=project,
            title=f"Session for {project_id}",
        )

        self.current_context = self.session_manager.create_context(
            project=project,
            session=session,
            principal=self.current_context.principal if self.current_context else None,
            mode=self.current_context.mode if self.current_context else "full",
            source_collection_external_ids=(
                self.current_context.source_collection_external_ids if self.current_context else None
            ),
            private_source_collection_external_id=(
                self.current_context.private_source_collection_external_id if self.current_context else None
            ),
        )

        self.console.print(f"[green]Switched to project:[/green] {project_id}")
        self.console.print(f"[dim]New session:[/dim] {session.external_id}")

    def _parse_user_args(self, args: str) -> tuple[str, list[str] | None]:
        """Parse user command args as '<user_id> [role1,role2]'."""
        parts = args.split(maxsplit=1)
        user_id = parts[0].strip()
        roles = None
        if len(parts) > 1:
            roles = [role.strip() for role in parts[1].split(",") if role.strip()]
        return user_id, roles

    async def handle_user(self, args: str, *, blank_memory: bool = False) -> None:
        """Switch to a user principal, optionally starting with a blank session."""
        if not self.current_context:
            self.console.print("[red]No active project. Use /project first.[/red]")
            return

        user_id, roles = self._parse_user_args(args)
        if not user_id:
            self.console.print("[red]Usage: /user <user_id> [role1,role2][/red]")
            return

        principal = self.session_manager.create_principal(
            external_id=user_id,
            display_name=user_id,
            roles=roles or self.settings.bot_roles,
        )

        if blank_memory:
            self.current_context = self.session_manager.create_blank_context_for_user(
                self.current_context.project,
                principal,
            )
            self.console.print(f"[green]Started blank user session:[/green] {user_id}")
            self.console.print(f"[dim]New session:[/dim] {self.current_context.session.external_id}")
        else:
            self.current_context = self.session_manager.create_context(
                project=self.current_context.project,
                session=self.current_context.session,
                principal=principal,
                mode=self.current_context.mode,
                source_collection_external_ids=self.current_context.source_collection_external_ids,
                private_source_collection_external_id=(
                    self.current_context.private_source_collection_external_id
                ),
            )
            self.console.print(f"[green]Switched user:[/green] {user_id}")

        if principal.roles:
            self.console.print(f"[dim]Roles:[/dim] {', '.join(principal.roles)}")

    async def handle_users(self) -> None:
        """Handle the /users command."""
        users = self.session_manager.list_users()
        if not users:
            self.console.print("[dim]No known users.[/dim]")
            return

        table = Table(title="Known Users")
        table.add_column("User ID", style="cyan")
        table.add_column("Display Name", style="white")
        table.add_column("Roles", style="green")

        for user_id, display_name, roles in users:
            table.add_row(user_id, display_name or "-", roles or "-")

        self.console.print(table)

    async def handle_session(self, session_id: str, title: str | None = None) -> None:
        """Handle the /session command."""
        if not self.current_context:
            self.console.print("[red]No active project. Use /project first.[/red]")
            return

        project = self.current_context.project
        session = Session(
            external_id=session_id,
            title=title or session_id,
            project_external_id=project.external_id,
        )

        self.current_context = self.session_manager.create_context(
            project=project,
            session=session,
            principal=self.current_context.principal,
            mode=self.current_context.mode,
            source_collection_external_ids=self.current_context.source_collection_external_ids,
            private_source_collection_external_id=self.current_context.private_source_collection_external_id,
        )

        self.console.print(f"[green]Switched to session:[/green] {session_id}")

    async def handle_sessions(self) -> None:
        """Handle the /sessions command."""
        sessions = self.session_manager.list_active_sessions()
        if not sessions:
            self.console.print("[dim]No active sessions.[/dim]")
            return

        table = Table(title="Active Sessions")
        table.add_column("Session ID", style="cyan")
        table.add_column("Project ID", style="green")
        table.add_column("Title", style="white")
        table.add_column("User ID", style="magenta")

        for session_id, project_id, title, user_id in sessions:
            table.add_row(session_id, project_id, title, user_id)

        self.console.print(table)

    def _require_sources(self, action: str) -> bool:
        """Guard helper: deny actions that need source access in memory-only mode."""
        if not self.current_context or self.current_context.allows_sources:
            return True
        self.console.print(
            f"[dim]{action} suppressed: memory-only session is active.[/dim]"
        )
        return False

    async def handle_query(self, query_text: str) -> None:
        """Handle the /query command."""
        if not self.client or not self.current_context or not self.memory_manager:
            self.console.print("[red]Not connected or no context.[/red]")
            return

        try:
            with self.console.status("[dim]Querying context...[/dim]"):
                if self.current_context.allows_sources:
                    result = await self.memory_manager.query_with_memory(
                        query=query_text,
                        context=self.current_context,
                        limit=8,
                    )
                else:
                    # Memory-only mode: query only conversation history
                    from .models import Principal
                    result = await self.client.query(
                        query=query_text,
                        principal=Principal(
                            external_id=self.current_context.principal.external_id,
                            display_name=self.current_context.principal.display_name,
                            roles=self.current_context.principal.roles,
                        ),
                        limit=8,
                        content_kinds=["conversation_message"],
                        source_collections=self.current_context.source_collections_for_query,
                        memory=self.current_context.to_api_format(),
                    )

            if result.items:
                self.console.print(f"[green]Found {len(result.items)} context items:[/green]")
                for i, item in enumerate(result.items, 1):
                    title = item.title or "Untitled"
                    panel = Panel(
                        f"{item.snippet[:200]}..." if len(item.snippet) > 200 else item.snippet,
                        title=f"{i}. {title} [dim](score: {item.score:.3f})[/dim]",
                        subtitle=f"short_id: [cyan]{item.short_id}[/cyan]",
                    )
                    self.console.print(panel)
            else:
                self.console.print("[dim]No context items found.[/dim]")

            if result.permission_counters:
                denied = sum(result.permission_counters.values())
                if denied > 0:
                    self.console.print(f"[yellow]{denied} items filtered by permissions[/yellow]")

        except KontextAPIError as exc:
            self.console.print(f"[red]Query failed:[/red] {exc}")

    async def handle_memory(self) -> None:
        """Handle the /memory command."""
        if not self.client or not self.current_context or not self.memory_manager:
            self.console.print("[red]Not connected or no context.[/red]")
            return

        try:
            messages = await self.memory_manager.retrieve_recent(
                context=self.current_context,
                limit=10,
            )

            if messages:
                self.console.print(f"[green]Recent conversation memory ({len(messages)} messages):[/green]")
                for msg in messages:
                    role_color = {
                        "user": "blue",
                        "assistant": "green",
                        "tool": "yellow",
                    }.get(msg.role, "white")

                    self.console.print(
                        f"[[{role_color}]{msg.role}[/{role_color}]] {msg.content[:100]}"
                    )
            else:
                self.console.print("[dim]No memory found for this session.[/dim]")

        except KontextAPIError as exc:
            self.console.print(f"[red]Failed to retrieve memory:[/red] {exc}")

    async def handle_search(self, query: str) -> None:
        """Handle the /search command."""
        if not self.client or not self.current_context or not self.memory_manager:
            self.console.print("[red]Not connected or no context.[/red]")
            return

        try:
            with self.console.status("[dim]Searching memory...[/dim]"):
                results = await self.memory_manager.search_memory(
                    query=query,
                    context=self.current_context,
                    limit=8,
                )

            if results:
                self.console.print(f"[green]Found {len(results)} matching messages:[/green]")
                for i, item in enumerate(results, 1):
                    role = item.get("role", "unknown")
                    content = item.get("content", "")[:150]
                    score = item.get("score", 0)
                    self.console.print(f"{i}. [{role}] (score: {score:.3f}): {content}...")
            else:
                self.console.print("[dim]No matching messages found.[/dim]")

        except KontextAPIError as exc:
            self.console.print(f"[red]Search failed:[/red] {exc}")

    async def handle_sources(self) -> None:
        """Handle the /sources command."""
        if not self.client or not self.current_context:
            self.console.print("[red]Not connected.[/red]")
            return

        try:
            sources = await self.client.list_sources(self.current_context.principal)
            if sources:
                self.console.print(f"[green]Found {len(sources)} sources:[/green]")
                table = Table(title="Ingested Sources")
                table.add_column("System", style="cyan")
                table.add_column("Type", style="green")
                table.add_column("Object ID", style="white")
                table.add_column("Version", style="dim")

                for src in sources:
                    table.add_row(
                        src.get("source_system", "unknown"),
                        src.get("source_object_type", "unknown"),
                        src.get("source_object_id", "unknown"),
                        src.get("source_version", "-") or "-",
                    )
                self.console.print(table)
            else:
                self.console.print("[dim]No sources found.[/dim]")

        except KontextAPIError as exc:
            self.console.print(f"[red]Failed to list sources:[/red] {exc}")

    async def handle_doc(self, short_id: str) -> None:
        """Handle the /doc command."""
        if not self.client or not self.current_context:
            self.console.print("[red]Not connected.[/red]")
            return

        if not self._require_sources("Document retrieval"):
            return

        try:
            doc = await self.client.get_document(short_id, self.current_context.principal)
            if doc:
                panel = Panel(
                    doc.get("body", "No content"),
                    title=f"Document: {doc.get('title') or short_id}",
                    subtitle=f"Type: {doc.get('content_type', 'unknown')}",
                )
                self.console.print(panel)
            else:
                self.console.print(f"[yellow]Document not found:[/yellow] {short_id}")

        except KontextAPIError as exc:
            self.console.print(f"[red]Failed to retrieve document:[/red] {exc}")

    async def handle_ingest(self) -> None:
        """Handle the /ingest command."""
        if not self.client or not self.current_context:
            self.console.print("[red]Not connected.[/red]")
            return

        self.console.print("[dim]Interactive content ingestion[/dim]")

        source_system = Prompt.ask("Source system", default="test-system")
        source_type = Prompt.ask("Source object type", default="test-record")
        source_id = Prompt.ask("Source object ID", default="test-001")
        title = Prompt.ask("Title", default=f"Test record {source_id}")
        collection_external_id = self.current_context.private_source_collection_external_id
        if collection_external_id is None and self.current_context.source_collection_external_ids:
            collection_external_id = self.current_context.source_collection_external_ids[0]
        if collection_external_id is None:
            raw_collection = Prompt.ask(
                "Source collection (blank for user-private)",
                default="",
            ).strip()
            collection_external_id = raw_collection or None

        self.console.print("Enter content (Ctrl+D or empty line to finish):")
        lines: list[str] = []
        while True:
            try:
                line = Prompt.ask("")
                if not line:
                    break
                lines.append(line)
            except EOFError:
                break

        content = "\n".join(lines)
        if not content:
            self.console.print("[dim]No content provided, cancelling.[/dim]")
            return

        try:
            with self.console.status("[dim]Ingesting...[/dim]"):
                result = await self.client.ingest_record(
                    content=content,
                    source_system=source_system,
                    source_object_type=source_type,
                    source_object_id=source_id,
                    title=title,
                    metadata={"ingested_by": "testing_bot"},
                    principal=self.current_context.principal,
                    collection_external_id=collection_external_id,
                )

            self.console.print(f"[green]Ingested successfully:[/green] {result.status}")
            self.console.print(f"[dim]Content item ID:[/dim] {result.content_item_id}")
            self.console.print(f"[dim]Source record ID:[/dim] {result.source_record_id}")
            self.console.print(f"[dim]Checksum:[/dim] {result.checksum[:16]}...")

        except KontextAPIError as exc:
            self.console.print(f"[red]Ingestion failed:[/red] {exc}")

    async def handle_status(self) -> None:
        """Handle the /status command."""
        if not self.client:
            self.console.print("[red]Not connected.[/red]")
            return

        try:
            health = await self.client.health_check()
            ready = await self.client.ready_check()

            table = Table(title="API Status")
            table.add_column("Check", style="cyan")
            table.add_column("Status", style="green")

            for key, value in health.items():
                table.add_row(f"Health ({key})", str(value))
            for key, value in ready.items():
                table.add_row(f"Ready ({key})", str(value))

            self.console.print(table)

        except Exception as exc:
            self.console.print(f"[red]Status check failed:[/red] {exc}")

    async def handle_chat_message(self, message: str) -> None:
        """Handle a regular chat message (not a command)."""
        if not self.client or not self.current_context or not self.memory_manager:
            self.console.print("[red]Not connected.[/red]")
            return

        # Store user message in memory
        try:
            with self.console.status("[dim]Storing message...[/dim]"):
                await self.memory_manager.store_message(
                    context=self.current_context,
                    role="user",
                    content=message,
                )

            # Add to local history
            self.current_context.add_message("user", message)

            # Build context pack
            with self.console.status("[dim]Building context...[/dim]"):
                context_pack = await self.memory_manager.build_context_pack(
                    query=message,
                    context=self.current_context,
                    include_memory=True,
                    include_sources=self.current_context.allows_sources,
                )

            # Display retrieved context
            if context_pack["source_items"] or context_pack["memory_items"]:
                context_display = self.memory_manager.format_context_for_display(context_pack)
                self.console.print(Panel(context_display, title="Context", border_style="dim"))

            # Generate response using LLM
            with self.console.status("[dim]Generating response...[/dim]"):
                response = await self._generate_response(message, context_pack)

            # Store assistant response
            with self.console.status("[dim]Storing response...[/dim]"):
                await self.memory_manager.store_message(
                    context=self.current_context,
                    role="assistant",
                    content=response,
                    metadata={"used_context": len(context_pack["source_items"])},
                )

            self.current_context.add_message("assistant", response)

            # Display response
            self.console.print(f"[green]Bot:[/green] {response}")

        except KontextAPIError as exc:
            self.console.print(f"[red]Error:[/red] {exc}")

    async def _generate_response(self, message: str, context_pack: dict[str, Any]) -> str:
        """Generate a response using the LLM with retrieved context."""
        if not self.llm:
            return "[Error: LLM not initialized]"

        # Build conversation history from context
        conversation_history: list[dict[str, str]] = []
        for msg in context_pack.get("memory_items", []):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant"):
                conversation_history.append({"role": role, "content": content})

        # Build context string
        context_parts: list[str] = []

        # Add sources
        sources = context_pack.get("source_items", [])
        if sources:
            context_parts.append("## Relevant Sources")
            for i, item in enumerate(sources, 1):
                title = item.get("title") or "Untitled"
                snippet = item.get("snippet", "")
                context_parts.append(f"{i}. {title}")
                context_parts.append(f"   {snippet}")

        context_str = "\n".join(context_parts)

        # Generate response using LLM
        try:
            response = await self.llm.generate_response(
                user_message=message,
                context=context_str,
                conversation_history=conversation_history,
            )
            return response
        except Exception as exc:
            self.console.print(f"[dim red]LLM error: {exc}[/dim red]")
            # Fallback to simple response
            return f"I received: '{message}'\n\n[Error generating response: {exc}]"


    async def run(self) -> None:
        """Main run loop."""
        self.print_banner()

        if not await self.connect():
            sys.exit(1)

        try:
            while True:
                try:
                    user_input = Prompt.ask("\n[you]")
                    user_input = user_input.strip()

                    if not user_input:
                        continue

                    if user_input.startswith("/"):
                        await self.handle_command(user_input)
                    else:
                        await self.handle_chat_message(user_input)

                except EOFError:
                    break
                except KeyboardInterrupt:
                    self.console.print("\n[yellow]Interrupted. Type /quit to exit.[/yellow]")

        finally:
            await self.disconnect()
            self.console.print("\n[dim]Goodbye![/dim]")

    async def handle_command(self, command_line: str) -> None:
        """Parse and handle a slash command."""
        parts = command_line[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        match cmd:
            case "help" | "h":
                self.print_help()
            case "quit" | "exit" | "q":
                raise SystemExit(0)
            case "user" | "u":
                if args:
                    await self.handle_user(args)
                else:
                    self.console.print("[red]Usage: /user <user_id> [role1,role2][/red]")
            case "blank-user" | "blankuser" | "bu":
                if args:
                    await self.handle_user(args, blank_memory=True)
                else:
                    self.console.print("[red]Usage: /blank-user <user_id> [role1,role2][/red]")
            case "users":
                await self.handle_users()
            case "project" | "p":
                if args:
                    await self.handle_project(args)
                else:
                    self.console.print("[red]Usage: /project <project_id>[/red]")
            case "session" | "s":
                if args:
                    await self.handle_session(args)
                else:
                    self.console.print("[red]Usage: /session <session_id>[/red]")
            case "sessions" | "ls":
                await self.handle_sessions()
            case "clear":
                if self.current_context:
                    self.current_context.messages.clear()
                    self.console.print("[green]Session history cleared.[/green]")
            case "reset":
                self.session_manager.clear_all_contexts()
                self.current_context = self.session_manager.get_or_create_default_context()
                self.console.print("[green]All sessions reset.[/green]")
            case "query" | "q":
                if args:
                    await self.handle_query(args)
                else:
                    self.console.print("[red]Usage: /query <query text>[/red]")
            case "memory" | "m":
                await self.handle_memory()
            case "search":
                if args:
                    await self.handle_search(args)
                else:
                    self.console.print("[red]Usage: /search <query text>[/red]")
            case "sources":
                await self.handle_sources()
            case "doc" | "d":
                if args:
                    await self.handle_doc(args)
                else:
                    self.console.print("[red]Usage: /doc <short_id>[/red]")
            case "ingest" | "i":
                await self.handle_ingest()
            case "status":
                await self.handle_status()
            case "test" | "t":
                from .test_runner import run_test_suite
                await run_test_suite(self.console, self.client, args or "full")
            case "audit":
                if args and self.client:
                    try:
                        audit = await self.client.get_audit(args)
                        if audit:
                            self.console.print(audit)
                        else:
                            self.console.print(f"[yellow]Audit not found:[/yellow] {args}")
                    except Exception as exc:
                        self.console.print(f"[red]Failed:[/red] {exc}")
                else:
                    self.console.print("[red]Usage: /audit <audit_id>[/red]")
            case _:
                self.console.print(f"[red]Unknown command:[/red] /{cmd}")
                self.console.print("Type /help for available commands.")
