"""
Step B: Probe a client website to understand its structure.

Scrapes a small sample of pages, strips cookie/nav noise,
analyzes the content types, and outputs a suggested ontology.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "01_pipeline_setup"))
from pipeline_config import load_config, ensure_data_dirs
from content_cleaner import extract_clean_text, extract_headings, extract_title

# ---------------------------------------------------------------------------


def discover_links(base_url: str, config: dict, max_links: int = 20) -> list[str]:
    """Get internal links from the homepage, respecting exclusions."""
    try:
        resp = requests.get(base_url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [warn] Could not fetch {base_url}: {e}")
        return [base_url]

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")
    domain = urlparse(base_url).netloc

    exclude_patterns = config.get("scraping", {}).get("exclude_patterns", [])
    exclude_pages = config.get("scraping", {}).get("exclude_page_types", [])
    all_exclude = exclude_patterns + exclude_pages

    links = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]).split("#")[0].rstrip("/")
        if urlparse(href).netloc != domain or not href.startswith("http"):
            continue
        if any(pat in href for pat in all_exclude):
            continue
        links.add(href)

    return sorted(links)[:max_links]


def scrape_page(url: str, config: dict) -> dict:
    """Scrape a single page with full cleaning pipeline."""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        return {"url": url, "error": str(e), "text": "", "text_length": 0}

    html = resp.text
    title = extract_title(html)
    headings = extract_headings(html, config)
    text = extract_clean_text(html, config)

    return {
        "url": url,
        "title": title,
        "headings": headings,
        "text_length": len(text),
        "text": text[:3000],
    }


def classify_page(page: dict) -> str:
    url_lower = page["url"].lower()
    mapping = {
        "contact_legal": ["/kontakt", "/contact", "/impressum"],
        "services": ["/leistung", "/service", "/angebot"],
        "projects": ["/projekt", "/project", "/referenz", "/case"],
        "about": ["/team", "/agentur", "/about", "/ueber"],
        "blog": ["/blog", "/news", "/artikel", "/article"],
        "faq": ["/faq", "/hilfe", "/help"],
        "product": ["/produkt", "/product", "/shop"],
        "legal": ["/datenschutz", "/privacy", "/agb", "/terms"],
    }
    for ptype, patterns in mapping.items():
        if any(k in url_lower for k in patterns):
            return ptype
    return "general"


def build_suggested_ontology(pages: list[dict]) -> dict:
    page_types: dict[str, int] = {}
    all_headings: list[str] = []
    total_text = ""

    for p in pages:
        ptype = classify_page(p)
        page_types[ptype] = page_types.get(ptype, 0) + 1
        all_headings.extend(p.get("headings", []))
        total_text += p.get("text", "") + " "

    de = len(re.findall(r"\b(und|die|der|ist|für|mit|von|das|auf)\b", total_text, re.I))
    en = len(re.findall(r"\b(the|and|is|for|with|from|that|are|this)\b", total_text, re.I))
    langs = []
    if de > en:
        langs.append("de")
    if en > 0:
        langs.append("en")

    return {
        "pages_scanned": len(pages),
        "detected_page_types": page_types,
        "detected_languages": langs or ["unknown"],
        "sample_headings": all_headings[:30],
        "suggested_chunk_types": sorted(set(page_types.keys())),
        "suggested_business_domains": sorted(set(page_types.keys())),
    }


def run_probe():
    config = load_config()
    base_url = config["client"]["base_url"]
    probe_limit = config["scraping"].get("probe_pages", 5)

    data_dir = ensure_data_dirs()
    probe_dir = data_dir / "probe"

    print(f"=== Probing {base_url} (limit {probe_limit} pages) ===\n")

    links = discover_links(base_url, config, max_links=probe_limit + 5)
    print(f"Discovered {len(links)} internal links (after exclusions). Scraping top {probe_limit}...\n")

    pages = []
    for url in links[:probe_limit]:
        print(f"  Scraping: {url}")
        page = scrape_page(url, config)
        pages.append(page)
        print(f"    -> {page.get('title', '?')} ({page['text_length']} chars)")

    ontology = build_suggested_ontology(pages)

    probe_output = probe_dir / "probe_result.json"
    with open(probe_output, "w") as f:
        json.dump({"pages": pages, "ontology": ontology}, f, indent=2, ensure_ascii=False)

    print(f"\n=== Suggested Ontology ===")
    print(json.dumps(ontology, indent=2, ensure_ascii=False))
    print(f"\nFull probe saved to {probe_output}")
    return ontology


if __name__ == "__main__":
    run_probe()
