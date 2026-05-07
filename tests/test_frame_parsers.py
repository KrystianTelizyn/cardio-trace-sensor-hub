from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.exceptions import FrameParsingError
from app.parsers.apple import ApplePayload
from app.parsers.ehr import EhrPayload
from app.parsers.frame_parsers import PAYLOAD_MODELS, parse_frame
from app.parsers.garmin import GarminPayload
from app.parsers.types import ParsedFrame

EXPECTED_TS = datetime.fromisoformat("2026-05-05T08:25:24.162404")
EXPECTED_SN = "1234567890"
EXPECTED_HR = 80.0
EXPECTED_SDNN = 13.5
EXPECTED_RMSSD = 35.5


def _assert_common_measurements(frame: ParsedFrame, *, brand: str) -> None:
    assert frame.brand == brand
    assert frame.serial_number == EXPECTED_SN
    assert frame.timestamp == EXPECTED_TS
    assert frame.heart_rate == EXPECTED_HR
    assert frame.sdnn == EXPECTED_SDNN
    assert frame.rmssd == EXPECTED_RMSSD


class TestApplePayload:
    def test_to_frame_happy_path(self, apple_payload: bytes) -> None:
        frame = ApplePayload.model_validate_json(apple_payload).to_frame()
        _assert_common_measurements(frame, brand="apple")

    def test_parse_frame_routes_apple(self, apple_payload: bytes) -> None:
        frame = parse_frame(apple_payload)
        _assert_common_measurements(frame, brand="apple")

    def test_parse_missing_device_id_raises(self, apple_payload: bytes) -> None:
        data = json.loads(apple_payload)
        del data["deviceInfo"]["deviceId"]
        raw = json.dumps(data).encode()
        with pytest.raises(FrameParsingError):
            parse_frame(raw)

    def test_parse_allows_null_measurements(self, apple_payload: bytes) -> None:
        data = json.loads(apple_payload)
        data["measurement"]["heart_rate"]["value_bpm"] = None
        for entry in data["measurement"]["hrv"]:
            if entry["type"] in ("sdnn", "rmssd"):
                entry["value_ms"] = None
        frame = parse_frame(json.dumps(data).encode())
        assert frame.heart_rate is None
        assert frame.sdnn is None
        assert frame.rmssd is None

    def test_extra_fields_are_ignored(self, apple_payload: bytes) -> None:
        data = json.loads(apple_payload)
        data["unexpected"] = {"ignored": True}
        data["deviceInfo"]["firmware"] = {"version": "1.0.0"}
        data["measurement"]["heart_rate"]["confidence"] = 0.97
        frame = parse_frame(json.dumps(data).encode())
        _assert_common_measurements(frame, brand="apple")


class TestGarminPayload:
    def test_to_frame_happy_path(self, garmin_payload: bytes) -> None:
        frame = GarminPayload.model_validate_json(garmin_payload).to_frame()
        _assert_common_measurements(frame, brand="garmin")

    def test_parse_frame_routes_garmin(self, garmin_payload: bytes) -> None:
        frame = parse_frame(garmin_payload)
        _assert_common_measurements(frame, brand="garmin")

    def test_parse_allows_null_measurements(self, garmin_payload: bytes) -> None:
        data = json.loads(garmin_payload)
        data["data"]["heart_rate_bpm"] = None
        data["data"]["sdnn_ms"] = None
        data["data"]["rmssd_ms"] = None
        frame = parse_frame(json.dumps(data).encode())
        assert frame.heart_rate is None
        assert frame.sdnn is None
        assert frame.rmssd is None

    def test_parse_wrong_message_type_raises(self, garmin_payload: bytes) -> None:
        data = json.loads(garmin_payload)
        data["header"]["message_type"] = "OTHER"
        with pytest.raises(FrameParsingError):
            parse_frame(json.dumps(data).encode())


class TestEhrPayload:
    def test_to_frame_happy_path(self, ehr_payload: bytes) -> None:
        frame = EhrPayload.model_validate_json(ehr_payload).to_frame()
        _assert_common_measurements(frame, brand="ehr")

    def test_parse_frame_routes_ehr(self, ehr_payload: bytes) -> None:
        frame = parse_frame(ehr_payload)
        _assert_common_measurements(frame, brand="ehr")

    def test_parse_allows_null_measurements(self, ehr_payload: bytes) -> None:
        data = json.loads(ehr_payload)
        for observation in data["observations"]:
            if observation["code"] in ("8867-4", "X-HRV-SDNN", "X-HRV-RMSSD"):
                observation["value"] = None
        frame = parse_frame(json.dumps(data).encode())
        assert frame.heart_rate is None
        assert frame.sdnn is None
        assert frame.rmssd is None

    def test_parse_missing_observation_raises(self, ehr_payload: bytes) -> None:
        data = json.loads(ehr_payload)
        data["observations"] = [
            observation
            for observation in data["observations"]
            if observation["code"] != "X-HRV-SDNN"
        ]
        with pytest.raises(FrameParsingError):
            parse_frame(json.dumps(data).encode())


class TestParseFrame:
    def test_no_parser_found(self) -> None:
        with pytest.raises(FrameParsingError, match="No parser found"):
            parse_frame(b'{"foo": 1}')

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(FrameParsingError, match="No parser found"):
            parse_frame(b"not json")

    def test_multiple_parsers_matched_raises(
        self, monkeypatch: pytest.MonkeyPatch, apple_payload: bytes
    ) -> None:
        monkeypatch.setattr(
            "app.parsers.frame_parsers.PAYLOAD_MODELS",
            [*PAYLOAD_MODELS, ApplePayload],
        )
        with pytest.raises(FrameParsingError, match="Multiple parsers matched"):
            parse_frame(apple_payload)
