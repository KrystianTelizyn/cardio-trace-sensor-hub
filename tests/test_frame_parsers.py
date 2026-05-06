from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.exceptions import FrameParsingError
from app.models import CardioTraceContext
from app.parsers.frame_parsers import (
    AppleParser,
    EhrParser,
    GarminParser,
    ParsersChain,
)

from tests.helpers import make_context

EXPECTED_TS = datetime.fromisoformat("2026-05-05T08:25:24.162404")
EXPECTED_SN = "1234567890"
EXPECTED_HR = 80.0
EXPECTED_SDNN = 13.5
EXPECTED_RMSSD = 35.5
EXPECTED_HRV = 35.5


def _assert_common_measurements(ctx: CardioTraceContext) -> None:
    assert ctx.serial_number == EXPECTED_SN
    assert ctx.timestamp == EXPECTED_TS
    assert ctx.hr == EXPECTED_HR
    assert ctx.sdnn == EXPECTED_SDNN
    assert ctx.rmssd == EXPECTED_RMSSD
    assert ctx.hrv == EXPECTED_HRV


class TestAppleParser:
    def test_parse_happy_path(self, apple_payload: bytes) -> None:
        ctx = make_context(apple_payload)
        AppleParser().parse(ctx)
        assert ctx.brand == "apple"
        _assert_common_measurements(ctx)

    def test_parsing_applicable_only_apple(
        self, apple_payload: bytes, garmin_payload: bytes, ehr_payload: bytes
    ) -> None:
        p = AppleParser()
        assert p.parsing_applicable(make_context(apple_payload)) is True
        assert p.parsing_applicable(make_context(garmin_payload)) is False
        assert p.parsing_applicable(make_context(ehr_payload)) is False

    def test_parse_missing_device_id_raises(self, apple_payload: bytes) -> None:
        data = json.loads(apple_payload)
        del data["deviceInfo"]["deviceId"]
        raw = json.dumps(data).encode()
        ctx = make_context(raw)
        with pytest.raises(FrameParsingError):
            AppleParser().parse(ctx)

    def test_parsing_applicable_invalid_json(self) -> None:
        assert AppleParser().parsing_applicable(make_context(b"not json")) is False

    def test_parse_allows_null_hr_sdnn_rmssd(self, apple_payload: bytes) -> None:
        data = json.loads(apple_payload)
        data["measurement"]["heart_rate"]["value_bpm"] = None
        for entry in data["measurement"]["hrv"]:
            if entry["type"] in ("sdnn", "rmssd"):
                entry["value_ms"] = None
        ctx = make_context(json.dumps(data).encode())
        AppleParser().parse(ctx)
        assert ctx.hr is None
        assert ctx.sdnn is None
        assert ctx.rmssd is None
        assert ctx.hrv is None


class TestGarminParser:
    def test_parse_happy_path(self, garmin_payload: bytes) -> None:
        ctx = make_context(garmin_payload)
        GarminParser().parse(ctx)
        assert ctx.brand == "garmin"
        _assert_common_measurements(ctx)

    def test_parsing_applicable_only_garmin(
        self, apple_payload: bytes, garmin_payload: bytes, ehr_payload: bytes
    ) -> None:
        p = GarminParser()
        assert p.parsing_applicable(make_context(apple_payload)) is False
        assert p.parsing_applicable(make_context(garmin_payload)) is True
        assert p.parsing_applicable(make_context(ehr_payload)) is False

    def test_parse_allows_null_hr_sdnn_rmssd(self, garmin_payload: bytes) -> None:
        data = json.loads(garmin_payload)
        data["data"]["heart_rate_bpm"] = None
        data["data"]["sdnn_ms"] = None
        data["data"]["rmssd_ms"] = None
        ctx = make_context(json.dumps(data).encode())
        GarminParser().parse(ctx)
        assert ctx.hr is None
        assert ctx.sdnn is None
        assert ctx.rmssd is None
        assert ctx.hrv is None


class TestEhrParser:
    def test_parse_happy_path(self, ehr_payload: bytes) -> None:
        ctx = make_context(ehr_payload)
        EhrParser().parse(ctx)
        assert ctx.brand == "ehr"
        _assert_common_measurements(ctx)

    def test_parsing_applicable_only_ehr(
        self, apple_payload: bytes, garmin_payload: bytes, ehr_payload: bytes
    ) -> None:
        p = EhrParser()
        assert p.parsing_applicable(make_context(apple_payload)) is False
        assert p.parsing_applicable(make_context(garmin_payload)) is False
        assert p.parsing_applicable(make_context(ehr_payload)) is True

    def test_parse_allows_null_hr_sdnn_rmssd(self, ehr_payload: bytes) -> None:
        data = json.loads(ehr_payload)
        for observation in data["observations"]:
            if observation["code"] in ("8867-4", "X-HRV-SDNN", "X-HRV-RMSSD"):
                observation["value"] = None
        ctx = make_context(json.dumps(data).encode())
        EhrParser().parse(ctx)
        assert ctx.hr is None
        assert ctx.sdnn is None
        assert ctx.rmssd is None
        assert ctx.hrv is None


class TestParsersChain:
    def test_routes_apple(self, apple_payload: bytes) -> None:
        ctx = make_context(apple_payload)
        ParsersChain().parse(ctx)
        assert ctx.brand == "apple"
        _assert_common_measurements(ctx)

    def test_routes_garmin(self, garmin_payload: bytes) -> None:
        ctx = make_context(garmin_payload)
        ParsersChain().parse(ctx)
        assert ctx.brand == "garmin"
        _assert_common_measurements(ctx)

    def test_routes_ehr(self, ehr_payload: bytes) -> None:
        ctx = make_context(ehr_payload)
        ParsersChain().parse(ctx)
        assert ctx.brand == "ehr"
        _assert_common_measurements(ctx)

    def test_no_parser_found(self) -> None:
        ctx = make_context(b'{"foo": 1}')
        with pytest.raises(FrameParsingError, match="No parser found"):
            ParsersChain().parse(ctx)

    def test_multiple_parsers_raises(self, apple_payload: bytes) -> None:
        chain = ParsersChain()
        chain.add_parser(AppleParser())
        ctx = make_context(apple_payload)
        with pytest.raises(FrameParsingError, match="Multiple parsers found"):
            chain.parse(ctx)
