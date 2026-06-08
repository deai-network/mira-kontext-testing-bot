"""HTTP client for the Catena AI API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import httpx
from httpx import HTTPStatusError

from .config import get_settings
from .errors import AuthenticationError, CatenaAPIError, ConfigurationError


@dataclass(frozen=True)
class CatenaUser:
    """Authenticated Catena user profile from GET /auth/me."""

    id: int
    email: str
    is_admin: bool
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None

    @property
    def display_name(self) -> str:
        parts = [part for part in (self.first_name, self.last_name) if part]
        if parts:
            return " ".join(parts)
        return self.email


@dataclass(frozen=True)
class CatenaChatResult:
    """Normalized response from POST /chat."""

    text: str
    thread_id: str | None
    flow_type: str | None
    raw: dict[str, Any]


class CatenaClient:
    """Async HTTP client for Catena AI chat and auth endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.catena_api_url).rstrip("/")
        self.timeout = timeout or settings.request_timeout
        self._token = token or settings.catena_token
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> CatenaClient:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def connect(self) -> None:
        """Initialize HTTP client and ensure a bearer token is available."""
        if not self._token:
            await self.login_from_settings()
        if not self._token:
            raise ConfigurationError(
                "Catena credentials required. Set CATENA_TOKEN or "
                "CATENA_IDENTIFIER + CATENA_PASSWORD."
            )

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self.timeout,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise CatenaAPIError("Catena client not connected. Use async with or connect().")
        return self._client

    async def login_from_settings(self) -> str:
        """Obtain a JWT via POST /auth/login using env credentials."""
        settings = get_settings()
        if not settings.catena_identifier or not settings.catena_password:
            raise ConfigurationError(
                "CATENA_IDENTIFIER and CATENA_PASSWORD are required when CATENA_TOKEN is unset."
            )
        token = await self.login(settings.catena_identifier, settings.catena_password)
        self._token = token
        return token

    async def login(self, identifier: str, password: str) -> str:
        """Authenticate and return the access token."""
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        ) as client:
            try:
                response = await client.post(
                    "/auth/login",
                    json={"identifier": identifier, "password": password},
                )
                response.raise_for_status()
            except HTTPStatusError as exc:
                self._handle_error(exc)

            token = self._extract_token(response)
            if not token:
                raise CatenaAPIError(
                    "Login succeeded but no access token was returned. "
                    "Create an API token via POST /auth/tokens and set CATENA_TOKEN."
                )
            return token

    async def health_check(self) -> dict[str, Any]:
        """Call GET /health."""
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.get("/health")
            response.raise_for_status()
            body = response.json()
            return body if isinstance(body, dict) else {"status": "ok"}

    async def me(self) -> CatenaUser:
        """Return the authenticated user profile."""
        client = self._ensure_client()
        try:
            response = await client.get("/auth/me")
            response.raise_for_status()
        except HTTPStatusError as exc:
            self._handle_error(exc)

        data = cast(dict[str, Any], response.json())
        return CatenaUser(
            id=int(data["id"]),
            email=str(data["email"]),
            is_admin=bool(data.get("is_admin", False)),
            first_name=cast(str | None, data.get("first_name")),
            last_name=cast(str | None, data.get("last_name")),
            company_name=cast(str | None, data.get("company_name")),
        )

    async def chat(
        self,
        query: str,
        *,
        thread_id: str | None = None,
        flow_id: str | None = None,
        llm_model: str | None = None,
        router_model: str | None = None,
        search_mode: str | None = None,
    ) -> CatenaChatResult:
        """Run POST /chat and return the final envelope."""
        client = self._ensure_client()
        settings = get_settings()

        payload: dict[str, Any] = {"query": query}
        if thread_id:
            payload["thread_id"] = thread_id
        if flow_id or settings.catena_default_flow_id:
            payload["flow_id"] = flow_id or settings.catena_default_flow_id
        if llm_model:
            payload["llm_model"] = llm_model
        if router_model:
            payload["router_model"] = router_model
        if search_mode:
            payload["search_mode"] = search_mode

        try:
            response = await client.post("/chat", json=payload)
            response.raise_for_status()
        except HTTPStatusError as exc:
            self._handle_error(exc)

        data = cast(dict[str, Any], response.json())
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            raise CatenaAPIError("Catena /chat returned an empty response.")

        return CatenaChatResult(
            text=text,
            thread_id=cast(str | None, data.get("thread_id")),
            flow_type=cast(str | None, data.get("flow_type")),
            raw=data,
        )

    def _extract_token(self, response: httpx.Response) -> str | None:
        """Read bearer token from JSON body or access_token cookie."""
        try:
            body = response.json()
            if isinstance(body, dict):
                typed = cast(dict[str, Any], body)
                for key in ("access_token", "token", "accessToken"):
                    value = typed.get(key)
                    if isinstance(value, str) and value:
                        return value
        except Exception:
            pass

        for cookie_name in ("access_token", "accessToken"):
            token = response.cookies.get(cookie_name)
            if token:
                return token
        return None

    def _handle_error(self, exc: HTTPStatusError) -> None:
        status = exc.response.status_code
        detail = _error_detail(exc.response)
        message = f"Catena API error {status}"
        if detail is not None:
            message = f"{message}: {detail}"
        if status in (401, 403):
            raise AuthenticationError(message) from exc
        raise CatenaAPIError(message) from exc


def _error_detail(response: httpx.Response) -> object | None:
    try:
        body = response.json()
        if isinstance(body, dict):
            return cast(dict[str, Any], body).get("detail")
    except Exception:
        return response.text[:500] if response.text else None
    return None
