from __future__ import annotations

import re

from app.config import AppSettings
from app.exceptions import TenantIdentificationError
from app.models import CardioTraceContext
from app.pipeline_steps.base import PipelineStep
from app.pipeline_steps.base import handles_pipeline_error
from logging import getLogger

logger = getLogger(__name__)


class TenantIdentificationStep(PipelineStep):
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

    @handles_pipeline_error(
        TenantIdentificationError, reason="tenant_identification_error"
    )
    async def on_tenant_identification_error(
        self, context: CardioTraceContext, exc: TenantIdentificationError
    ) -> None:
        logger.warning("Error identifying tenant: %s", exc)
