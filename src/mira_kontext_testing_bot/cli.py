"""CLI entry point for the Mira Kontext Testing Bot."""

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from .chat_interface import ChatInterface
from .client import KontextClient
from .config import get_settings, load_env_file
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
        load_env_file(Path(env_file))
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
@click.argument("url")
@click.option("--api-url", help="Override API URL")
@click.option("--token", help="Override API token")
@click.pass_context
def crawl(
    ctx: click.Context,
    url: str,
    api_url: str | None,
    token: str | None,
) -> None:
    """Fetch a web page via Firecrawl and ingest it into the API."""
    settings = get_settings()
    effective_url = api_url or ctx.obj.get("api_url") or settings.kontext_api_url
    effective_token = token or ctx.obj.get("token") or settings.kontext_token

    if not effective_token:
        console.print("[red]Error: API token required.[/red]")
        sys.exit(1)

    if not settings.firecrawl_api_key:
        console.print("[red]Error: FIRECRAWL_API_KEY not configured.[/red]")
        sys.exit(1)

    async def execute() -> None:
        from .session import get_session_manager
        from .web_fetcher import WebFetcher, WebFetchError

        client = KontextClient(base_url=effective_url, token=effective_token)
        await client.connect()
        fetcher = WebFetcher()
        session_mgr = get_session_manager()
        context = session_mgr.get_or_create_default_context()

        try:
            with console.status(f"[dim]Fetching {url}...[/dim]"):
                result = await fetcher.fetch_url(
                    url=url,
                    client=client,
                    context=context,
                )
            console.print(f"[green]Fetched and ingested:[/green] {result['title']}")
            console.print(f"[dim]URL:[/dim] {result['url']}")
            console.print(f"[dim]Content length:[/dim] {result['content_length']} chars")
            console.print(f"[dim]Ingest status:[/dim] {result['ingest_status']}")
            console.print(f"[dim]Content item ID:[/dim] {result['content_item_id']}")
        except WebFetchError as exc:
            console.print(f"[red]Crawl failed:[/red] {exc}")
            sys.exit(1)
        finally:
            await client.close()

    asyncio.run(execute())


@cli.command("search-web")
@click.argument("query")
@click.option("--max-results", default=3, help="Maximum web results to fetch")
@click.option("--api-url", help="Override API URL")
@click.option("--token", help="Override API token")
@click.pass_context
def search_web(
    ctx: click.Context,
    query: str,
    max_results: int,
    api_url: str | None,
    token: str | None,
) -> None:
    """Search the web via DuckDuckGo, fetch top results, and ingest into API."""
    settings = get_settings()
    effective_url = api_url or ctx.obj.get("api_url") or settings.kontext_api_url
    effective_token = token or ctx.obj.get("token") or settings.kontext_token

    if not effective_token:
        console.print("[red]Error: API token required.[/red]")
        sys.exit(1)

    if not settings.firecrawl_api_key:
        console.print("[red]Error: FIRECRAWL_API_KEY not configured.[/red]")
        sys.exit(1)

    async def execute() -> None:
        from .session import get_session_manager
        from .web_fetcher import WebFetcher, WebFetchError

        client = KontextClient(base_url=effective_url, token=effective_token)
        await client.connect()
        fetcher = WebFetcher()
        session_mgr = get_session_manager()
        context = session_mgr.get_or_create_default_context()

        try:
            with console.status(f"[dim]Searching web for '{query}'...[/dim]"):
                results = await fetcher.search_and_ingest(
                    query=query,
                    client=client,
                    context=context,
                    max_results=max_results,
                )

            if not results:
                console.print("[dim]No web results found.[/dim]")
                return

            succeeded = [r for r in results if "error" not in r]
            failed = [r for r in results if "error" in r]

            console.print(f"[green]Ingested {len(succeeded)} page(s) from web search.[/green]")

            for r in succeeded:
                console.print(f"\n  [cyan]{r['title']}[/cyan]")
                console.print(f"  URL: {r['url']}")
                console.print(f"  Status: {r['ingest_status']} | Length: {r['content_length']} chars")

            if failed:
                console.print(f"\n[yellow]{len(failed)} page(s) failed:[/yellow]")
                for r in failed:
                    console.print(f"  [red]- {r['url']}:[/red] {r['error']}")

        except WebFetchError as exc:
            console.print(f"[red]Web search failed:[/red] {exc}")
            sys.exit(1)
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

    # Web fetcher status
    firecrawl_status = "Set" if settings.firecrawl_api_key else "Not set"
    console.print(f"Firecrawl:  {firecrawl_status} (crawl/search-web)")
    console.print(f"Auto Web:   {settings.auto_web_search}")


# Entry point for the package
def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
