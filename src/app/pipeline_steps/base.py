from __future__ import annotations

import abc

from app.models import CardioTraceContext

TENANT_IDENTIFICATION_STEP = "tenant_identification"
DEVICE_DISCOVERY_STEP = "device_discovery"
BACKEND_IDENTIFICATION_STEP = "backend_identification"
SAVE_RECORD_STEP = "save_record"


class PipelineStep(abc.ABC):
    async def pre(self, context: CardioTraceContext) -> None:
        pass

    @abc.abstractmethod
    async def run(self, context: CardioTraceContext) -> None:
        pass

    async def on_error(self, context: CardioTraceContext, exc: Exception) -> None:
        pass
