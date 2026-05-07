from fastapi import APIRouter, Depends, Response

from app.deps import get_sensor_hub
from app.metrics import render_metrics
from app.sensor_hub import SensorHub
from app.schemas import HealthResponse, ReadinessResponse

router = APIRouter()


@router.get("/livez", response_model=HealthResponse, tags=["Health"])
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadinessResponse, tags=["Health"])
async def readyz(
    sensor_hub: SensorHub = Depends(get_sensor_hub),
) -> ReadinessResponse:
    checks = await sensor_hub.is_ready()
    return ReadinessResponse(
        status="ok" if all(checks.values()) else "error", checks=checks
    )


@router.get("/metrics", tags=["Observability"])
async def metrics() -> Response:
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)
