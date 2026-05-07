from __future__ import annotations

import pytest

from app.config import AppSettings

from tests.helpers import load_payload


@pytest.fixture
def apple_payload() -> bytes:
    return load_payload("apple")


@pytest.fixture
def garmin_payload() -> bytes:
    return load_payload("garmin")


@pytest.fixture
def ehr_payload() -> bytes:
    return load_payload("ehr")


@pytest.fixture
def app_settings() -> AppSettings:
    from tests.helpers import fake_settings

    return fake_settings()
