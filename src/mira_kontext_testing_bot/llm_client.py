"""LLM client for generating responses using retrieved context."""

from __future__ import annotations

from typing import cast

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

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
        import json
        import logging
        settings = get_settings()
        self.api_key = api_key or settings.llm_api_key or settings.nebius_api_key
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout = settings.llm_timeout

        logger = logging.getLogger("mira_testing_bot.api")
        logger.setLevel(logging.DEBUG)
        if not logger.handlers:
            fh = logging.FileHandler("bot_api_requests.log")
            fh.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            fh.setFormatter(formatter)
            logger.addHandler(fh)

        async def log_request(request: httpx.Request) -> None:
            await request.aread()
            body = request.content.decode('utf-8', errors='replace')
            try:
                if body:
                    body = json.dumps(json.loads(body), indent=2)
            except Exception:
                pass
            logger.debug(f"--> Request: {request.method} {request.url}\nHeaders: {dict(request.headers)}\nPayload:\n{body}")

        async def log_response(response: httpx.Response) -> None:
            await response.aread()
            body = response.text
            try:
                if body:
                    body = json.dumps(json.loads(body), indent=2)
            except Exception:
                pass
            logger.debug(f"<-- Response: {response.request.method} {response.request.url} - Status {response.status_code}\nPayload:\n{body}\n{'-'*80}")

        http_client = httpx.AsyncClient(
            timeout=self.timeout,
            event_hooks={'request': [log_request], 'response': [log_response]}
        )

        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            http_client=http_client
        )

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
        messages: list[ChatCompletionMessageParam] = []

        # System prompt
        default_system = _default_system_prompt()
        messages.append(
            cast(
                ChatCompletionMessageParam,
                {"role": "system", "content": system_prompt or default_system},
            )
        )

        # Add context as a system message
        if context:
            messages.append(
                cast(
                    ChatCompletionMessageParam,
                    {
                        "role": "system",
                        "content": f"Retrieved context:\n{context}",
                    },
                )
            )

        # Add conversation history (last 10 messages)
        for msg in conversation_history[-10:]:
            messages.append(
                cast(
                    ChatCompletionMessageParam,
                    {"role": msg["role"], "content": msg["content"]},
                )
            )

        # Add current user message
        messages.append(
            cast(
                ChatCompletionMessageParam,
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_message}],
                },
            )
        )

        # Make request
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
            )
            content = response.choices[0].message.content if response.choices else None
            if content is None:
                raise LLMError("LLM response did not contain content.")
            return str(content)
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
        default_system = _default_system_prompt()
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

        import json
        import logging
        logger = logging.getLogger("mira_testing_bot.api")
        logger.setLevel(logging.DEBUG)
        if not logger.handlers:
            fh = logging.FileHandler("bot_api_requests.log")
            fh.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            fh.setFormatter(formatter)
            logger.addHandler(fh)

        async def log_request(request: httpx.Request) -> None:
            await request.aread()
            body = request.content.decode('utf-8', errors='replace')
            try:
                if body:
                    body = json.dumps(json.loads(body), indent=2)
            except Exception:
                pass
            logger.debug(f"--> Request: {request.method} {request.url}\nHeaders: {dict(request.headers)}\nPayload:\n{body}")

        async def log_response(response: httpx.Response) -> None:
            await response.aread()
            body = response.text
            try:
                if body:
                    body = json.dumps(json.loads(body), indent=2)
            except Exception:
                pass
            logger.debug(f"<-- Response: {response.request.method} {response.request.url} - Status {response.status_code}\nPayload:\n{body}\n{'-'*80}")

        # Make request to Ollama Cloud API
        async with httpx.AsyncClient(timeout=self.timeout, event_hooks={'request': [log_request], 'response': [log_response]}) as client:
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
            memory_lines = [
                line for line in context.split("\n") if "Conversation History" in line
            ]
            if memory_lines:
                lines.append("- I have access to our conversation history")

        lines.append("\n[This is a placeholder response. To get AI-generated answers, configure LLM_API_KEY]")

        return "\n".join(lines)


def _default_system_prompt() -> str:
    return (
        "You are the conversational response layer for the Mira Kontext Testing Bot. "
        "The surrounding bot can store sources, query memory, list sources, retrieve "
        "documents, and fetch or search web pages through API actions before you are called. "
        "Do not claim that the bot has no ingest endpoints, APIs, storage access, or web "
        "fetch capability. If an API action has already been completed, summarize only the "
        "action result provided by the bot. If the user asks for web research and no web "
        "action has been run yet, explicitly suggest using /search-web <query> or /crawl <url>. "
        "Answer using the retrieved context and conversation history. Be concise and clear."
    )
