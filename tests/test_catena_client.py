"""Tests for CatenaClient (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mira_kontext_testing_bot.catena_client import CatenaClient
from mira_kontext_testing_bot.errors import AuthenticationError, CatenaAPIError


@pytest.mark.asyncio
async def test_chat_returns_final_envelope() -> None:
    client = CatenaClient(base_url="http://catena.test", token="test-token")
    mock_response = httpx.Response(
        200,
        json={
            "type": "final",
            "thread_id": "42",
            "flow_type": "router",
            "text": "Hello from Catena",
            "data": None,
        },
        request=httpx.Request("POST", "http://catena.test/chat"),
    )

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        await client.connect()
        result = await client.chat("Hi", thread_id="42", flow_id="router")
        await client.close()

    assert result.text == "Hello from Catena"
    assert result.thread_id == "42"
    assert result.flow_type == "router"


@pytest.mark.asyncio
async def test_me_parses_user_profile() -> None:
    client = CatenaClient(base_url="http://catena.test", token="test-token")
    mock_response = httpx.Response(
        200,
        json={
            "id": 7,
            "email": "user@catena.ai",
            "is_admin": False,
            "first_name": "Ada",
            "last_name": "Lovelace",
        },
        request=httpx.Request("GET", "http://catena.test/auth/me"),
    )

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        await client.connect()
        user = await client.me()
        await client.close()

    assert user.id == 7
    assert user.email == "user@catena.ai"
    assert user.display_name == "Ada Lovelace"


@pytest.mark.asyncio
async def test_chat_empty_text_raises() -> None:
    client = CatenaClient(base_url="http://catena.test", token="test-token")
    mock_response = httpx.Response(
        200,
        json={"type": "final", "text": "   "},
        request=httpx.Request("POST", "http://catena.test/chat"),
    )

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        await client.connect()
        with pytest.raises(CatenaAPIError, match="empty response"):
            await client.chat("Hi")
        await client.close()


@pytest.mark.asyncio
async def test_me_auth_error() -> None:
    client = CatenaClient(base_url="http://catena.test", token="bad-token")
    mock_response = httpx.Response(
        401,
        json={"detail": "Invalid token"},
        request=httpx.Request("GET", "http://catena.test/auth/me"),
    )

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        await client.connect()
        with pytest.raises(AuthenticationError):
            await client.me()
        await client.close()
