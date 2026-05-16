"""Pytest fixtures for testing bot tests."""

import pytest


@pytest.fixture
def mock_settings():
    """Return mock settings for tests."""
    return {
        "kontext_api_url": "http://localhost:8080",
        "kontext_token": "test-token",
        "bot_principal_id": "test-bot",
        "bot_display_name": "Test Bot",
        "bot_roles": ["tester"],
        "default_project_id": "test-project",
        "default_session_id": "test-session",
    }
