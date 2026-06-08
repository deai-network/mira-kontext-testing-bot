"""Tests for CatenaMemoryBridge."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from mira_kontext_testing_bot.catena_bridge import CatenaMemoryBridge
from mira_kontext_testing_bot.catena_client import CatenaChatResult, CatenaUser
from mira_kontext_testing_bot.models import Principal, Project, Session
from mira_kontext_testing_bot.session import ChatContext


def _context() -> ChatContext:
    project = Project(external_id="proj-1", title="Test")
    session = Session(external_id="thread-1", project_external_id="proj-1")
    principal = Principal(external_id="catena:pending")
    return ChatContext(project=project, session=session, principal=principal, mode="memory_only")


@pytest.mark.asyncio
async def test_run_turn_stores_user_and_assistant() -> None:
    catena = AsyncMock()
    kontext = AsyncMock()
    bridge = CatenaMemoryBridge(catena, kontext)

    catena.me.return_value = CatenaUser(id=3, email="a@b.com", is_admin=False)
    kontext.get_recent_memory.return_value = []
    kontext.search_memory.return_value = []
    kontext.write_memory_message.side_effect = [
        {"message_id": "u1"},
        {"message_id": "a1"},
    ]
    catena.chat.return_value = CatenaChatResult(
        text="Answer",
        thread_id="thread-1",
        flow_type="router",
        raw={},
    )

    result = await bridge.run_turn(_context(), "Question?", flow_id="router")

    assert result.catena.text == "Answer"
    assert kontext.write_memory_message.await_count == 2
    catena.chat.assert_awaited_once_with(
        "Question?",
        thread_id="thread-1",
        flow_id="router",
    )


@pytest.mark.asyncio
async def test_principal_from_catena_user() -> None:
    bridge = CatenaMemoryBridge(AsyncMock(), AsyncMock())
    user = CatenaUser(id=9, email="x@y.com", is_admin=True, first_name="Cat", last_name="ena")
    principal = bridge.principal_from_catena_user(user)
    assert principal.external_id == "catena:user:9"
    assert principal.email == "x@y.com"
    assert "admin" in principal.roles
