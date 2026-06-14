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
    # Canonical local port is 7070 (mira-kontext-api docker-compose + .env.example).
    # The old 8080 default predated that; .env still overrides this when present.
    kontext_api_url: str = Field(default="http://localhost:7070")
    kontext_token: str | None = Field(default=None)

    # Retrieval transport: "mcp" (query_context over Streamable HTTP, the agent wire
    # protocol per ADR 0005) or "rest" (POST /v1/query). MCP and REST share the same
    # QueryService + ACL server-side, so results match; MCP is the production-parity path.
    retrieval_transport: str = Field(default="mcp")  # mcp | rest
    # Streamable-HTTP MCP endpoint (compose `mcp` service publishes 7072, path /mcp).
    mcp_url: str = Field(default="http://localhost:7072/mcp")

    # Reranking (precision stage between retrieval and answer). We retrieve a wide
    # candidate set, then a listwise LLM reranker re-scores by text relevance and we
    # keep the top-K — this fixes "loads everything" even when vector recall is weak.
    rerank_enabled: bool = Field(default=True)
    rerank_candidates: int = Field(default=20)  # how many to retrieve before reranking
    rerank_top_k: int = Field(default=5)  # how many to keep after reranking
    rerank_min_score: float = Field(default=0.0)  # drop candidates below this (0..1)
    rerank_model: str | None = Field(default=None)  # defaults to llm_model (gpt-oss-120b)
    rerank_timeout: float = Field(default=20.0)

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
    nebius_api_key: str | None = Field(default=None)
    llm_api_key: str | None = Field(default=None)
    llm_base_url: str = Field(default="https://api.tokenfactory.nebius.com/v1/")
    llm_model: str = Field(default="openai/gpt-oss-120b")
    llm_timeout: float = Field(default=30.0)
    llm_provider: str = Field(default="nebius")  # nebius, openai, ollama, openrouter

    # Fast intent classification configuration
    intent_api_key: str | None = Field(default=None)
    intent_base_url: str = Field(default="https://api.tokenfactory.nebius.com/v1/")
    intent_model: str = Field(default="openai/gpt-oss-120b")
    intent_provider: str = Field(default="nebius")
    intent_confidence_threshold: float = Field(default=0.75)
    intent_timeout: float = Field(default=8.0)

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
