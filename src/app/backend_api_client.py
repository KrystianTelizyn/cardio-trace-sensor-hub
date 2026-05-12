from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx
import logging
from app.models import CardioTraceRecord

from app.exceptions import (
    BackendApiError,
    BackendApiValidationError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnrichedDeviceContext:
    device_uid: str | None
    session_uid: str | None


class BackendApiClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=5.0)

    async def shutdown(self) -> None:
        await self._client.aclose()

    async def send_message(
        self,
        path: str,
        *,
        tenant_id: str,
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        headers = {"X-Tenant-Id": tenant_id}
        try:
            response = await self._client.post(path, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise BackendApiError(f"Backend API request failed: {exc}") from exc
        if response.status_code >= 500:
            raise BackendApiError(
                f"Backend API server error: {response.status_code}",
                status_code=response.status_code,
            )
        return response

    async def enrich(
        self, serial_number: str, brand: str, tenant_id: str
    ) -> EnrichedDeviceContext:
        response = await self.send_message(
            "/ingestion/enrich",
            tenant_id=tenant_id,
            payload={"serial_number": serial_number, "brand": brand},
        )
        if response.status_code == 400:
            raise BackendApiValidationError(
                "Invalid enrich payload",
                status_code=response.status_code,
            )
        if response.status_code != 200:
            raise BackendApiError(
                f"Unexpected enrich response status: {response.status_code}",
                status_code=response.status_code,
            )

        data = self._parse_json(response)
        device_uid = data.get("device_uid")
        session_uid = data.get("session_uid")
        if device_uid is not None and not isinstance(device_uid, str):
            raise BackendApiError(
                "Invalid enrich response: 'device_uid' must be string or null",
                status_code=response.status_code,
            )
        if session_uid is not None and not isinstance(session_uid, str):
            raise BackendApiError(
                "Invalid enrich response: 'session_uid' must be string or null",
                status_code=response.status_code,
            )
        return EnrichedDeviceContext(device_uid=device_uid, session_uid=session_uid)

    async def store(self, tenant_id: str, record: CardioTraceRecord) -> None:
        response = await self.send_message(
            "/measurements",
            tenant_id=tenant_id,
            payload=record.model_dump(mode="json"),
        )

        if response.status_code == 201:
            self._parse_json(response)
            return
        if response.status_code == 202:
            logger.info(
                "Measurement dropped by backend: measurement_session_id=%s",
                record.measurement_session_id,
            )
            return
        if response.status_code == 400:
            raise BackendApiValidationError(
                "Invalid measurements payload",
                status_code=response.status_code,
            )
        if response.status_code == 404:
            raise BackendApiError(
                "Measurement session not found",
                status_code=response.status_code,
            )
        raise BackendApiError(
            f"Unexpected measurements response status: {response.status_code}",
            status_code=response.status_code,
        )

    async def is_ready(self) -> bool:
        try:
            response = await self._client.get("/health")
        except httpx.HTTPError:
            return False
        return response.status_code < 500

    def _parse_json(self, response: httpx.Response) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise BackendApiError(
                "Backend API returned invalid JSON",
                status_code=response.status_code,
            ) from exc
        if not isinstance(payload, dict):
            raise BackendApiError(
                "Backend API returned unexpected response shape",
                status_code=response.status_code,
            )
        return payload
