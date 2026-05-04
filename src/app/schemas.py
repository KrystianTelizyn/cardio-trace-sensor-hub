from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, bool] = Field(default_factory=dict)
