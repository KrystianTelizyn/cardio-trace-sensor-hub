from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backend_api_client import EnrichedDeviceContext
from app.exceptions import PipelineStageError, TenantIdentificationError
from app.models import CardioTraceContext, CardioTraceRecord
from app.sensor_hub import SensorHub

from tests.helpers import fake_settings, make_context


@pytest.fixture
def sensor_hub():
    settings = fake_settings()
    with (
        patch("app.sensor_hub.MqttIngress", autospec=True),
        patch("app.sensor_hub.Redis.from_url", autospec=True) as redis_from_url,
        patch("app.sensor_hub.BackendApiClient", autospec=True) as backend_cls,
    ):
        redis_instance = MagicMock()
        redis_instance.get = AsyncMock(return_value=None)
        redis_from_url.return_value = redis_instance

        backend_instance = MagicMock()
        backend_instance.enrich = AsyncMock(
            return_value=EnrichedDeviceContext(
                device_uid="dev-uid-1", session_uid="sess-uid-1"
            )
        )
        backend_instance.store = AsyncMock()
        backend_instance.shutdown = AsyncMock()
        backend_instance.is_ready = AsyncMock(return_value=True)
        backend_cls.return_value = backend_instance

        hub = SensorHub(settings)
        yield hub


class TestIdentifyTenant:
    def test_extracts_tenant_id(self, sensor_hub: SensorHub) -> None:
        ctx = make_context(b"{}", topic="cardio-trace/tenant-abc/device-1")
        sensor_hub.identify_tenant(ctx)
        assert ctx.tenant_id == "tenant-abc"

    def test_bad_topic_raises(self, sensor_hub: SensorHub) -> None:
        ctx = make_context(b"{}", topic="bad-topic")
        with pytest.raises(TenantIdentificationError):
            sensor_hub.identify_tenant(ctx)


class TestBackendIdentification:
    async def test_redis_cache_hit_no_enrich_call(self, sensor_hub: SensorHub) -> None:
        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            serial_number="sn1",
            brand="apple",
        )
        sensor_hub.redis_client.get = AsyncMock(
            side_effect=["dev-from-redis", "sess-from-redis"]
        )

        await sensor_hub.backend_identification(ctx)

        assert ctx.device_id == "dev-from-redis"
        assert ctx.session_id == "sess-from-redis"
        sensor_hub.backend_api_client.enrich.assert_not_called()
        assert sensor_hub.redis_client.get.await_count == 2

    async def test_redis_miss_calls_enrich(self, sensor_hub: SensorHub) -> None:
        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            serial_number="sn1",
            brand="garmin",
        )
        sensor_hub.redis_client.get = AsyncMock(return_value=None)

        await sensor_hub.backend_identification(ctx)

        assert ctx.device_id == "dev-uid-1"
        assert ctx.session_id == "sess-uid-1"
        sensor_hub.backend_api_client.enrich.assert_called_once_with(
            serial_number="sn1", brand="garmin"
        )

    async def test_missing_prerequisites_raises(self, sensor_hub: SensorHub) -> None:
        ctx = CardioTraceContext(
            raw=b"{}", topic="x", tenant_id=None, serial_number="s", brand="apple"
        )
        with pytest.raises(PipelineStageError) as ei:
            await sensor_hub.backend_identification(ctx)
        assert ei.value.stage == "backend_identification"


class TestSaveRecord:
    async def test_happy_path_calls_store(self, sensor_hub: SensorHub) -> None:
        ts = datetime.fromisoformat("2026-05-05T08:25:24.162404")
        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            session_id="sess-1",
            timestamp=ts,
            hr=72.0,
            hrv=40.0,
        )

        await sensor_hub.save_record(ctx)

        sensor_hub.backend_api_client.store.assert_called_once()
        call_args = sensor_hub.backend_api_client.store.call_args
        assert call_args[0][0] == "t1"
        record = call_args[0][1]
        assert isinstance(record, CardioTraceRecord)
        assert record.measurement_session_id == "sess-1"
        assert record.timestamp == ts
        assert record.heart_rate == 72.0
        assert record.hrv == 40.0

    async def test_missing_fields_raises(self, sensor_hub: SensorHub) -> None:
        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            session_id="sess-1",
            timestamp=None,
            hr=72.0,
            hrv=40.0,
        )
        with pytest.raises(PipelineStageError) as ei:
            await sensor_hub.save_record(ctx)
        assert ei.value.stage == "save_record"


class TestOnMessage:
    async def test_end_to_end_apple(
        self, sensor_hub: SensorHub, apple_payload: bytes
    ) -> None:
        topic = "cardio-trace/my-tenant/wearable-1"
        sensor_hub.redis_client.get = AsyncMock(return_value=None)

        await sensor_hub.on_message(topic, apple_payload)

        sensor_hub.backend_api_client.enrich.assert_called_once()
        sensor_hub.backend_api_client.store.assert_called_once()
        store_call = sensor_hub.backend_api_client.store.call_args
        assert store_call[0][0] == "my-tenant"
        record: CardioTraceRecord = store_call[0][1]
        assert record.heart_rate == 80.0
        assert record.hrv == 35.5
        assert record.measurement_session_id == "sess-uid-1"

    async def test_invalid_payload_swallowed(self, sensor_hub: SensorHub) -> None:
        topic = "cardio-trace/t1/d1"
        await sensor_hub.on_message(topic, b'{"foo": 1}')

        sensor_hub.backend_api_client.enrich.assert_not_called()
        sensor_hub.backend_api_client.store.assert_not_called()

    async def test_null_measurements_are_handled_but_not_stored(
        self, sensor_hub: SensorHub, garmin_payload: bytes
    ) -> None:
        topic = "cardio-trace/t1/d1"
        sensor_hub.redis_client.get = AsyncMock(return_value=None)
        data = json.loads(garmin_payload)
        data["data"]["heart_rate_bpm"] = None
        data["data"]["sdnn_ms"] = None
        data["data"]["rmssd_ms"] = None

        await sensor_hub.on_message(topic, json.dumps(data).encode())

        sensor_hub.backend_api_client.enrich.assert_called_once()
        sensor_hub.backend_api_client.store.assert_not_called()
