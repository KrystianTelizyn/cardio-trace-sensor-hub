from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ValidationError, model_validator

from app.exceptions import FrameParsingError
from app.models import CardioTraceContext


class FrameParser(Protocol):
    def parse(self, context: CardioTraceContext) -> CardioTraceContext: ...
    def parsing_applicable(self, context: CardioTraceContext) -> bool: ...


class ParsersChain:
    def __init__(self):
        self.parsers: list[FrameParser] = []
        self.add_parser(AppleParser())
        self.add_parser(GarminParser())
        self.add_parser(EhrParser())

    def add_parser(self, parser: FrameParser) -> None:
        self.parsers.append(parser)

    def parse(self, context: CardioTraceContext) -> CardioTraceContext:
        parsers_votes = [parser.parsing_applicable(context) for parser in self.parsers]
        votes_sum = sum(parsers_votes)
        if votes_sum == 0:
            raise FrameParsingError("No parser found for the given context")
        if votes_sum > 1:
            raise FrameParsingError("Multiple parsers found for the given context")
        return self.parsers[parsers_votes.index(True)].parse(context)


# ---------------------------------------------------------------------------
# Base class – owns validation + protocol boilerplate
# ---------------------------------------------------------------------------


class BaseFrameParser:
    brand: str = ""
    payload_model: type[BaseModel]

    def parsing_applicable(self, context: CardioTraceContext) -> bool:
        try:
            self.payload_model.model_validate_json(context.raw)
            return True
        except ValidationError:
            return False

    def parse(self, context: CardioTraceContext) -> CardioTraceContext:
        try:
            payload = self.payload_model.model_validate_json(context.raw)
        except ValidationError as exc:
            raise FrameParsingError(str(exc)) from exc
        self._apply(payload, context)
        return context

    def _apply(self, payload: BaseModel, context: CardioTraceContext) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Payload models – one flat model per vendor
# ---------------------------------------------------------------------------


class ApplePayload(BaseModel):
    deviceInfo: dict
    measurement: dict

    @model_validator(mode="after")
    def check_structure(self) -> ApplePayload:
        if "deviceId" not in self.deviceInfo:
            raise ValueError("missing deviceInfo.deviceId")
        m = self.measurement
        if "timestamp_iso" not in m or "heart_rate" not in m or "hrv" not in m:
            raise ValueError("missing required measurement fields")
        if not any(e.get("type") == "rmssd" for e in m["hrv"]):
            raise ValueError("missing rmssd entry in measurement.hrv")
        return self


class GarminPayload(BaseModel):
    header: dict
    data: dict

    @model_validator(mode="after")
    def check_structure(self) -> GarminPayload:
        if self.header.get("message_type") != "HEART_RATE_HRV_EPOCH":
            raise ValueError("unexpected or missing header.message_type")
        for key in ("device_id", "collected_at"):
            if key not in self.header:
                raise ValueError(f"missing header.{key}")
        for key in ("heart_rate_bpm", "rmssd_ms"):
            if key not in self.data:
                raise ValueError(f"missing data.{key}")
        return self


class EhrPayload(BaseModel):
    meta: dict
    observations: list[dict]

    @model_validator(mode="after")
    def check_structure(self) -> EhrPayload:
        for key in ("device_id", "received_at", "protocol_version"):
            if key not in self.meta:
                raise ValueError(f"missing meta.{key}")
        codes = {obs.get("code") for obs in self.observations}
        if "8867-4" not in codes:
            raise ValueError("missing heart-rate observation 8867-4")
        if "X-HRV-RMSSD" not in codes:
            raise ValueError("missing RMSSD observation X-HRV-RMSSD")
        return self


# ---------------------------------------------------------------------------
# Parsers – model + _apply mapping only
# ---------------------------------------------------------------------------


class AppleParser(BaseFrameParser):
    brand = "apple"
    payload_model = ApplePayload

    def _apply(self, payload: ApplePayload, context: CardioTraceContext) -> None:
        context.serial_number = payload.deviceInfo["deviceId"]
        context.brand = self.brand
        context.timestamp = datetime.fromisoformat(payload.measurement["timestamp_iso"])
        context.hr = float(payload.measurement["heart_rate"]["value_bpm"])
        context.hrv = next(
            float(e["value_ms"])
            for e in payload.measurement["hrv"]
            if e["type"] == "rmssd"
        )


class GarminParser(BaseFrameParser):
    brand = "garmin"
    payload_model = GarminPayload

    def _apply(self, payload: GarminPayload, context: CardioTraceContext) -> None:
        context.serial_number = payload.header["device_id"]
        context.brand = self.brand
        context.timestamp = datetime.fromisoformat(payload.header["collected_at"])
        context.hr = float(payload.data["heart_rate_bpm"])
        context.hrv = float(payload.data["rmssd_ms"])


class EhrParser(BaseFrameParser):
    brand = "ehr"
    payload_model = EhrPayload

    def _apply(self, payload: EhrPayload, context: CardioTraceContext) -> None:
        by_code = {obs["code"]: obs["value"] for obs in payload.observations}
        context.serial_number = payload.meta["device_id"]
        context.brand = self.brand
        context.timestamp = datetime.fromisoformat(payload.meta["received_at"])
        context.hr = float(by_code["8867-4"])
        context.hrv = float(by_code["X-HRV-RMSSD"])
