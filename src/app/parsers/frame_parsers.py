from __future__ import annotations

from pydantic import ValidationError

from app.exceptions import FrameParsingError
from app.parsers.apple import ApplePayload
from app.parsers.ehr import EhrPayload
from app.parsers.garmin import GarminPayload
from app.parsers.types import FramePayload, ParsedFrame

PAYLOAD_MODELS: list[type[FramePayload]] = [
    ApplePayload,
    GarminPayload,
    EhrPayload,
]


def parse_frame(raw: bytes) -> ParsedFrame:
    matches: list[FramePayload] = []
    for model_cls in PAYLOAD_MODELS:
        try:
            payload = model_cls.model_validate_json(raw)  # type: ignore[union-attr]
            matches.append(payload)  # type: ignore[arg-type]
        except (ValidationError, ValueError):
            continue
    if not matches:
        raise FrameParsingError("No parser found for the given context")
    if len(matches) > 1:
        raise FrameParsingError("Multiple parsers matched the given context")
    return matches[0].to_frame()
