"""Listwise reranker for retrieved context items.

Sits between retrieval and answer generation. Vector recall (especially with weak or
stub embeddings) returns a noisy candidate set ordered by a near-meaningless score;
this re-scores each candidate by *text* relevance to the query using the same Nebius
OSS chat model the bot already uses (gpt-oss-120b), then keeps the top-K above a
threshold. That is what stops the bot from dumping everything into the LLM context.

Fail-open: any rerank error returns the original order truncated to top-K, so a flaky
reranker degrades to plain retrieval rather than breaking chat.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from openai import AsyncOpenAI

from .config import get_settings
from .models import ContextItem

_SYSTEM_PROMPT = (
    "You are a precise search-result reranker. You are given a user query and a list of "
    "numbered candidate passages. Score how well each passage answers the query on a "
    "scale from 0.0 (irrelevant) to 1.0 (directly answers it). Judge by the passage "
    "text, not its position. Respond with ONLY a JSON array of objects "
    '{"index": <int>, "score": <float>} covering every candidate. No prose.'
)


class Reranker:
    """Reranks `ContextItem`s by query relevance using a listwise LLM call."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.llm_api_key or settings.nebius_api_key
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.rerank_model or settings.llm_model
        self.timeout = timeout or settings.rerank_timeout
        self.min_score = settings.rerank_min_score

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def rerank(
        self,
        query: str,
        items: list[ContextItem],
        top_k: int,
    ) -> list[ContextItem]:
        """Return the top-K items reordered by relevance to `query`.

        Each returned item carries its relevance under `metadata["_rerank_score"]`.
        """
        if not items:
            return []
        # Nothing to gain from a model call when the candidate set already fits.
        if not self.configured or len(items) == 1:
            return items[:top_k]

        try:
            scores = await self._score(query, items)
        except Exception:  # noqa: BLE001 - fail open to plain retrieval order
            return items[:top_k]

        ranked: list[tuple[ContextItem, float]] = []
        for idx, item in enumerate(items):
            score = scores.get(idx)
            if score is None:
                continue
            if score < self.min_score:
                continue
            item.metadata = {**item.metadata, "_rerank_score": round(score, 4)}
            ranked.append((item, score))

        if not ranked:
            # The model returned nothing usable above threshold — don't silently drop
            # all context; fall back to original order.
            return items[:top_k]

        ranked.sort(key=lambda pair: pair[1], reverse=True)
        return [item for item, _ in ranked[:top_k]]

    async def _score(self, query: str, items: list[ContextItem]) -> dict[int, float]:
        candidates = "\n\n".join(
            f"[{idx}] {(item.title or 'Untitled')}\n{item.snippet}"
            for idx, item in enumerate(items)
        )
        user = f"Query: {query}\n\nCandidates:\n{candidates}"

        async with httpx.AsyncClient(timeout=self.timeout) as http_client:
            client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                http_client=http_client,
            )
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                temperature=0.0,
                max_tokens=600,
            )
        content = response.choices[0].message.content if response.choices else None
        return _parse_scores(content or "")


def _parse_scores(content: str) -> dict[int, float]:
    """Extract {index: score} from the model output, tolerating stray prose."""
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if not match:
        return {}
    try:
        parsed: Any = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    scores: dict[int, float] = {}
    if isinstance(parsed, list):
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            idx = entry.get("index")
            score = entry.get("score")
            if isinstance(idx, int) and isinstance(score, (int, float)):
                scores[idx] = max(0.0, min(1.0, float(score)))
    return scores
