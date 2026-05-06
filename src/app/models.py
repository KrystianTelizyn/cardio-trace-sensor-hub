from dataclasses import dataclass
from pydantic import BaseModel
from datetime import datetime


class CardioTraceRecord(BaseModel):
    measurement_session_id: str
    timestamp: datetime
    heart_rate: float
    hrv: float


@dataclass
class CardioTraceContext:
    raw: bytes
    topic: str
    tenant_id: str | None = None
    session_id: str | None = None
    device_id: str | None = None
    serial_number: str | None = None
    brand: str | None = None
    timestamp: datetime | None = None
    hr: float | None = None
    sdnn: float | None = None
    rmssd: float | None = None
    hrv: float | None = None
