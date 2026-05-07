from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline import MessagePipeline
from app.sensor_hub import SensorHub

from tests.helpers import fake_settings


@pytest.fixture
def patched_dependencies():
    with (
        patch("app.sensor_hub.MqttIngress", autospec=True) as mqtt_cls,
        patch("app.sensor_hub.Redis.from_url", autospec=True) as redis_from_url,
        patch("app.sensor_hub.BackendApiClient", autospec=True) as backend_cls,
    ):
        redis_instance = MagicMock()
        redis_instance.aclose = AsyncMock()
        redis_from_url.return_value = redis_instance

        backend_instance = MagicMock()
        backend_instance.shutdown = AsyncMock()
        backend_cls.return_value = backend_instance

        mqtt_instance = MagicMock()
        mqtt_instance.start = AsyncMock()
        mqtt_instance.stop = AsyncMock()
        mqtt_cls.return_value = mqtt_instance

        yield {
            "mqtt_cls": mqtt_cls,
            "mqtt_instance": mqtt_instance,
            "redis_instance": redis_instance,
            "backend_instance": backend_instance,
        }


def test_pipeline_is_injected_into_mqtt_ingress(patched_dependencies) -> None:
    settings = fake_settings()

    hub = SensorHub(settings)

    assert isinstance(hub.pipeline, MessagePipeline)
    assert hub.pipeline.redis_client is patched_dependencies["redis_instance"]
    assert hub.pipeline.backend_api_client is patched_dependencies["backend_instance"]

    patched_dependencies["mqtt_cls"].assert_called_once_with(
        settings.mqtt_host,
        settings.mqtt_port,
        settings.mqtt_subscribe_pattern,
        hub.pipeline,
    )


async def test_lifecycle_starts_and_stops_dependencies(patched_dependencies) -> None:
    settings = fake_settings()

    async with SensorHub(settings) as hub:
        patched_dependencies["mqtt_instance"].start.assert_awaited_once()
        patched_dependencies["mqtt_instance"].stop.assert_not_called()

    patched_dependencies["mqtt_instance"].stop.assert_awaited_once()
    patched_dependencies["redis_instance"].aclose.assert_awaited_once()
    patched_dependencies["backend_instance"].shutdown.assert_awaited_once()
    assert hub.pipeline is not None
