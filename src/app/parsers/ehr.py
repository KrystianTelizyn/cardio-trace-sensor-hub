from __future__ import annotations

from datetime import datetime

from pydantic import model_validator

from app.parsers.types import ExtraAllowedModel, ParsedFrame


class EhrMeta(ExtraAllowedModel):
    device_id: str
    received_at: datetime
    protocol_version: str


class EhrObservation(ExtraAllowedModel):
    code: str
    value: float | None = None


class EhrPayload(ExtraAllowedModel):
    meta: EhrMeta
    observations: list[EhrObservation]

    @model_validator(mode="after")
    def check_required_observations(self) -> EhrPayload:
        codes = {observation.code for observation in self.observations}
        if "8867-4" not in codes:
            raise ValueError("missing heart-rate observation 8867-4")
        if "X-HRV-SDNN" not in codes:
            raise ValueError("missing SDNN observation X-HRV-SDNN")
        if "X-HRV-RMSSD" not in codes:
            raise ValueError("missing RMSSD observation X-HRV-RMSSD")
        return self

    def to_frame(self) -> ParsedFrame:
        by_code = {
            observation.code: observation.value for observation in self.observations
        }
        return ParsedFrame(
            brand="ehr",
            serial_number=self.meta.device_id,
            timestamp=self.meta.received_at,
            heart_rate=by_code["8867-4"],
            sdnn=by_code["X-HRV-SDNN"],
            rmssd=by_code["X-HRV-RMSSD"],
        )
