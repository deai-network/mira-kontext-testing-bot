"""
Step D/E: Process scraped pages and additional documents into chunks.

Reads from data/scraped/ and produces data/chunks/chunks.json.
Handles: web pages, FAQs, product sheets, generic markdown.
"""
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "01_pipeline_setup"))
from pipeline_config import load_config, ensure_data_dirs

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def generate_doc_id(content: str) -> str:
    return "doc_" + hashlib.md5(content.encode()).hexdigest()[:12]


def detect_language(text: str) -> str:
    de = len(re.findall(r"\b(und|die|der|ist|für|mit|ein|eine)\b", text, re.I))
    en = len(re.findall(r"\b(the|and|is|for|with|from|that|are)\b", text, re.I))
    return "de" if de >= en else "en"


def classify_content(text: str) -> list[str]:
    t = text.lower()
    cats: list[str] = []
    if any(w in t for w in ["unternehmen", "über uns", "company", "about us", "team", "agentur"]):
        cats.append("company_overview")
    if any(w in t for w in ["produkt", "product", "service", "leistung", "angebot"]):
        cats.append("products_services")
    if any(w in t for w in ["faq", "frage", "question", "hilfe", "support"]):
        cats.append("customer_service")
    if any(w in t for w in ["projekt", "project", "referenz", "case stud"]):
        cats.append("projects")
    if any(w in t for w in ["kontakt", "contact", "impressum"]):
        cats.append("contact")
    if any(w in t for w in ["datenschutz", "privacy", "agb", "terms"]):
        cats.append("legal")
    return cats or ["general"]


# ---------------------------------------------------------------------------
# Chunking strategies
# ---------------------------------------------------------------------------

def chunk_web_page(page: dict, config: dict) -> list[dict]:
    """Chunk a scraped web page by paragraphs, respecting chunk_size."""
    text = page.get("text", "").strip()
    if not text:
        return []

    url = page.get("url", "")
    title = page.get("title", "")
    chunk_size = config["processing"]["chunk_size"]
    lang = detect_language(text)

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    chunks = []
    current_lines: list[str] = []
    current_len = 0

    def finalize():
        nonlocal current_lines, current_len
        if not current_lines:
            return
        chunk_text = "\n\n".join(current_lines)
        chunks.append({
            "doc_id": generate_doc_id(f"{url}_{len(chunks)}"),
            "content": chunk_text,
            "chunk_type": "web",
            "content_categories": classify_content(chunk_text),
            "language": lang,
            "source_url": url,
            "source_title": title,
            "chunk_length": len(chunk_text),
        })
        current_lines = []
        current_len = 0

    for para in paragraphs:
        if current_len + len(para) > chunk_size and current_len > 0:
            finalize()
        current_lines.append(para)
        current_len += len(para)

    finalize()
    return chunks


def chunk_faq(text: str, filename: str) -> list[dict]:
    """Split FAQ content into Q&A chunks."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    q, a_parts = "", []

    def finalize():
        nonlocal q, a_parts
        if not q or not a_parts:
            return
        answer = " ".join(a_parts)
        chunks.append({
            "doc_id": generate_doc_id(f"faq_{q}"),
            "content": f"Q: {q}\nA: {answer}",
            "chunk_type": "faq",
            "content_categories": ["customer_service", "faq"],
            "language": detect_language(answer),
            "metadata": {"question": q, "original_filename": filename},
        })
        q, a_parts = "", []

    for p in paragraphs:
        if p.endswith("?") or re.match(r"^(Frage|Question|Q)\s*:", p, re.I):
            finalize()
            q = p
        elif p.startswith("#"):
            continue
        else:
            a_parts.append(p)

    finalize()
    return chunks


def chunk_product_sheet(text: str, filename: str) -> list[dict]:
    """Chunk a product data sheet by section headers."""
    section_headers = [
        "Zutaten", "Zusammensetzung", "Hinweise", "Anwendung",
        "Verzehrempfehlung", "Ingredients", "Composition", "Usage",
        "Warnings", "Dosage", "Description",
    ]
    pattern = r"\n(?=(?:" + "|".join(section_headers) + r")\s*:?)"
    sections = [s.strip() for s in re.split(pattern, text, flags=re.I) if s.strip()]

    chunks = []
    for i, section in enumerate(sections):
        chunks.append({
            "doc_id": generate_doc_id(f"prod_{filename}_{i}"),
            "content": section,
            "chunk_type": "product",
            "content_categories": ["products_services"],
            "language": detect_language(section),
            "metadata": {"original_filename": filename, "section_index": i},
        })
    return chunks


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def process_scraped_pages(pages: list[dict], config: dict) -> list[dict]:
    all_chunks = []
    for page in pages:
        all_chunks.extend(chunk_web_page(page, config))
    return all_chunks


def process_additional_file(filepath: Path, config: dict) -> list[dict]:
    """Process a single additional document (md, txt)."""
    text = filepath.read_text(encoding="utf-8")
    name = filepath.name.lower()

    if "faq" in name:
        return chunk_faq(text, filepath.name)
    if any(k in name for k in ["lmiv", "product", "produkt", "sheet"]):
        return chunk_product_sheet(text, filepath.name)

    # Default: treat as web-like content
    return chunk_web_page({"text": text, "url": "", "title": filepath.stem}, config)


def run_processing():
    config = load_config()
    data_dir = ensure_data_dirs()
    scraped_file = data_dir / "scraped" / "scraped_pages.json"
    out_file = data_dir / "chunks" / "chunks.json"

    all_chunks: list[dict] = []

    # 1. Process scraped pages
    if scraped_file.exists():
        pages = json.loads(scraped_file.read_text())
        print(f"Processing {len(pages)} scraped pages...")
        all_chunks.extend(process_scraped_pages(pages, config))
    else:
        print(f"No scraped data found at {scraped_file}. Run the scraper first.")

    # 2. Process additional documents from data/additional/
    additional_dir = data_dir / "additional"
    if additional_dir.exists():
        for fp in sorted(additional_dir.glob("*")):
            if fp.suffix in (".md", ".txt"):
                print(f"Processing additional file: {fp.name}")
                all_chunks.extend(process_additional_file(fp, config))

    # 3. Save
    with open(out_file, "w") as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)

    print(f"\nGenerated {len(all_chunks)} chunks -> {out_file}")

    # Quick stats
    types = {}
    for c in all_chunks:
        t = c.get("chunk_type", "unknown")
        types[t] = types.get(t, 0) + 1
    print(f"Chunk types: {json.dumps(types)}")

    return all_chunks


if __name__ == "__main__":
    run_processing()
