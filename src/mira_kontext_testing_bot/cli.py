"""CLI entry point for the Mira Kontext Testing Bot."""

import asyncio
import sys

import click
from rich.console import Console
from rich.panel import Panel

from .chat_interface import ChatInterface
from .config import get_settings, load_env_file
from .client import KontextClient
from .test_runner import run_test_suite

console = Console()


@click.group()
@click.option("--env-file", type=click.Path(exists=True), help="Path to .env file")
@click.option("--api-url", help="Kontext API base URL")
@click.option("--token", help="Kontext API token")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.pass_context
def cli(ctx: click.Context, env_file: str | None, api_url: str | None, token: str | None, debug: bool) -> None:
    """Mira Kontext Testing Bot - CLI interface."""
    # Load environment file if specified
    if env_file:
        load_env_file(env_file)
    else:
        load_env_file()

    # Store options in context
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = api_url
    ctx.obj["token"] = token
    ctx.obj["debug"] = debug


@cli.command()
@click.pass_context
def chat(ctx: click.Context) -> None:
    """Start interactive chat session."""
    # Override settings with CLI options
    settings = get_settings()
    if ctx.obj.get("api_url"):
        settings.kontext_api_url = ctx.obj["api_url"]
    if ctx.obj.get("token"):
        settings.kontext_token = ctx.obj["token"]
    if ctx.obj.get("debug"):
        settings.debug = True

    interface = ChatInterface()
    try:
        asyncio.run(interface.run())
    except SystemExit as exc:
        sys.exit(exc.code)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        if settings.debug:
            raise
        sys.exit(1)


@cli.command()
@click.argument("suite", default="full")
@click.option("--api-url", help="Override API URL")
@click.option("--token", help="Override API token")
@click.pass_context
def test(ctx: click.Context, suite: str, api_url: str | None, token: str | None) -> None:
    """Run test scenarios against the API.

    Available suites: health, memory, query, ingest, audit, full
    """
    settings = get_settings()
    effective_url = api_url or ctx.obj.get("api_url") or settings.kontext_api_url
    effective_token = token or ctx.obj.get("token") or settings.kontext_token

    if not effective_token:
        console.print("[red]Error: API token required. Set KONTEXT_TOKEN or use --token.[/red]")
        sys.exit(1)

    async def run() -> None:
        client = KontextClient(base_url=effective_url, token=effective_token)
        await client.connect()

        try:
            await run_test_suite(console, client, suite)
        finally:
            await client.close()

    try:
        asyncio.run(run())
    except Exception as exc:
        console.print(f"[red]Test execution failed:[/red] {exc}")
        if settings.debug:
            raise
        sys.exit(1)


@cli.command()
@click.option("--api-url", help="Override API URL")
@click.option("--token", help="Override API token")
@click.pass_context
def status(ctx: click.Context, api_url: str | None, token: str | None) -> None:
    """Check API health and readiness."""
    settings = get_settings()
    effective_url = api_url or ctx.obj.get("api_url") or settings.kontext_api_url
    effective_token = token or ctx.obj.get("token") or settings.kontext_token

    async def check() -> None:
        client = KontextClient(base_url=effective_url, token=effective_token or "dummy")
        await client.connect()

        try:
            health = await client.health_check()
            ready = await client.ready_check()

            console.print(Panel("[bold green]API Status: OK[/bold green]", border_style="green"))
            console.print(f"Health: {health}")
            console.print(f"Ready:  {ready}")
        except Exception as exc:
            console.print(Panel("[bold red]API Status: Failed[/bold red]", border_style="red"))
            console.print(f"[red]Error: {exc}[/red]")
        finally:
            await client.close()

    asyncio.run(check())


@cli.command()
@click.argument("query")
@click.option("--limit", default=8, help="Maximum results to return")
@click.option("--content-kind", multiple=True, help="Filter by content kind")
@click.option("--api-url", help="Override API URL")
@click.option("--token", help="Override API token")
@click.pass_context
def query(
    ctx: click.Context,
    query: str,
    limit: int,
    content_kind: tuple[str, ...],
    api_url: str | None,
    token: str | None,
) -> None:
    """Execute a single context query."""
    settings = get_settings()
    effective_url = api_url or ctx.obj.get("api_url") or settings.kontext_api_url
    effective_token = token or ctx.obj.get("token") or settings.kontext_token

    if not effective_token:
        console.print("[red]Error: API token required.[/red]")
        sys.exit(1)

    async def execute() -> None:
        from .models import Principal

        client = KontextClient(base_url=effective_url, token=effective_token)
        await client.connect()

        try:
            result = await client.query(
                query=query,
                principal=Principal(
                    external_id=settings.bot_principal_id,
                    display_name=settings.bot_display_name,
                    roles=settings.bot_roles,
                ),
                limit=limit,
                content_kinds=list(content_kind) if content_kind else None,
            )

            console.print(f"[green]Query executed. Audit ID: {result.audit_id}[/green]")
            console.print(f"Found {len(result.items)} items")

            for i, item in enumerate(result.items, 1):
                title = item.title or "Untitled"
                console.print(f"\n{i}. {title} (score: {item.score:.3f})")
                console.print(f"   short_id: {item.short_id}")
                console.print(f"   {item.snippet[:150]}...")

            if result.permission_counters:
                denied = sum(result.permission_counters.values())
                if denied > 0:
                    console.print(f"\n[yellow]{denied} items filtered by permissions[/yellow]")
        finally:
            await client.close()

    asyncio.run(execute())


@cli.command()
def config() -> None:
    """Display current configuration."""
    settings = get_settings()

    console.print(Panel("[bold]Current Configuration[/bold]", border_style="blue"))
    console.print(f"API URL:    {settings.kontext_api_url}")
    console.print(f"Bot ID:     {settings.bot_principal_id}")
    console.print(f"Bot Name:   {settings.bot_display_name}")
    console.print(f"Bot Roles:  {', '.join(settings.bot_roles)}")
    console.print(f"Timeout:    {settings.request_timeout}s")
    console.print(f"Debug:      {settings.debug}")

    # Token is masked for security
    token_status = "Set" if settings.kontext_token else "Not set"
    console.print(f"Token:      {token_status}")


# Entry point for the package
def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
