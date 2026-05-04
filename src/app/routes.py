from fastapi import APIRouter, Depends

from app.deps import get_sensor_hub
from app.sensor_hub import SensorHub
from app.schemas import HealthResponse, ReadinessResponse

router = APIRouter()


@router.get("/healthz", response_model=HealthResponse, tags=["Health"])
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadinessResponse, tags=["Health"])
async def readyz(
    sensor_hub: SensorHub = Depends(get_sensor_hub),
) -> ReadinessResponse:
    checks = sensor_hub.is_ready()
    return ReadinessResponse(
        status="ok" if all(checks.values()) else "error", checks=checks
    )
