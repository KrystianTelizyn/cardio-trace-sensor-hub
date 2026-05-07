from __future__ import annotations

from app.backend_api_client import BackendApiClient
from app.exceptions import BackendApiError, PipelineStageError
from app.metrics import BACKEND_STORE_REQUESTS_TOTAL, status_class_from_code
from app.models import CardioTraceContext, CardioTraceRecord
from app.pipeline_steps.base import PipelineStep, SAVE_RECORD_STEP


class SaveRecordStep(PipelineStep):
    name = SAVE_RECORD_STEP

    def __init__(self, backend_api_client: BackendApiClient) -> None:
        self._backend_api_client = backend_api_client

    async def pre(self, context: CardioTraceContext) -> None:
        if (
            context.tenant_id is None
            or context.session_id is None
            or context.timestamp is None
        ):
            raise PipelineStageError(
                stage=SAVE_RECORD_STEP,
                message="Missing one or more required context fields",
            )

    async def run(self, context: CardioTraceContext) -> None:
        record = CardioTraceRecord(
            measurement_session_id=context.session_id,
            timestamp=context.timestamp,
            heart_rate=context.heart_rate,
            sdnn=context.sdnn,
            rmssd=context.rmssd,
        )
        await self._backend_api_client.store(context.tenant_id, record)

        BACKEND_STORE_REQUESTS_TOTAL.labels(result="success", status_class="2xx").inc()

    async def on_error(self, context: CardioTraceContext, exc: Exception) -> None:
        if isinstance(exc, BackendApiError):
            BACKEND_STORE_REQUESTS_TOTAL.labels(
                result="error",
                status_class=status_class_from_code(exc.status_code),
            ).inc()
