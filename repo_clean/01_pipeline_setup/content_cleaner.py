"""
Shared content cleaning logic used by both probe and scraper.
Handles: cookie banners, nav/footer stripping, text noise removal.
"""
import re
from bs4 import BeautifulSoup


def clean_html(html: str, config: dict) -> BeautifulSoup:
    """Parse HTML and strip noise elements before text extraction."""
    soup = BeautifulSoup(html, "html.parser")

    selectors = config.get("cleaning", {}).get("strip_selectors", [])
    for sel in selectors:
        for el in soup.select(sel):
            el.decompose()

    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    return soup


def clean_text(text: str, config: dict) -> str:
    """Remove noise patterns from extracted text."""
    patterns = config.get("cleaning", {}).get("strip_text_patterns", [])
    lines = text.split("\n")
    cleaned = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        skip = False
        for pat in patterns:
            if re.match(pat, stripped, re.I | re.M):
                skip = True
                break
        if not skip:
            cleaned.append(stripped)

    result = "\n".join(cleaned)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def extract_clean_text(html: str, config: dict) -> str:
    """Full pipeline: parse HTML, strip elements, clean text."""
    soup = clean_html(html, config)
    raw_text = soup.get_text(separator="\n", strip=True)
    return clean_text(raw_text, config)


def extract_headings(html: str, config: dict) -> list[str]:
    """Extract h1-h3 headings from cleaned HTML."""
    soup = clean_html(html, config)
    return [h.get_text(strip=True) for h in soup.find_all(re.compile(r"^h[1-3]$"))]


def extract_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.title.string.strip() if soup.title and soup.title.string else ""
