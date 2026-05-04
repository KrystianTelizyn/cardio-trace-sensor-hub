import os

import pytest

from app.config import AppSettings


def test_app_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("BACKEND_API_BASE_URL", "http://api:8000")
    monkeypatch.setenv("MQTT_HOST", "broker")
    monkeypatch.setenv("MQTT_PORT", "1883")
    monkeypatch.setenv("MQTT_SUBSCRIBE_PATTERN", "example/#")

    s = AppSettings.from_env(os.environ)
    assert s.redis_url == "redis://redis:6379/0"
    assert s.backend_api_base_url == "http://api:8000"
    assert s.mqtt_host == "broker"
    assert s.mqtt_port == 1883
