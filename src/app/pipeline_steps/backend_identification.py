from __future__ import annotations

import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.backend_api_client import BackendApiClient
from app.exceptions import (
    BackendApiError,
    DeviceIdentityNotFoundError,
    PipelineStageError,
    SessionIdentityNotFoundError,
)
from app.metrics import (
    BACKEND_ENRICH_REQUESTS_TOTAL,
    REDIS_CACHE_HITS_TOTAL,
    REDIS_CACHE_LOOKUPS_TOTAL,
    PIPELINE_MESSAGES_DROPPED_TOTAL,
    status_class_from_code,
)
from app.models import CardioTraceContext
from app.pipeline_steps.base import PipelineStep, handles_pipeline_error

logger = logging.getLogger(__name__)
DEVICE_NOT_FOUND_SENTINEL = "NONE"
SESSION_NOT_FOUND_SENTINEL = "NONE"


class BackendIdentificationStep(PipelineStep):
    def __init__(
        self,
        redis_client: Redis,
        backend_api_client: BackendApiClient,
    ) -> None:
        self._redis_client = redis_client
        self._backend_api_client = backend_api_client
        self.used_backend_enrich = False

    async def pre(self, context: CardioTraceContext) -> None:
        self.used_backend_enrich = False
        if (
            context.tenant_id is None
            or context.serial_number is None
            or context.brand is None
        ):
            raise PipelineStageError(
                stage=self.__class__.__name__,
                message="Missing tenant_id, serial number, or brand for enrichment",
            )

    async def run(self, context: CardioTraceContext) -> None:
        try:
            device_uid, session_uid = await self._resolve_from_cache(context)
        except RedisError:
            logger.warning("Redis unavailable, falling back to backend enrichment")
            device_uid, session_uid = None, None

        if device_uid == DEVICE_NOT_FOUND_SENTINEL:
            raise DeviceIdentityNotFoundError(
                f"Device not registered: {context.brand}/{context.serial_number}"
            )
        if session_uid == SESSION_NOT_FOUND_SENTINEL:
            raise SessionIdentityNotFoundError(
                f"Session not found for device: {context.brand}/{context.serial_number}"
            )

        if device_uid is not None and session_uid is not None:
            context.device_id = device_uid
            context.session_id = session_uid
            return

        self.used_backend_enrich = True
        enriched = await self._backend_api_client.enrich(
            serial_number=context.serial_number,
            brand=context.brand,
            tenant_id=context.tenant_id,
        )
        if enriched.device_uid is None:
            raise DeviceIdentityNotFoundError(
                f"Device not registered: {context.brand}/{context.serial_number}"
            )
        if enriched.session_uid is None:
            raise SessionIdentityNotFoundError(
                f"Session not found for device: {context.brand}/{context.serial_number}"
            )
        context.device_id = enriched.device_uid
        context.session_id = enriched.session_uid

        if self.used_backend_enrich:
            BACKEND_ENRICH_REQUESTS_TOTAL.labels(
                result="success", status_class="2xx"
            ).inc()

    @handles_pipeline_error(BackendApiError)
    async def on_backend_api_error(
        self, context: CardioTraceContext, exc: BackendApiError
    ) -> None:
        logger.warning("Backend API error: %s", exc)
        BACKEND_ENRICH_REQUESTS_TOTAL.labels(
            result="error",
            status_class=status_class_from_code(exc.status_code),
        ).inc()
        PIPELINE_MESSAGES_DROPPED_TOTAL.labels(reason="backend_api_error").inc()

    @handles_pipeline_error(DeviceIdentityNotFoundError)
    async def on_device_identity_not_found_error(
        self, context: CardioTraceContext, exc: DeviceIdentityNotFoundError
    ) -> None:
        logger.warning("Device identity not found: %s", exc)
        PIPELINE_MESSAGES_DROPPED_TOTAL.labels(
            reason="device_identity_not_found_error"
        ).inc()

    @handles_pipeline_error(SessionIdentityNotFoundError)
    async def on_session_identity_not_found_error(
        self, context: CardioTraceContext, exc: SessionIdentityNotFoundError
    ) -> None:
        logger.warning("Session identity not found: %s", exc)
        PIPELINE_MESSAGES_DROPPED_TOTAL.labels(
            reason="session_identity_not_found_error"
        ).inc()

    @handles_pipeline_error(PipelineStageError)
    async def on_pipeline_stage_error(
        self, context: CardioTraceContext, exc: PipelineStageError
    ) -> None:
        logger.warning("Pipeline stage error: %s", exc)
        PIPELINE_MESSAGES_DROPPED_TOTAL.labels(reason="pipeline_stage_error").inc()

    async def _resolve_from_cache(
        self, context: CardioTraceContext
    ) -> tuple[str | None, str | None]:
        device_map_key = (
            f"device_map:{context.tenant_id}:{context.brand}:{context.serial_number}"
        )
        REDIS_CACHE_LOOKUPS_TOTAL.inc()
        device_uid = await self._redis_client.get(device_map_key)
        if device_uid is not None and device_uid != DEVICE_NOT_FOUND_SENTINEL:
            REDIS_CACHE_HITS_TOTAL.inc()
        if device_uid is None or device_uid == DEVICE_NOT_FOUND_SENTINEL:
            return device_uid, None

        device_session_key = f"device_session:{context.tenant_id}:{device_uid}"
        REDIS_CACHE_LOOKUPS_TOTAL.inc()
        session_uid = await self._redis_client.get(device_session_key)
        if session_uid is not None and session_uid != SESSION_NOT_FOUND_SENTINEL:
            REDIS_CACHE_HITS_TOTAL.inc()
        return device_uid, session_uid
