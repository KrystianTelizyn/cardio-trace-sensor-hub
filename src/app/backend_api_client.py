from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from app.exceptions import (
    BackendApiError,
    BackendApiValidationError,
    DeviceIdentityNotFoundError,
)


@dataclass(frozen=True)
class EnrichedDeviceContext:
    device_uid: str
    session_uid: str | None


class BackendApiClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=5.0)

    async def shutdown(self) -> None:
        await self._client.aclose()

    async def send_message(self, message: str) -> None: ...

    async def enrich(self, serial_number: str, brand: str) -> EnrichedDeviceContext:
        payload = {"serial_number": serial_number, "brand": brand}
        response = await self._client.post("/ingestion/enrich", json=payload)
        if response.status_code == 400:
            raise BackendApiValidationError("Invalid enrich payload")
        if response.status_code == 404:
            raise DeviceIdentityNotFoundError("Device identity not found")
        if response.status_code >= 500:
            raise BackendApiError(f"Backend API server error: {response.status_code}")
        if response.status_code != 200:
            raise BackendApiError(
                f"Unexpected enrich response status: {response.status_code}"
            )

        data = self._parse_json(response)
        device_uid = data.get("device_uid")
        session_uid = data.get("session_uid")
        if not isinstance(device_uid, str):
            raise BackendApiError("Invalid enrich response: 'device_uid' is missing")
        if session_uid is not None and not isinstance(session_uid, str):
            raise BackendApiError(
                "Invalid enrich response: 'session_uid' must be string or null"
            )

        return EnrichedDeviceContext(device_uid=device_uid, session_uid=session_uid)

    async def store(self, *args: Any, **kwargs: Any) -> None: ...

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
            raise BackendApiError("Backend API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise BackendApiError("Backend API returned unexpected response shape")
        return payload
