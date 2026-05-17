"""Fast intent classification for natural-language bot actions."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal, Protocol

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .config import get_settings

IntentName = Literal[
    "chat",
    "ingest_source",
    "query_sources",
    "list_sources",
    "get_document",
    "search_memory",
    "web_search",
]

_WRITE_INTENT_RE = re.compile(
    r"\b(ingest|store|save|add|remember|archive|upload|index)\b",
    re.IGNORECASE,
)
_NON_ACTIONABLE_WRITE_RE = re.compile(
    r"\b(could|would|should|might|can)\s+"
    r"(ingest|store|save|add|remember|archive|upload|index)\b|"
    r"\b(draft|prepare|write|generate)\b.*\b"
    r"(could|would|should|might|can)\s+"
    r"(ingest|store|save|add|remember|archive|upload|index)\b",
    re.IGNORECASE,
)


class IntentDecision(BaseModel):
    """Structured action decision from the fast classifier."""

    model_config = ConfigDict(extra="forbid")

    intent: IntentName = "chat"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    title: str | None = None
    content: str | None = None
    query: str | None = None
    short_id: str | None = None
    source_system: str | None = None
    source_object_type: str | None = None
    source_object_id: str | None = None
    collection_external_id: str | None = None
    reason: str | None = None

    @classmethod
    def chat(cls, reason: str | None = None) -> IntentDecision:
        """Return a safe fallback decision."""
        return cls(intent="chat", confidence=0.0, reason=reason)

    def is_actionable(self, raw_message: str, threshold: float = 0.75) -> bool:
        """Whether this decision may execute an action without further clarification."""
        if self.confidence < threshold:
            return False
        if self.intent == "chat":
            return False
        if self.intent == "ingest_source":
            if _NON_ACTIONABLE_WRITE_RE.search(raw_message):
                return False
            return bool(self.content and _WRITE_INTENT_RE.search(raw_message))
        if self.intent == "query_sources":
            return bool(self.query or raw_message.strip())
        if self.intent == "web_search":
            return bool(self.query or raw_message.strip())
        if self.intent == "get_document":
            return bool(self.short_id)
        return True


class IntentClassifier:
    """OpenAI-compatible client for fast action classification."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        confidence_threshold: float | None = None,
        timeout: float | None = None,
        client: ClassifierClientProtocol | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = (
            api_key
            if api_key is not None
            else (settings.intent_api_key or settings.nebius_api_key)
        )
        self.base_url = (base_url or settings.intent_base_url).rstrip("/")
        self.model = model or settings.intent_model
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.intent_confidence_threshold
        )
        self.timeout = timeout if timeout is not None else settings.intent_timeout

        http_client: httpx.AsyncClient | None = None
        if not client:
            logger = logging.getLogger("mira_testing_bot.api")
            logger.setLevel(logging.DEBUG)
            if not logger.handlers:
                fh = logging.FileHandler("bot_api_requests.log")
                fh.setLevel(logging.DEBUG)
                formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
                fh.setFormatter(formatter)
                logger.addHandler(fh)

            async def log_request(request: httpx.Request) -> None:
                await request.aread()
                body = request.content.decode("utf-8", errors="replace")
                try:
                    if body:
                        body = json.dumps(json.loads(body), indent=2)
                except Exception:
                    pass
                logger.debug(
                    "--> Request: %s %s\nHeaders: %s\nPayload:\n%s",
                    request.method,
                    request.url,
                    dict(request.headers),
                    body,
                )

            async def log_response(response: httpx.Response) -> None:
                await response.aread()
                body = response.text
                try:
                    if body:
                        body = json.dumps(json.loads(body), indent=2)
                except Exception:
                    pass
                logger.debug(
                    "<-- Response: %s %s - Status %s\nPayload:\n%s\n%s",
                    response.request.method,
                    response.request.url,
                    response.status_code,
                    body,
                    "-" * 80,
                )

            http_client = httpx.AsyncClient(
                timeout=self.timeout,
                event_hooks={"request": [log_request], "response": [log_response]},
            )

        self._client = client or AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            http_client=http_client,
        )

    @property
    def is_configured(self) -> bool:
        """Whether classifier calls can be made."""
        return bool(self.api_key)

    async def classify(self, raw_message: str) -> IntentDecision:
        """Classify a raw user message into a safe action decision."""
        if not self.is_configured:
            return IntentDecision.chat("intent classifier not configured")

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                temperature=0,
                max_tokens=350,
                messages=[
                    {
                        "role": "system",
                        "content": _INTENT_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": raw_message}],
                    },
                ],
            )
            content = response.choices[0].message.content if response.choices else None
            if not isinstance(content, str):
                raise TypeError("intent classifier content must be a string")
            decision = _parse_decision(content)
            if not decision.is_actionable(raw_message, self.confidence_threshold):
                if decision.intent == "ingest_source":
                    return IntentDecision.chat("ingest intent was not explicit or complete")
                if decision.confidence < self.confidence_threshold:
                    return IntentDecision.chat("intent confidence below threshold")
            return decision
        except (KeyError, TypeError, ValueError, ValidationError, AttributeError):
            return IntentDecision.chat("intent classifier failed")


def _parse_decision(content: str) -> IntentDecision:
    return _DECISION_ADAPTER.validate_json(content)


_DECISION_ADAPTER: TypeAdapter[IntentDecision] = TypeAdapter(IntentDecision)


class ClassifierClientProtocol(Protocol):
    chat: Any

_INTENT_SYSTEM_PROMPT = """Classify the user's raw message for a testing bot.
Return only compact JSON with these fields:
intent: one of chat, ingest_source, query_sources, list_sources, get_document, search_memory, web_search.
confidence: number from 0 to 1.
title, content, query, short_id, source_system, source_object_type, source_object_id,
collection_external_id: optional strings or null.

Rules:
- Use ingest_source only when the user explicitly asks to ingest, store, save, add, upload, or
  index content into the knowledge base. Include the exact content to store.
- Use chat when the user asks to draft, discuss, explain, or prepare content without explicitly
  asking to write it.
- Use web_search when the user explicitly asks for online research, web search, crawling, or
  fetching internet sources. Put the best search string in query.
- Do not infer actions from previous messages or external context.
- For private/default ingest, set collection_external_id to null.
- Prefer safe chat fallback when uncertain.
"""
