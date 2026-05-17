"""Tests for natural-language intent classification."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mira_kontext_testing_bot.intent_classifier import IntentClassifier, IntentDecision


def test_intent_decision_requires_explicit_write_intent_for_ingest() -> None:
    decision = IntentDecision(
        intent="ingest_source",
        confidence=0.96,
        content="Synthetic supply chain dataset",
        title="Supply chain dataset",
    )

    assert decision.is_actionable("please ingest this supply chain dataset") is True
    assert decision.is_actionable("draft a supply chain dataset I could ingest later") is False


def test_intent_decision_rejects_underspecified_ingest() -> None:
    decision = IntentDecision(intent="ingest_source", confidence=0.98)

    assert decision.is_actionable("store this") is False


def test_intent_decision_allows_web_search_queries() -> None:
    decision = IntentDecision(intent="web_search", confidence=0.92, query="p&g supply chain")

    assert decision.is_actionable("can you research p&g supply chain online?") is True


@pytest.mark.asyncio
async def test_classifier_parses_openai_compatible_json_response() -> None:
    class FakeCompletions:
        async def create(self, **kwargs: object) -> object:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"intent":"list_sources","confidence":0.91,"query":null,"content":null}'
                        )
                    )
                ]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    classifier = IntentClassifier(
        api_key="test-key",
        base_url="https://classifier.test",
        model="qwen-test",
        confidence_threshold=0.75,
        client=client,
    )

    decision = await classifier.classify("show my sources")

    assert decision.intent == "list_sources"
    assert decision.confidence == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_classifier_falls_back_to_chat_on_invalid_json() -> None:
    class FakeCompletions:
        async def create(self, **kwargs: object) -> object:
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    classifier = IntentClassifier(
        api_key="test-key",
        base_url="https://classifier.test",
        model="nemotron-test",
        confidence_threshold=0.75,
        client=client,
    )

    decision = await classifier.classify("hello")

    assert decision.intent == "chat"
    assert decision.confidence == 0.0
