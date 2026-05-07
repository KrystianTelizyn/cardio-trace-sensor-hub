from __future__ import annotations

import re

from app.config import AppSettings
from app.exceptions import TenantIdentificationError
from app.models import CardioTraceContext
from app.pipeline_steps.base import PipelineStep, TENANT_IDENTIFICATION_STEP


class TenantIdentificationStep(PipelineStep):
    name = TENANT_IDENTIFICATION_STEP

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    async def run(self, context: CardioTraceContext) -> None:
        match = re.match(self._settings.tenant_extraction_regex, context.topic)
        if match:
            context.tenant_id = match.group(1)
            return
        raise TenantIdentificationError(
            "Could not extract tenant_id from topic "
            f"'{context.topic}' using pattern "
            f"'{self._settings.tenant_extraction_regex}'"
        )
