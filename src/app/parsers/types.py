from __future__ import annotations

from datetime import datetime
from typing import NamedTuple, Protocol

from pydantic import BaseModel, ConfigDict


class ParsedFrame(NamedTuple):
    brand: str
    serial_number: str
    timestamp: datetime
    heart_rate: float | None
    sdnn: float | None
    rmssd: float | None


class FramePayload(Protocol):
    def to_frame(self) -> ParsedFrame: ...


class ExtraAllowedModel(BaseModel):
    model_config = ConfigDict(extra="allow")
