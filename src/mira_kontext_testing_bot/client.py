"""HTTP client for the Mira Kontext API."""

from __future__ import annotations

from contextlib import suppress
from typing import Any, cast
from uuid import UUID

import httpx
from httpx import HTTPStatusError

from .config import get_settings
from .errors import (
    AuthenticationError,
    ConfigurationError,
    KontextAPIError,
    NotFoundError,
    PermissionError,
    SourceIsolationError,
    ValidationError,
)
from .models import (
    ContextItem,
    IngestResult,
    MemoryMessage,
    Principal,
    Project,
    QueryResult,
    Session,
)


class KontextClient:
    """Async HTTP client for the Mira Kontext API."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.kontext_api_url).rstrip("/")
        self.token = token or settings.kontext_token
        self.timeout = timeout or settings.request_timeout

        if not self.token:
            raise ConfigurationError("Kontext API token is required. Set KONTEXT_TOKEN env var.")

        self._client: httpx.AsyncClient | None = None
        self.source_collections_supported: bool | None = None

    async def __aenter__(self) -> KontextClient:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def connect(self) -> None:
        """Initialize the HTTP client."""
        import json
        import logging

        # Set up a dedicated logger for the API client
        logger = logging.getLogger("mira_testing_bot.api")
        logger.setLevel(logging.DEBUG)

        # Avoid duplicate handlers if connect() is called multiple times
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

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self.timeout,
            event_hooks={
                'request': [log_request],
                'response': [log_response]
            }
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure client is connected."""
        if self._client is None:
            raise KontextAPIError("Client not connected. Use 'async with' or call connect().")
        return self._client

    def _handle_error(self, exc: HTTPStatusError) -> None:
        """Convert HTTP errors to typed exceptions."""
        status = exc.response.status_code
        body: dict[str, Any] = {}
        with suppress(Exception):
            body = exc.response.json()

        detail = body.get("detail", str(exc))

        if status == 401:
            raise AuthenticationError(f"Authentication failed: {detail}")
        if status == 403:
            raise PermissionError(f"Permission denied: {detail}")
        if status == 404:
            raise NotFoundError(f"Resource not found: {detail}")
        if status == 422:
            if _is_stale_ingest_contract(detail):
                self.source_collections_supported = False
                raise SourceIsolationError(_SOURCE_ISOLATION_UNSUPPORTED_MESSAGE)
            if _is_stale_source_collection_query_contract(detail):
                self.source_collections_supported = False
                raise SourceIsolationError(_SOURCE_ISOLATION_UNSUPPORTED_MESSAGE)
            raise ValidationError(f"Validation error: {detail}")

        raise KontextAPIError(f"API error {status}: {detail}")

    async def health_check(self) -> dict[str, str]:
        """Check API health status."""
        client = self._ensure_client()
        try:
            response = await client.get("/health")
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            self._handle_error(exc)
            raise

    async def ready_check(self) -> dict[str, str]:
        """Check API readiness (includes DB connectivity)."""
        client = self._ensure_client()
        try:
            response = await client.get("/ready")
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            self._handle_error(exc)
            raise

    async def query(
        self,
        query: str,
        principal: Principal | None = None,
        limit: int = 8,
        content_kinds: list[str] | None = None,
        metadata_match: dict[str, Any] | None = None,
        source_scope: list[dict[str, Any]] | None = None,
        source_collections: list[str] | None = None,
        memory: dict[str, Any] | None = None,
    ) -> QueryResult:
        """Execute a context query against the API."""
        client = self._ensure_client()
        settings = get_settings()

        payload: dict[str, Any] = {
            "query": query,
            "principal": {
                "external_id": (principal.external_id if principal else settings.bot_principal_id),
                "display_name": (
                    principal.display_name if principal else settings.bot_display_name
                ),
                "roles": (principal.roles if principal else settings.bot_roles),
            },
            "limit": max(1, min(limit, 20)),
        }

        if content_kinds:
            payload["content_kinds"] = content_kinds
        if metadata_match:
            payload["metadata_match"] = metadata_match
        if source_scope:
            payload["source_scope"] = source_scope
        if source_collections is not None:
            payload["source_collections"] = source_collections
        if memory:
            payload["memory"] = memory

        try:
            response = await client.post("/v1/query", json=payload)
            response.raise_for_status()
            data = response.json()
            if source_collections is not None:
                self.source_collections_supported = True

            return QueryResult(
                audit_id=UUID(data["audit_id"]),
                items=[ContextItem(**item) for item in data.get("items", [])],
                permission_counters=data.get("permission_counters", {}),
            )
        except HTTPStatusError as exc:
            detail = _error_detail(exc.response)
            if _is_stale_source_collection_query_contract(detail):
                self.source_collections_supported = False
                raise SourceIsolationError(_SOURCE_ISOLATION_UNSUPPORTED_MESSAGE) from exc
            self._handle_error(exc)
            raise

    async def get_document(self, short_id: str, principal: Principal | None = None) -> dict[str, Any] | None:
        """Retrieve a specific document by short ID."""
        client = self._ensure_client()
        settings = get_settings()
        params = {
            "principal_external_id": (
                principal.external_id if principal is not None else settings.bot_principal_id
            )
        }
        try:
            response = await client.get(f"/v1/documents/{short_id}", params=params)
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            self._handle_error(exc)
            raise

    async def ingest_record(
        self,
        content: str,
        source_system: str,
        source_object_type: str,
        source_object_id: str,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
        entities: list[dict[str, Any]] | None = None,
        source_version: str | None = None,
        source_url: str | None = None,
        principal: Principal | None = None,
        collection_external_id: str | None = None,
    ) -> IngestResult:
        """Ingest a source record into the API."""
        client = self._ensure_client()
        settings = get_settings()

        payload: dict[str, Any] = {
            "source_system": source_system,
            "source_object_type": source_object_type,
            "source_object_id": source_object_id,
            "content": content,
            "principal": {
                "external_id": (principal.external_id if principal else settings.bot_principal_id),
                "display_name": (principal.display_name if principal else settings.bot_display_name),
            },
        }
        if collection_external_id:
            payload["collection_external_id"] = collection_external_id
        if title:
            payload["title"] = title
        if metadata:
            payload["metadata"] = metadata
        if entities:
            payload["entities"] = entities
        if source_version:
            payload["source_version"] = source_version
        if source_url:
            payload["source_url"] = source_url

        try:
            response = await client.post("/v1/ingest/records", json=payload)
            response.raise_for_status()
            data = response.json()
            self.source_collections_supported = True
            return _parse_ingest_result(data)
        except HTTPStatusError as exc:
            detail = _error_detail(exc.response)
            if _is_stale_ingest_contract(detail):
                self.source_collections_supported = False
                raise SourceIsolationError(_SOURCE_ISOLATION_UNSUPPORTED_MESSAGE) from exc
            self._handle_error(exc)
            raise

    async def write_memory_message(
        self,
        message: str,
        role: str,
        project: Project,
        session: Session,
        principal: Principal | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write a conversation message to memory."""
        client = self._ensure_client()
        settings = get_settings()

        payload: dict[str, Any] = {
            "project": {
                "external_id": project.external_id,
                "title": project.title,
                "metadata": project.metadata,
            },
            "session": {
                "external_id": session.external_id,
                "title": session.title,
                "metadata": session.metadata,
            },
            "principal": {
                "external_id": (
                    principal.external_id if principal else settings.bot_principal_id
                ),
                "display_name": (
                    principal.display_name if principal else settings.bot_display_name
                ),
            },
            "role": role,
            "content": message,
        }

        if metadata:
            payload["metadata"] = metadata

        try:
            response = await client.post("/v1/memory/messages", json=payload)
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            self._handle_error(exc)
            raise

    async def get_recent_memory(
        self,
        project_external_id: str | None = None,
        session_external_id: str | None = None,
        principal_external_id: str | None = None,
        limit: int = 20,
    ) -> list[MemoryMessage]:
        """Retrieve recent conversation memory."""
        client = self._ensure_client()

        params: dict[str, Any] = {"limit": limit}
        if project_external_id:
            params["project_external_id"] = project_external_id
        if session_external_id:
            params["session_external_id"] = session_external_id
        if principal_external_id:
            params["principal_external_id"] = principal_external_id

        try:
            response = await client.get("/v1/memory/recent", params=params)
            response.raise_for_status()
            data = response.json()

            return [MemoryMessage(**msg) for msg in data.get("messages", [])]
        except HTTPStatusError as exc:
            self._handle_error(exc)
            raise

    async def search_memory(
        self,
        query: str,
        project_external_id: str | None = None,
        session_external_id: str | None = None,
        principal_external_id: str | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """Search conversation memory semantically."""
        client = self._ensure_client()

        payload: dict[str, Any] = {
            "query": query,
            "limit": max(1, min(limit, 20)),
        }
        if project_external_id:
            payload["project_external_id"] = project_external_id
        if session_external_id:
            payload["session_external_id"] = session_external_id
        if principal_external_id:
            payload["principal_external_id"] = principal_external_id

        try:
            response = await client.post("/v1/memory/search", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])
        except HTTPStatusError as exc:
            self._handle_error(exc)
            raise

    async def list_sources(self, principal: Principal | None = None) -> list[dict[str, Any]]:
        """List all ingested sources."""
        client = self._ensure_client()
        settings = get_settings()
        params = {
            "principal_external_id": (
                principal.external_id if principal is not None else settings.bot_principal_id
            )
        }
        try:
            response = await client.get("/v1/sources", params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("sources", [])
        except HTTPStatusError as exc:
            self._handle_error(exc)
            raise

    async def create_token(
        self, name: str, scopes: list[str], expires_at: str | None = None
    ) -> dict[str, Any]:
        """Create a new API token."""
        client = self._ensure_client()

        payload: dict[str, Any] = {"name": name, "scopes": scopes}
        if expires_at:
            payload["expires_at"] = expires_at

        try:
            response = await client.post("/v1/tokens", json=payload)
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            self._handle_error(exc)
            raise

    async def list_tokens(self) -> list[dict[str, Any]]:
        """List all API tokens."""
        client = self._ensure_client()
        try:
            response = await client.get("/v1/tokens")
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            self._handle_error(exc)
            raise

    async def revoke_token(self, token_id: str) -> None:
        """Revoke an API token."""
        client = self._ensure_client()
        try:
            response = await client.delete(f"/v1/tokens/{token_id}")
            response.raise_for_status()
        except HTTPStatusError as exc:
            self._handle_error(exc)
            raise

    async def get_audit(self, audit_id: str) -> dict[str, Any] | None:
        """Retrieve an audit record by ID."""
        client = self._ensure_client()
        try:
            response = await client.get(f"/v1/audit/{audit_id}")
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            self._handle_error(exc)
            raise


_SOURCE_ISOLATION_UNSUPPORTED_MESSAGE = (
    "The API server does not support source collection isolation. "
    "Restart/redeploy mira-kontext-api after the source collection migration before using "
    "blank-user source workflows."
)


def _is_stale_ingest_contract(detail: object) -> bool:
    """Detect old API schemas that reject principal-aware source records."""
    return _has_extra_forbidden_field(detail, {"principal", "collection_external_id"})


def _is_stale_source_collection_query_contract(detail: object) -> bool:
    """Detect old API schemas that reject source collection scoped queries."""
    return _has_extra_forbidden_field(detail, {"source_collections"})


def _has_extra_forbidden_field(detail: object, rejected_fields: set[str]) -> bool:
    if not isinstance(detail, list):
        return False
    detail_items = cast(list[object], detail)
    for item in detail_items:
        if not isinstance(item, dict):
            continue
        typed_item = cast(dict[str, object], item)
        if typed_item.get("type") != "extra_forbidden":
            continue
        loc = typed_item.get("loc")
        loc_parts = cast(list[object], loc) if isinstance(loc, list) else []
        if any(isinstance(part, str) and part in rejected_fields for part in loc_parts):
            return True
    return False


def _error_detail(response: httpx.Response) -> object:
    with suppress(Exception):
        body = response.json()
        if isinstance(body, dict):
            typed_body = cast(dict[str, object], body)
            return typed_body.get("detail")
    return None


def _parse_ingest_result(data: dict[str, Any]) -> IngestResult:
    return IngestResult(
        content_item_id=UUID(data["content_item_id"]),
        source_record_id=UUID(data["source_record_id"]),
        checksum=data["checksum"],
        status=data["status"],
        entity_ids=[UUID(eid) for eid in data.get("entity_ids", [])],
    )
