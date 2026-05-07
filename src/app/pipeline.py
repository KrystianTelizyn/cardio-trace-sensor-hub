from __future__ import annotations


from redis.asyncio import Redis

from app.backend_api_client import BackendApiClient
from app.config import AppSettings

from app.metrics import (
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
            context = CardioTraceContext(raw=payload, topic=topic)
            for step in self.steps:
                try:
                    await step.pre(context)
                    await step.run(context)
                except Exception as exc:
                    await step.on_error(context, exc)
                    break
            else:
                PIPELINE_MESSAGES_PROCESSED_TOTAL.inc()
