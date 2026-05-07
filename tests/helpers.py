from __future__ import annotations

from pathlib import Path

from app.config import AppSettings
from app.models import CardioTraceContext

REPO_ROOT = Path(__file__).resolve().parent.parent
PAYLOADS_DIR = REPO_ROOT / "payloads"


def load_payload(name: str) -> bytes:
    """Load a JSON payload file from the repo `payloads/` directory as bytes."""
    path = PAYLOADS_DIR / f"{name}.json"
    return path.read_bytes()


def make_context(
    raw: bytes, topic: str = "cardio-trace/tenant-abc/device-1"
) -> CardioTraceContext:
    return CardioTraceContext(raw=raw, topic=topic)


def fake_settings() -> AppSettings:
    return AppSettings(
        host="0.0.0.0",
        port=8000,
        mqtt_host="localhost",
        mqtt_port=1883,
        mqtt_subscribe_pattern="example/#",
        tenant_extraction_regex=r"^cardio-trace/([^/]+)/[^/]+$",
        redis_url="redis://localhost:6379/0",
        backend_api_base_url="http://localhost:8000",
    )
