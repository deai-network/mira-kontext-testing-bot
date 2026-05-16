"""LLM client for generating responses using retrieved context."""

from __future__ import annotations

from typing import Any

import httpx

from .config import get_settings
from .errors import BotError


class LLMError(BotError):
    """Raised when LLM generation fails."""

    pass


class LLMClient:
    """Client for LLM API (OpenAI/Requesty/OpenRouter compatible)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.llm_api_key
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout = settings.llm_timeout

    async def generate_response(
        self,
        user_message: str,
        context: str,
        conversation_history: list[dict[str, str]],
        system_prompt: str | None = None,
    ) -> str:
        """Generate a response using the LLM."""
        if not self.api_key:
            raise LLMError("LLM API key not configured. Set LLM_API_KEY in .env")

        # Build messages
        messages: list[dict[str, str]] = []

        # System prompt
        default_system = (
            "You are a helpful assistant with access to a knowledge base. "
            "Use the provided context to answer the user's question. "
            "If the context doesn't contain relevant information, say so. "
            "Be concise but informative."
        )
        messages.append({"role": "system", "content": system_prompt or default_system})

        # Add context as a system message
        if context:
            messages.append({
                "role": "system",
                "content": f"Retrieved context:\n{context}",
            })

        # Add conversation history (last 10 messages)
        for msg in conversation_history[-10:]:
            messages.append(msg)

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        # Make request
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 1000,
                    },
                )
                response.raise_for_status()
                data = response.json()

                if "choices" in data and len(data["choices"]) > 0:
                    return str(data["choices"][0]["message"]["content"])
                else:
                    raise LLMError(f"Unexpected response format: {data}")

            except httpx.HTTPStatusError as exc:
                raise LLMError(f"LLM API error: {exc.response.status_code}") from exc
            except Exception as exc:
                raise LLMError(f"Failed to generate response: {exc}") from exc

    def generate_simple_response(
        self,
        user_message: str,
        context: str,
        conversation_history: list[dict[str, str]],
    ) -> str:
        """Synchronous wrapper for simple responses (fallback)."""
        import asyncio

        try:
            return asyncio.run(
                self.generate_response(user_message, context, conversation_history)
            )
        except LLMError:
            # Return a fallback response
            return self._fallback_response(user_message, context)

    def _fallback_response(self, user_message: str, context: str) -> str:
        """Generate a simple fallback response when LLM is unavailable."""
        lines: list[str] = []
        lines.append(f"You asked: '{user_message}'")

        if context:
            lines.append("\nBased on the retrieved context, here's what I found:")
            # Extract just the source titles from context
            for line in context.split("\n"):
                if line.strip().startswith(("1.", "2.", "3.", "4.", "5.")):
                    lines.append(line)

        lines.append(
            "\n[Note: LLM not configured. Set LLM_API_KEY in .env for AI-generated responses.]"
        )

        return "\n".join(lines)


class OllamaCloudClient:
    """Client for Ollama Cloud API (https://ollama.com)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.llm_api_key
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout = settings.llm_timeout

    async def generate_response(
        self,
        user_message: str,
        context: str,
        conversation_history: list[dict[str, str]],
        system_prompt: str | None = None,
    ) -> str:
        """Generate a response using Ollama Cloud API."""
        if not self.api_key:
            raise LLMError("OLLAMA_API_KEY not configured. Set it in .env")

        # Build messages
        messages: list[dict[str, str]] = []

        # System prompt
        default_system = (
            "You are a helpful assistant with access to a knowledge base. "
            "Use the provided context to answer the user's question. "
            "If the context doesn't contain relevant information, say so. "
            "Be concise but informative."
        )
        if system_prompt or default_system:
            messages.append({"role": "system", "content": system_prompt or default_system})

        # Add context as a system message
        if context:
            messages.append({
                "role": "system",
                "content": f"Retrieved context:\n{context}",
            })

        # Add conversation history
        for msg in conversation_history[-10:]:
            messages.append(msg)

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        # Make request to Ollama Cloud API
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": 0.7,
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()

                if "message" in data:
                    return str(data["message"]["content"])
                else:
                    raise LLMError(f"Unexpected response format: {data}")

            except httpx.HTTPStatusError as exc:
                error_body = exc.response.text
                hint = ""
                if exc.response.status_code == 404 and "not found" in error_body.lower():
                    hint = (
                        " List valid model names: curl https://ollama.com/api/tags "
                        "(see https://docs.ollama.com/cloud)."
                    )
                raise LLMError(
                    f"Ollama Cloud API error {exc.response.status_code}: {error_body}.{hint}",
                ) from exc
            except Exception as exc:
                raise LLMError(f"Failed to generate response: {exc}") from exc


class MockLLMClient:
    """Mock LLM client for testing without API calls."""

    async def generate_response(
        self,
        user_message: str,
        context: str,
        conversation_history: list[dict[str, str]],
        system_prompt: str | None = None,
    ) -> str:
        """Return a mock response that shows the user what would happen."""
        lines: list[str] = []
        lines.append(f"You asked: '{user_message}'")

        if context:
            lines.append("\nBased on the retrieved context:")

            # Count sources
            source_count = sum(1 for line in context.split("\n") if line.strip().startswith("## Relevant Sources"))

            if source_count > 0:
                lines.append(f"- I found {source_count} relevant source(s) in the knowledge base")

            # Extract memory info
            memory_lines = [l for l in context.split("\n") if "Conversation History" in l]
            if memory_lines:
                lines.append("- I have access to our conversation history")

        lines.append("\n[This is a placeholder response. To get AI-generated answers, configure LLM_API_KEY]")

        return "\n".join(lines)
