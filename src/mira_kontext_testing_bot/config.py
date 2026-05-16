"""Configuration settings for the testing bot."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Bot configuration loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Configuration
    kontext_api_url: str = Field(default="http://localhost:8080")
    kontext_token: str | None = Field(default=None)

    # Bot Identity
    bot_principal_id: str = Field(default="testing-bot")
    bot_display_name: str = Field(default="Mira Kontext Testing Bot")
    bot_roles: list[str] = Field(default_factory=lambda: ["tester", "admin"])

    # Default Project/Session
    default_project_id: str = Field(default="default-test-project")
    default_project_title: str = Field(default="Default Test Project")
    default_session_id: str = Field(default="default-test-session")
    default_session_title: str = Field(default="Default Test Session")

    # Test Configuration
    test_tenant_prefix: str = Field(default="test-bot")
    request_timeout: float = Field(default=30.0)
    debug: bool = Field(default=False)

    # LLM Configuration
    llm_api_key: str | None = Field(default=None)
    llm_base_url: str = Field(default="https://api.openai.com/v1")
    llm_model: str = Field(default="gpt-4o-mini")
    llm_timeout: float = Field(default=30.0)
    llm_provider: str = Field(default="openai")  # openai, ollama, openrouter

    # Web Fetching Configuration
    firecrawl_api_key: str | None = Field(default=None)
    auto_web_search: bool = Field(default=True)  # Propose web search when no local results found


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def load_env_file(path: Path | None = None) -> None:
    """Load environment variables from .env file if present."""
    if path is None:
        path = Path(".env")
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in __import__("os").environ:
            continue
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1].strip()
        __import__("os").environ[key] = value
