"""Tests for data models."""

import pytest
from pydantic import ValidationError

from mira_kontext_testing_bot.models import (
    Message,
    Principal,
    Project,
    ScenarioOutcome,
    Session,
    SuiteOutcome,
)


class TestMessage:
    """Tests for Message model."""

    def test_valid_message(self):
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.metadata == {}

    def test_invalid_role(self):
        with pytest.raises(ValidationError):
            Message(role="invalid", content="Hello")

    def test_empty_content(self):
        with pytest.raises(ValidationError):
            Message(role="user", content="")


class TestProject:
    """Tests for Project model."""

    def test_valid_project(self):
        proj = Project(external_id="proj-1", title="Test Project")
        assert proj.external_id == "proj-1"
        assert proj.title == "Test Project"

    def test_default_metadata(self):
        proj = Project(external_id="proj-1")
        assert proj.metadata == {}


class TestSession:
    """Tests for Session model."""

    def test_valid_session(self):
        sess = Session(
            external_id="sess-1",
            title="Test Session",
            project_external_id="proj-1",
        )
        assert sess.external_id == "sess-1"
        assert sess.project_external_id == "proj-1"


class TestPrincipal:
    """Tests for Principal model."""

    def test_valid_principal(self):
        principal = Principal(
            external_id="user-1",
            display_name="Test User",
            roles=["admin", "user"],
        )
        assert principal.external_id == "user-1"
        assert principal.display_name == "Test User"
        assert principal.roles == ["admin", "user"]

    def test_default_roles(self):
        principal = Principal(external_id="user-1")
        assert principal.roles == []


class TestScenarioOutcome:
    """Tests for ScenarioOutcome model."""

    def test_passed_result(self):
        result = ScenarioOutcome(
            scenario_name="test",
            passed=True,
            duration_ms=100.0,
        )
        assert result.passed is True
        assert result.error_message is None

    def test_failed_result(self):
        result = ScenarioOutcome(
            scenario_name="test",
            passed=False,
            duration_ms=50.0,
            error_message="Something failed",
        )
        assert result.passed is False
        assert result.error_message == "Something failed"


class TestSuiteOutcome:
    """Tests for SuiteOutcome model."""

    def test_success_rate(self):
        suite = SuiteOutcome(
            suite_name="full",
            results=[
                ScenarioOutcome(scenario_name="a", passed=True, duration_ms=10.0),
                ScenarioOutcome(scenario_name="b", passed=True, duration_ms=10.0),
                ScenarioOutcome(scenario_name="c", passed=False, duration_ms=10.0),
            ],
            total=3,
            passed=2,
            failed=1,
            duration_ms=30.0,
        )
        assert suite.success_rate == pytest.approx(100.0 * 2 / 3)

    def test_zero_success_rate(self):
        suite = SuiteOutcome(
            suite_name="empty",
            results=[],
            total=0,
            passed=0,
            failed=0,
            duration_ms=0.0,
        )
        assert suite.success_rate == 0.0
