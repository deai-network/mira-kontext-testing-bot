"""
Step D/E (final): Embed chunks and upload to Supabase.

Reads data/chunks/chunks.json, computes OpenAI embeddings,
and upserts into the knowledge_base_v3 table.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "01_pipeline_setup"))
from pipeline_config import load_config, ensure_data_dirs, get_env

# ---------------------------------------------------------------------------

def embed_texts(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    from openai import OpenAI
    client = OpenAI(api_key=get_env("OPENAI_API_KEY"))

    embeddings = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        print(f"  Embedding batch {i // batch_size + 1} ({len(batch)} items)...")
        resp = client.embeddings.create(input=batch, model=model)
        embeddings.extend([d.embedding for d in resp.data])
        time.sleep(0.2)

    return embeddings


def upload_to_supabase(chunks: list[dict], embeddings: list[list[float]], table: str):
    from supabase import create_client

    url = get_env("SUPABASE_URL")
    key = get_env("SUPABASE_SERVICE_KEY")
    sb = create_client(url, key)

    print(f"  Uploading {len(chunks)} rows to {table}...")
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        row = {
            "doc_id": chunk["doc_id"],
            "content": chunk["content"],
            "embedding": emb,
            "chunk_type": chunk.get("chunk_type", "general"),
            "content_categories": chunk.get("content_categories", []),
            "language": chunk.get("language", "de"),
            "source_url": chunk.get("source_url", ""),
            "source_type": chunk.get("chunk_type", "web"),
            "chunk_length": chunk.get("chunk_length", len(chunk["content"])),
            "metadata": json.dumps({
                k: v for k, v in chunk.items()
                if k not in ("doc_id", "content", "embedding")
            }),
        }
        sb.table(table).upsert(row, on_conflict="doc_id").execute()

        if (i + 1) % 50 == 0:
            print(f"    ... {i + 1}/{len(chunks)} uploaded")

    print(f"  Done. {len(chunks)} rows in {table}.")


def run_embed_and_upload():
    config = load_config()
    data_dir = ensure_data_dirs()
    chunks_file = data_dir / "chunks" / "chunks.json"
    table = config["database"]["table_name"]
    model = config["processing"]["embedding_model"]

    if not chunks_file.exists():
        print(f"No chunks found at {chunks_file}. Run process_documents.py first.")
        return

    chunks = json.loads(chunks_file.read_text())
    print(f"=== Embedding & Upload: {len(chunks)} chunks ===\n")

    texts = [c["content"] for c in chunks]
    embeddings = embed_texts(texts, model=model)

    upload_to_supabase(chunks, embeddings, table)
    print("\n=== Embedding & Upload complete ===")


if __name__ == "__main__":
    run_embed_and_upload()
