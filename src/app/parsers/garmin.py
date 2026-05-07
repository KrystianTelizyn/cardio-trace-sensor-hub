from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.parsers.types import ExtraAllowedModel, ParsedFrame


class GarminHeader(ExtraAllowedModel):
    message_type: Literal["HEART_RATE_HRV_EPOCH"]
    device_id: str
    collected_at: datetime


class GarminData(ExtraAllowedModel):
    heart_rate_bpm: float | None
    sdnn_ms: float | None
    rmssd_ms: float | None


class GarminPayload(ExtraAllowedModel):
    header: GarminHeader
    data: GarminData

    def to_frame(self) -> ParsedFrame:
        return ParsedFrame(
            brand="garmin",
            serial_number=self.header.device_id,
            timestamp=self.header.collected_at,
            heart_rate=self.data.heart_rate_bpm,
            sdnn=self.data.sdnn_ms,
            rmssd=self.data.rmssd_ms,
        )
