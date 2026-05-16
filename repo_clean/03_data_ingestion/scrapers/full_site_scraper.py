"""
Step D: Full website scrape.

Uses Firecrawl if FIRECRAWL_API_KEY is set (with cookie dismiss actions),
otherwise falls back to requests+bs4 with HTML-level cleaning.
Saves all scraped pages as JSON to data/scraped/.
"""
import json
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "01_pipeline_setup"))
from pipeline_config import load_config, ensure_data_dirs, get_env
from content_cleaner import extract_clean_text, extract_headings, extract_title

# ---------------------------------------------------------------------------


def build_firecrawl_actions(config: dict) -> list[dict]:
    """Build Firecrawl browser actions from config cookie_handling."""
    cookie_cfg = config.get("scraping", {}).get("cookie_handling", {})
    actions = []

    wait_before = cookie_cfg.get("wait_before_ms", 3000)
    actions.append({"type": "wait", "milliseconds": wait_before})

    for selector in cookie_cfg.get("click_selectors", []):
        actions.append({"type": "click", "selector": selector})

    wait_after = cookie_cfg.get("wait_after_ms", 1500)
    actions.append({"type": "wait", "milliseconds": wait_after})

    return actions


def crawl_with_firecrawl(base_url: str, config: dict) -> list[dict]:
    """Use Firecrawl API with cookie-dismiss actions."""
    from firecrawl import FirecrawlApp

    api_key = get_env("FIRECRAWL_API_KEY")
    app = FirecrawlApp(api_key=api_key)

    max_pages = config["scraping"]["max_pages"]
    exclude = config["scraping"].get("exclude_patterns", [])
    exclude += config["scraping"].get("exclude_page_types", [])
    actions = build_firecrawl_actions(config)

    print(f"  Firecrawl crawl: {base_url} (limit={max_pages})")
    print(f"  Cookie actions: {len(actions)} steps configured")

    result = app.crawl_url(
        base_url,
        params={
            "limit": max_pages,
            "excludePaths": exclude,
            "scrapeOptions": {
                "formats": ["markdown", "html"],
                "actions": actions,
                "waitFor": 2000,
            },
        },
    )

    items = result.get("data", result) if isinstance(result, dict) else result
    if not isinstance(items, list):
        items = [items]

    pages = []
    for item in items:
        html = item.get("html", "")
        md = item.get("markdown", "")
        meta = item.get("metadata", {})
        url = meta.get("sourceURL", meta.get("url", ""))

        # Clean even the Firecrawl output
        if html:
            text = extract_clean_text(html, config)
        else:
            text = md

        pages.append({
            "url": url,
            "title": meta.get("title", ""),
            "text": text,
            "text_length": len(text),
            "source": "firecrawl",
        })

    return pages


def crawl_with_requests(base_url: str, config: dict) -> list[dict]:
    """Fallback BFS crawl with HTML-level cleaning."""
    max_pages = config["scraping"]["max_pages"]
    exclude = config["scraping"].get("exclude_patterns", [])
    exclude += config["scraping"].get("exclude_page_types", [])

    domain = urlparse(base_url).netloc
    visited: set[str] = set()
    queue = [base_url]
    pages: list[dict] = []

    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        normalized = url.split("#")[0].rstrip("/")
        if normalized in visited:
            continue
        if any(pat in normalized for pat in exclude):
            continue
        visited.add(normalized)

        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"  [skip] {url}: {e}")
            continue

        html = resp.text
        title = extract_title(html)
        text = extract_clean_text(html, config)

        pages.append({
            "url": url,
            "title": title,
            "text": text,
            "text_length": len(text),
            "source": "requests_bs4",
        })
        print(f"  [{len(pages)}/{max_pages}] {url} ({len(text)} chars)")

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"]).split("#")[0].rstrip("/")
            if urlparse(href).netloc == domain and href not in visited:
                queue.append(href)

        time.sleep(0.5)

    return pages


def run_scrape():
    config = load_config()
    base_url = config["client"]["base_url"]
    data_dir = ensure_data_dirs()
    out_file = data_dir / "scraped" / "scraped_pages.json"

    print(f"=== Full scrape: {base_url} ===\n")

    use_firecrawl = bool(get_env("FIRECRAWL_API_KEY", required=False))

    if use_firecrawl:
        print("Using Firecrawl API (with cookie dismiss actions)...\n")
        pages = crawl_with_firecrawl(base_url, config)
    else:
        print("FIRECRAWL_API_KEY not set. Using requests+bs4 fallback...\n")
        pages = crawl_with_requests(base_url, config)

    with open(out_file, "w") as f:
        json.dump(pages, f, indent=2, ensure_ascii=False)

    print(f"\nScraped {len(pages)} pages -> {out_file}")
    return pages


if __name__ == "__main__":
    run_scrape()
