"""Integration checks against https://docs.ollama.com/cloud documented endpoints."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_ollama_cloud_tags_lists_qwen_variants():
    """Public catalog must include at least one Qwen model name (regression guard)."""

    httpx_mod = pytest.importorskip("httpx")
    resp = httpx_mod.get("https://ollama.com/api/tags", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    models = data.get("models") or []
    names = [m["name"] for m in models if isinstance(m, dict) and "name" in m]
    qwen = [n for n in names if "qwen" in n.lower()]
    assert qwen, f"Expected at least one qwen-* tag; got none in {names[:15]}..."
    assert "qwen3-next:80b" in names or "qwen3.5:397b" in names, (
        "Expected canonical Qwen tags; refresh this test if catalog renames models."
    )
