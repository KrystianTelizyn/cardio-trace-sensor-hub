from __future__ import annotations

from datetime import datetime

from pydantic import model_validator

from app.parsers.types import ExtraAllowedModel, ParsedFrame


class AppleDeviceInfo(ExtraAllowedModel):
    deviceId: str


class AppleHeartRate(ExtraAllowedModel):
    value_bpm: float | None = None


class AppleHrvEntry(ExtraAllowedModel):
    type: str
    value_ms: float | None = None


class AppleMeasurement(ExtraAllowedModel):
    timestamp_iso: datetime
    heart_rate: AppleHeartRate
    hrv: list[AppleHrvEntry]

    @model_validator(mode="after")
    def check_required_hrv_entries(self) -> AppleMeasurement:
        hrv_types = {entry.type for entry in self.hrv}
        if "sdnn" not in hrv_types:
            raise ValueError("missing sdnn entry in measurement.hrv")
        if "rmssd" not in hrv_types:
            raise ValueError("missing rmssd entry in measurement.hrv")
        return self


class ApplePayload(ExtraAllowedModel):
    deviceInfo: AppleDeviceInfo
    measurement: AppleMeasurement

    def to_frame(self) -> ParsedFrame:
        hrv_by_type = {entry.type: entry.value_ms for entry in self.measurement.hrv}
        return ParsedFrame(
            brand="apple",
            serial_number=self.deviceInfo.deviceId,
            timestamp=self.measurement.timestamp_iso,
            heart_rate=self.measurement.heart_rate.value_bpm,
            sdnn=hrv_by_type["sdnn"],
            rmssd=hrv_by_type["rmssd"],
        )
