from dataclasses import dataclass
from pydantic import BaseModel
from datetime import datetime


class CardioTraceRecord(BaseModel):
    tenant_id: str
    session_id: str
    device_id: str
    timestamp: datetime
    hr: float
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
    hrv: float | None = None
