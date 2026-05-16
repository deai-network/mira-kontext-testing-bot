"""Tests for session management."""

import pytest

from mira_kontext_testing_bot.models import Principal, Project, Session
from mira_kontext_testing_bot.session import ChatContext, SessionManager


class TestChatContext:
    """Tests for ChatContext."""

    @pytest.fixture
    def basic_context(self):
        project = Project(external_id="proj-1", title="Project 1")
        session = Session(
            external_id="sess-1",
            title="Session 1",
            project_external_id="proj-1",
        )
        principal = Principal(external_id="user-1", display_name="User")
        return ChatContext(project=project, session=session, principal=principal)

    def test_add_message(self, basic_context):
        basic_context.add_message("user", "Hello")
        assert len(basic_context.messages) == 1
        assert basic_context.messages[0].role == "user"
        assert basic_context.messages[0].content == "Hello"

    def test_get_recent_context(self, basic_context):
        for i in range(15):
            basic_context.add_message("user", f"Message {i}")

        recent = basic_context.get_recent_context(window=5)
        assert len(recent) == 5
        assert recent[-1].content == "Message 14"

    def test_to_api_format(self, basic_context):
        api_format = basic_context.to_api_format()
        assert api_format["project_external_id"] == "proj-1"
        assert api_format["session_external_id"] == "sess-1"
        assert api_format["principal_external_id"] == "user-1"


class TestSessionManager:
    """Tests for SessionManager."""

    @pytest.fixture
    def manager(self):
        return SessionManager()

    def test_create_project(self, manager):
        project = manager.create_project("proj-1", title="Test Project")
        assert project.external_id == "proj-1"
        assert project.title == "Test Project"

    def test_create_session(self, manager):
        project = manager.create_project("proj-1")
        session = manager.create_session(
            project=project,
            external_id="sess-1",
            title="Test Session",
        )
        assert session.external_id == "sess-1"
        assert session.project_external_id == "proj-1"

    def test_create_context(self, manager):
        project = manager.create_project("proj-1")
        session = manager.create_session(project=project)
        principal = Principal(external_id="user-1")

        context = manager.create_context(project, session, principal)
        assert context.project == project
        assert context.session == session
        assert context.principal == principal

    def test_create_principal_tracks_known_users(self, manager):
        principal = manager.create_principal(
            external_id="analyst@example.com",
            display_name="Analyst",
            roles=["tester"],
        )

        assert principal.external_id == "analyst@example.com"
        assert principal.display_name == "Analyst"
        assert manager.list_users() == [("analyst@example.com", "Analyst", "tester")]

    def test_create_blank_context_for_user_starts_empty_session(self, manager):
        project = manager.create_project("proj-1")
        existing_session = manager.create_session(project=project, external_id="sess-1")
        existing_user = manager.create_principal("existing-user")
        existing_context = manager.create_context(project, existing_session, existing_user)
        existing_context.add_message("user", "Existing memory")

        blank_user = manager.create_principal("blank-user")
        blank_context = manager.create_blank_context_for_user(project, blank_user)

        assert blank_context.principal.external_id == "blank-user"
        assert blank_context.project == project
        assert blank_context.session.external_id != existing_session.external_id
        assert blank_context.session.metadata["blank_memory"] is True
        assert blank_context.messages == []
        assert manager.get_conversation_history(blank_context.session.external_id) == []

    def test_get_context(self, manager):
        project = manager.create_project("proj-1")
        session = manager.create_session(project=project, external_id="sess-1")
        context = manager.create_context(project, session)

        retrieved = manager.get_context("sess-1")
        assert retrieved == context

    def test_clear_context(self, manager):
        project = manager.create_project("proj-1")
        session = manager.create_session(project=project, external_id="sess-1")
        manager.create_context(project, session)

        assert manager.clear_context("sess-1") is True
        assert manager.get_context("sess-1") is None
        assert manager.clear_context("sess-1") is False

    def test_clear_all_contexts(self, manager):
        project = manager.create_project("proj-1")
        for i in range(3):
            session = manager.create_session(project, external_id=f"sess-{i}")
            manager.create_context(project, session)

        manager.clear_all_contexts()
        assert manager.list_active_sessions() == []

    def test_list_active_sessions(self, manager):
        project = manager.create_project("proj-1")
        for i in range(3):
            session = manager.create_session(project, external_id=f"sess-{i}", title=f"Session {i}")
            manager.create_context(project, session)

        sessions = manager.list_active_sessions()
        assert len(sessions) == 3
        assert sessions[0][3] == "testing-bot"
