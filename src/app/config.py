from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from app.exceptions import ConfigError


class Env:
    """Minimal environment accessor (empty strings treated as unset)."""

    def __init__(self, environ: Mapping[str, str]):
        self._environ = environ

    def __call__(
        self, key: str, *, required: bool = True, default: str | None = None
    ) -> str | None:
        value = self._environ.get(key)
        if value is not None:
            value = value.strip() or None
        if value is None:
            value = default
        if required and value is None:
            raise ConfigError(f"Missing required environment variable: {key}")
        return value


@dataclass(frozen=True)
class AppSettings:
    """Application configuration loaded from process environment."""

    host: str
    port: int
    mqtt_host: str
    mqtt_port: int
    mqtt_subscribe_pattern: str
    redis_url: str
    backend_api_base_url: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AppSettings:
        env = Env(environ if environ is not None else os.environ)
        port_s = env("PORT", required=False) or "8000"
        mqtt_port_s = env("MQTT_PORT", required=False) or "1883"
        return cls(
            host=env("HOST", required=False) or "0.0.0.0",
            port=int(port_s),
            mqtt_host=env("MQTT_HOST", required=False) or "localhost",
            mqtt_port=int(mqtt_port_s),
            mqtt_subscribe_pattern=env("MQTT_SUBSCRIBE_PATTERN", required=False)
            or "example/#",
            redis_url=env("REDIS_URL"),
            backend_api_base_url=env("BACKEND_API_BASE_URL"),
        )
