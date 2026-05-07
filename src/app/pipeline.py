from __future__ import annotations

import logging

from redis.asyncio import Redis

from app.backend_api_client import BackendApiClient
from app.config import AppSettings
from app.exceptions import (
    BackendApiError,
    DeviceIdentityNotFoundError,
    FrameParsingError,
    PipelineStageError,
    SessionIdentityNotFoundError,
    TenantIdentificationError,
)
from app.metrics import (
    PIPELINE_MESSAGES_DROPPED_TOTAL,
    PIPELINE_MESSAGES_PROCESSED_TOTAL,
    PIPELINE_PROCESSING_SECONDS,
)
from app.models import CardioTraceContext
from app.pipeline_steps import (
    BackendIdentificationStep,
    DeviceDiscoveryStep,
    SaveRecordStep,
    TenantIdentificationStep,
)

logger = logging.getLogger(__name__)
_DROP_REASON_MAP: dict[type[Exception], str] = {
    DeviceIdentityNotFoundError: "device_not_found",
    SessionIdentityNotFoundError: "session_not_found",
    TenantIdentificationError: "tenant_parse",
    FrameParsingError: "frame_parse",
    PipelineStageError: "pipeline_stage",
    BackendApiError: "backend_error",
}
_WARNING_REASONS = {"device_not_found", "session_not_found"}


class MessagePipeline:
    def __init__(
        self,
        settings: AppSettings,
        redis_client: Redis,
        backend_api_client: BackendApiClient,
    ) -> None:
        self.settings = settings
        self.redis_client = redis_client
        self.backend_api_client = backend_api_client
        self.steps = [
            TenantIdentificationStep(self.settings),
            DeviceDiscoveryStep(),
            BackendIdentificationStep(self.redis_client, self.backend_api_client),
            SaveRecordStep(self.backend_api_client),
        ]

    async def on_message(self, topic: str, payload: bytes) -> None:
        with PIPELINE_PROCESSING_SECONDS.time():
            try:
                context = CardioTraceContext(raw=payload, topic=topic)
                for step in self.steps:
                    await step.pre(context)
                    try:
                        await step.run(context)
                    except Exception as exc:
                        await step.on_error(context, exc)
                        raise
                PIPELINE_MESSAGES_PROCESSED_TOTAL.inc()
            except Exception as exc:
                self._handle_pipeline_failure(topic, exc)

    def _handle_pipeline_failure(self, topic: str, exc: Exception) -> None:
        reason = next(
            (
                mapped
                for kind, mapped in _DROP_REASON_MAP.items()
                if isinstance(exc, kind)
            ),
            "unexpected",
        )
        PIPELINE_MESSAGES_DROPPED_TOTAL.labels(reason=reason).inc()

        if reason in _WARNING_REASONS:
            logger.warning("Frame dropped on topic %s: %s", topic, exc)
        else:
            logger.exception("Error processing message on topic %s: %s", topic, exc)
