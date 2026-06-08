"""Interactive CLI for Catena AI chat with Kontext conversation memory."""

from __future__ import annotations

import uuid

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .catena_bridge import CatenaMemoryBridge
from .catena_client import CatenaClient
from .client import KontextClient
from .config import get_settings
from .errors import CatenaAPIError, KontextAPIError
from .session import ChatContext, get_session_manager


class CatenaChatInterface:
    """Memory-backed Catena chat harness for integration testing."""

    def __init__(self) -> None:
        self.console = Console()
        self.settings = get_settings()
        self.session_manager = get_session_manager()
        self.catena: CatenaClient | None = None
        self.kontext: KontextClient | None = None
        self.bridge: CatenaMemoryBridge | None = None
        self.current_context: ChatContext | None = None
        self.current_flow_id: str | None = self.settings.catena_default_flow_id

    def print_banner(self) -> None:
        banner = Panel.fit(
            "[bold blue]Catena + Kontext Integration Harness[/bold blue]\n"
            "[dim]Catena /chat with Kontext /v1/memory/* persistence[/dim]\n\n"
            "Type [bold green]/help[/bold green] for commands",
            title="Welcome",
            border_style="blue",
        )
        self.console.print(banner)

    def print_help(self) -> None:
        help_text = """
## Catena + Kontext Commands

### Session
- **/thread [id]** - Set Catena thread id (= Kontext session). New id if omitted.
- **/flow [id]** - Set Catena flow_id for `/chat` (e.g. `router`, `deep_search`)
- **/project [id]** - Switch Kontext project external_id
- **/memory** - Show recent Kontext memory for current thread
- **/search <text>** - Semantic search in Kontext memory

### Status
- **/catena-status** - Catena health + authenticated user
- **/kontext-status** - Kontext health + readiness
- **/context** - Show current project, thread, flow, principal

### General
- **/help** - Show this help
- **/quit** or **/exit** - Exit

### Chat
Any other text is sent to **Catena /chat** and stored in **Kontext memory**.
        """
        self.console.print(Markdown(help_text))

    async def connect(self) -> bool:
        try:
            self.catena = CatenaClient()
            self.kontext = KontextClient()
            await self.catena.connect()
            await self.kontext.connect()

            catena_health = await self.catena.health_check()
            kontext_health = await self.kontext.health_check()
            kontext_ready = await self.kontext.ready_check()

            self.bridge = CatenaMemoryBridge(self.catena, self.kontext)
            self.current_context = self._default_context()
            await self.bridge.sync_context_from_catena(self.current_context)

            user = await self.bridge.resolve_catena_user()
            self.console.print(f"[green]Catena:[/green] {catena_health}")
            self.console.print(
                f"[green]Catena user:[/green] {user.email} "
                f"({'admin' if user.is_admin else 'user'})"
            )
            self.console.print(f"[green]Kontext health:[/green] {kontext_health}")
            self.console.print(f"[green]Kontext ready:[/green] {kontext_ready}")
            self._print_context_summary()
            return True
        except (CatenaAPIError, KontextAPIError, Exception) as exc:
            self.console.print(f"[red]Connection failed:[/red] {exc}")
            return False

    def _default_context(self) -> ChatContext:
        settings = get_settings()
        project = self.session_manager.create_project(
            external_id=settings.catena_project_id,
            title=settings.catena_project_title,
        )
        thread_id = self._new_thread_id()
        session = self.session_manager.create_session(
            project=project,
            external_id=thread_id,
            title=f"Catena thread {thread_id}",
        )
        principal = self.session_manager.create_principal(
            external_id="catena:pending",
            display_name="Catena user",
        )
        return self.session_manager.create_context(
            project=project,
            session=session,
            principal=principal,
            mode="memory_only",
        )

    def _new_thread_id(self) -> str:
        prefix = self.settings.catena_thread_prefix.rstrip("-")
        return f"{prefix}-{uuid.uuid4().hex[:12]}"

    def _print_context_summary(self) -> None:
        if not self.current_context:
            return
        ctx = self.current_context
        flow = self.current_flow_id or "(server default)"
        self.console.print(f"[dim]Project:[/dim] {ctx.project.external_id}")
        self.console.print(f"[dim]Thread:[/dim] {ctx.session.external_id}")
        self.console.print(f"[dim]Flow:[/dim] {flow}")
        self.console.print(f"[dim]Principal:[/dim] {ctx.principal.external_id}")

    async def run(self) -> None:
        self.print_banner()
        if not await self.connect():
            return

        self.console.print("\n[dim]Ready. Type a message or /help.[/dim]\n")
        while True:
            try:
                user_input = self.console.input("[bold cyan]You:[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[yellow]Goodbye![/yellow]")
                break

            if not user_input:
                continue
            if user_input.startswith("/"):
                if await self.handle_command(user_input):
                    break
                continue
            await self.handle_chat_message(user_input)

    async def handle_command(self, command: str) -> bool:
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit"):
            self.console.print("[yellow]Goodbye![/yellow]")
            return True
        if cmd == "/help":
            self.print_help()
        elif cmd == "/catena-status":
            await self._cmd_catena_status()
        elif cmd == "/kontext-status":
            await self._cmd_kontext_status()
        elif cmd == "/context":
            self._print_context_summary()
        elif cmd == "/thread":
            await self._cmd_thread(arg)
        elif cmd == "/flow":
            self._cmd_flow(arg)
        elif cmd == "/project":
            self._cmd_project(arg)
        elif cmd == "/memory":
            await self._cmd_memory()
        elif cmd == "/search":
            await self._cmd_search(arg)
        else:
            self.console.print(f"[red]Unknown command:[/red] {cmd}. Type /help.")
        return False

    async def _cmd_catena_status(self) -> None:
        if not self.catena or not self.bridge:
            self.console.print("[red]Not connected.[/red]")
            return
        health = await self.catena.health_check()
        user = await self.bridge.resolve_catena_user()
        table = Table(title="Catena Status")
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("health", str(health))
        table.add_row("email", user.email)
        table.add_row("user_id", str(user.id))
        table.add_row("is_admin", str(user.is_admin))
        table.add_row("company", user.company_name or "")
        self.console.print(table)

    async def _cmd_kontext_status(self) -> None:
        if not self.kontext:
            self.console.print("[red]Not connected.[/red]")
            return
        health = await self.kontext.health_check()
        ready = await self.kontext.ready_check()
        self.console.print(f"health: {health}")
        self.console.print(f"ready: {ready}")

    async def _cmd_thread(self, thread_id: str) -> None:
        if not self.current_context:
            return
        new_id = thread_id or self._new_thread_id()
        self.current_context.session.external_id = new_id
        self.current_context.session.title = f"Catena thread {new_id}"
        self.current_context.messages.clear()
        self.console.print(f"[green]Thread set to[/green] {new_id}")

    def _cmd_flow(self, flow_id: str) -> None:
        if not flow_id:
            self.console.print(f"[dim]Current flow:[/dim] {self.current_flow_id or '(server default)'}")
            return
        self.current_flow_id = flow_id
        self.console.print(f"[green]Flow set to[/green] {flow_id}")

    def _cmd_project(self, project_id: str) -> None:
        if not self.current_context or not project_id:
            self.console.print("[red]Usage:[/red] /project <external_id>")
            return
        self.current_context.project.external_id = project_id
        self.current_context.session.project_external_id = project_id
        self.console.print(f"[green]Project set to[/green] {project_id}")

    async def _cmd_memory(self) -> None:
        if not self.kontext or not self.current_context or not self.bridge:
            self.console.print("[red]Not connected.[/red]")
            return
        await self.bridge.sync_context_from_catena(self.current_context)
        recent = await self.kontext.get_recent_memory(
            project_external_id=self.current_context.project.external_id,
            session_external_id=self.current_context.session.external_id,
            principal_external_id=self.current_context.principal.external_id,
            limit=20,
        )
        if not recent:
            self.console.print("[dim]No Kontext memory for this thread yet.[/dim]")
            return
        for msg in recent:
            role = msg.role.capitalize()
            preview = msg.content[:200] + ("..." if len(msg.content) > 200 else "")
            self.console.print(f"[bold]{role}:[/bold] {preview}")

    async def _cmd_search(self, query: str) -> None:
        if not query:
            self.console.print("[red]Usage:[/red] /search <text>")
            return
        if not self.kontext or not self.current_context or not self.bridge:
            self.console.print("[red]Not connected.[/red]")
            return
        await self.bridge.sync_context_from_catena(self.current_context)
        hits = await self.kontext.search_memory(
            query=query,
            project_external_id=self.current_context.project.external_id,
            session_external_id=self.current_context.session.external_id,
            principal_external_id=self.current_context.principal.external_id,
        )
        if not hits:
            self.console.print("[dim]No matching Kontext memory.[/dim]")
            return
        for index, hit in enumerate(hits, 1):
            score = hit.get("score", 0)
            content = str(hit.get("content", ""))[:180]
            self.console.print(f"{index}. [score={score:.3f}] {content}")

    async def handle_chat_message(self, message: str) -> None:
        if not self.bridge or not self.current_context:
            self.console.print("[red]Not connected.[/red]")
            return

        try:
            with self.console.status("[dim]Catena chat + Kontext memory...[/dim]"):
                result = await self.bridge.run_turn(
                    self.current_context,
                    message,
                    flow_id=self.current_flow_id,
                )

            preview = result.memory_preview
            if preview.recent_messages or preview.search_hits:
                lines: list[str] = []
                if preview.recent_messages:
                    lines.append(f"Recent memory: {len(preview.recent_messages)} message(s)")
                if preview.search_hits:
                    lines.append(f"Memory search: {len(preview.search_hits)} hit(s)")
                self.console.print(Panel("\n".join(lines), title="Kontext", border_style="dim"))

            self.current_context.add_message("user", message)
            self.current_context.add_message("assistant", result.catena.text)
            flow = result.catena.flow_type or "unknown"
            self.console.print(
                Panel(
                    result.catena.text,
                    title=f"Catena ({flow}) · thread {result.thread_id}",
                    border_style="green",
                )
            )
        except (CatenaAPIError, KontextAPIError) as exc:
            self.console.print(f"[red]Error:[/red] {exc}")

    async def shutdown(self) -> None:
        if self.catena:
            await self.catena.close()
        if self.kontext:
            await self.kontext.close()
