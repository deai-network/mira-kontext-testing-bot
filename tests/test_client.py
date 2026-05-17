"""Tests for Kontext API client behavior."""

from __future__ import annotations

import json

import httpx
import pytest

from mira_kontext_testing_bot.client import KontextClient
from mira_kontext_testing_bot.errors import SourceIsolationError, ValidationError
from mira_kontext_testing_bot.models import Principal


@pytest.mark.asyncio
async def test_ingest_fails_closed_when_api_rejects_principal_aware_payload() -> None:
    calls: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        calls.append(payload)
        if len(calls) == 1:
            return httpx.Response(
                422,
                json={
                    "detail": [
                        {
                            "type": "extra_forbidden",
                            "loc": ["body", "principal"],
                            "msg": "Extra inputs are not permitted",
                            "input": {"external_id": "t1"},
                        },
                        {
                            "type": "extra_forbidden",
                            "loc": ["body", "collection_external_id"],
                            "msg": "Extra inputs are not permitted",
                            "input": "user-t1-private",
                        },
                    ]
                },
            )
        raise AssertionError("legacy retry must not run for isolation-sensitive ingest")

    client = KontextClient(base_url="https://api.test", token="token")
    client._client = httpx.AsyncClient(  # pyright: ignore[reportPrivateUsage]
        base_url="https://api.test",
        transport=httpx.MockTransport(handler),
    )

    try:
        with pytest.raises(SourceIsolationError, match="source collection isolation"):
            await client.ingest_record(
                content="dataset",
                source_system="test",
                source_object_type="dataset",
                source_object_id="dataset-1",
                principal=Principal(external_id="t1"),
                collection_external_id="user-t1-private",
            )
        assert client.source_collections_supported is False
        assert len(calls) == 1
        assert "principal" in calls[0]
        assert "collection_external_id" in calls[0]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_query_fails_closed_when_api_rejects_source_collection_scope() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "detail": [
                    {
                        "type": "extra_forbidden",
                        "loc": ["body", "source_collections"],
                        "msg": "Extra inputs are not permitted",
                        "input": ["user-t1-private"],
                    }
                ]
            },
        )

    client = KontextClient(base_url="https://api.test", token="token")
    client._client = httpx.AsyncClient(  # pyright: ignore[reportPrivateUsage]
        base_url="https://api.test",
        transport=httpx.MockTransport(handler),
    )

    try:
        with pytest.raises(SourceIsolationError, match="source collection isolation"):
            await client.query(
                query="supply chain",
                principal=Principal(external_id="t1"),
                source_collections=["user-t1-private"],
            )
        assert client.source_collections_supported is False
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_ingest_raises_validation_error_when_legacy_retry_also_fails() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "detail": [
                    {
                        "type": "value_error",
                        "loc": ["body", "source_system"],
                        "msg": "invalid source system",
                        "input": "bad",
                    }
                ]
            },
        )

    client = KontextClient(base_url="https://api.test", token="token")
    client._client = httpx.AsyncClient(  # pyright: ignore[reportPrivateUsage]
        base_url="https://api.test",
        transport=httpx.MockTransport(handler),
    )

    try:
        with pytest.raises(ValidationError, match="Validation error"):
            await client.ingest_record(
                content="dataset",
                source_system="bad",
                source_object_type="dataset",
                source_object_id="dataset-1",
                principal=Principal(external_id="t1"),
            )
    finally:
        await client.close()
