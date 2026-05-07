from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.backend_api_client import EnrichedDeviceContext
from app.exceptions import (
    DeviceIdentityNotFoundError,
    PipelineStageError,
    SessionIdentityNotFoundError,
    TenantIdentificationError,
)
from app.models import CardioTraceContext, CardioTraceRecord
from app.pipeline import (
    DEVICE_NOT_FOUND_SENTINEL,
    SESSION_NOT_FOUND_SENTINEL,
    MessagePipeline,
)

from tests.helpers import fake_settings, make_context


@pytest.fixture
def pipeline() -> MessagePipeline:
    settings = fake_settings()

    redis_instance = MagicMock()
    redis_instance.get = AsyncMock(return_value=None)

    backend_instance = MagicMock()
    backend_instance.enrich = AsyncMock(
        return_value=EnrichedDeviceContext(
            device_uid="dev-uid-1", session_uid="sess-uid-1"
        )
    )
    backend_instance.store = AsyncMock()

    return MessagePipeline(settings, redis_instance, backend_instance)


class TestIdentifyTenant:
    def test_extracts_tenant_id(self, pipeline: MessagePipeline) -> None:
        ctx = make_context(b"{}", topic="cardio-trace/tenant-abc/device-1")
        pipeline.identify_tenant(ctx)
        assert ctx.tenant_id == "tenant-abc"

    def test_bad_topic_raises(self, pipeline: MessagePipeline) -> None:
        ctx = make_context(b"{}", topic="bad-topic")
        with pytest.raises(TenantIdentificationError):
            pipeline.identify_tenant(ctx)


class TestBackendIdentification:
    async def test_redis_cache_hit_no_enrich_call(
        self, pipeline: MessagePipeline
    ) -> None:
        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            serial_number="sn1",
            brand="apple",
        )
        pipeline.redis_client.get = AsyncMock(
            side_effect=["dev-from-redis", "sess-from-redis"]
        )

        await pipeline.backend_identification(ctx)

        assert ctx.device_id == "dev-from-redis"
        assert ctx.session_id == "sess-from-redis"
        pipeline.backend_api_client.enrich.assert_not_called()
        assert pipeline.redis_client.get.await_count == 2

    async def test_redis_miss_calls_enrich(self, pipeline: MessagePipeline) -> None:
        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            serial_number="sn1",
            brand="garmin",
        )
        pipeline.redis_client.get = AsyncMock(return_value=None)

        await pipeline.backend_identification(ctx)

        assert ctx.device_id == "dev-uid-1"
        assert ctx.session_id == "sess-uid-1"
        pipeline.backend_api_client.enrich.assert_called_once_with(
            serial_number="sn1", brand="garmin", tenant_id="t1"
        )

    async def test_device_sentinel_raises(self, pipeline: MessagePipeline) -> None:
        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            serial_number="sn1",
            brand="apple",
        )
        pipeline.redis_client.get = AsyncMock(return_value=DEVICE_NOT_FOUND_SENTINEL)

        with pytest.raises(DeviceIdentityNotFoundError):
            await pipeline.backend_identification(ctx)

        pipeline.backend_api_client.enrich.assert_not_called()

    async def test_session_sentinel_raises(self, pipeline: MessagePipeline) -> None:
        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            serial_number="sn1",
            brand="apple",
        )
        pipeline.redis_client.get = AsyncMock(
            side_effect=["dev-from-redis", SESSION_NOT_FOUND_SENTINEL]
        )

        with pytest.raises(SessionIdentityNotFoundError):
            await pipeline.backend_identification(ctx)

        pipeline.backend_api_client.enrich.assert_not_called()

    async def test_device_cached_session_miss_calls_enrich(
        self, pipeline: MessagePipeline
    ) -> None:
        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            serial_number="sn1",
            brand="garmin",
        )
        pipeline.redis_client.get = AsyncMock(side_effect=["dev-from-redis", None])

        await pipeline.backend_identification(ctx)

        assert ctx.device_id == "dev-uid-1"
        assert ctx.session_id == "sess-uid-1"
        pipeline.backend_api_client.enrich.assert_called_once_with(
            serial_number="sn1", brand="garmin", tenant_id="t1"
        )

    async def test_enrich_returns_null_device_raises(
        self, pipeline: MessagePipeline
    ) -> None:
        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            serial_number="sn1",
            brand="garmin",
        )
        pipeline.redis_client.get = AsyncMock(return_value=None)
        pipeline.backend_api_client.enrich = AsyncMock(
            return_value=EnrichedDeviceContext(
                device_uid=None, session_uid="sess-uid-1"
            )
        )

        with pytest.raises(DeviceIdentityNotFoundError):
            await pipeline.backend_identification(ctx)

    async def test_enrich_returns_null_session_raises(
        self, pipeline: MessagePipeline
    ) -> None:
        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            serial_number="sn1",
            brand="garmin",
        )
        pipeline.redis_client.get = AsyncMock(return_value=None)
        pipeline.backend_api_client.enrich = AsyncMock(
            return_value=EnrichedDeviceContext(device_uid="dev-uid-1", session_uid=None)
        )

        with pytest.raises(SessionIdentityNotFoundError):
            await pipeline.backend_identification(ctx)

    async def test_redis_failure_falls_back_to_enrich(
        self, pipeline: MessagePipeline
    ) -> None:
        from redis.exceptions import ConnectionError as RedisConnectionError

        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            serial_number="sn1",
            brand="garmin",
        )
        pipeline.redis_client.get = AsyncMock(side_effect=RedisConnectionError("down"))

        await pipeline.backend_identification(ctx)

        assert ctx.device_id == "dev-uid-1"
        assert ctx.session_id == "sess-uid-1"
        pipeline.backend_api_client.enrich.assert_called_once_with(
            serial_number="sn1", brand="garmin", tenant_id="t1"
        )

    async def test_missing_prerequisites_raises(
        self, pipeline: MessagePipeline
    ) -> None:
        ctx = CardioTraceContext(
            raw=b"{}", topic="x", tenant_id=None, serial_number="s", brand="apple"
        )
        with pytest.raises(PipelineStageError) as ei:
            await pipeline.backend_identification(ctx)
        assert ei.value.stage == "backend_identification"


class TestSaveRecord:
    async def test_happy_path_calls_store(self, pipeline: MessagePipeline) -> None:
        ts = datetime.fromisoformat("2026-05-05T08:25:24.162404")
        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            session_id="sess-1",
            timestamp=ts,
            heart_rate=72.0,
            sdnn=22.0,
            rmssd=40.0,
        )

        await pipeline.save_record(ctx)

        pipeline.backend_api_client.store.assert_called_once()
        call_args = pipeline.backend_api_client.store.call_args
        assert call_args[0][0] == "t1"
        record = call_args[0][1]
        assert isinstance(record, CardioTraceRecord)
        assert record.measurement_session_id == "sess-1"
        assert record.timestamp == ts
        assert record.heart_rate == 72.0
        assert record.sdnn == 22.0
        assert record.rmssd == 40.0

    async def test_missing_fields_raises(self, pipeline: MessagePipeline) -> None:
        ctx = CardioTraceContext(
            raw=b"{}",
            topic="cardio-trace/t1/d1",
            tenant_id="t1",
            session_id="sess-1",
            timestamp=None,
            heart_rate=72.0,
            sdnn=22.0,
            rmssd=40.0,
        )
        with pytest.raises(PipelineStageError) as ei:
            await pipeline.save_record(ctx)
        assert ei.value.stage == "save_record"


class TestOnMessage:
    async def test_end_to_end_apple(
        self, pipeline: MessagePipeline, apple_payload: bytes
    ) -> None:
        topic = "cardio-trace/my-tenant/wearable-1"
        pipeline.redis_client.get = AsyncMock(return_value=None)

        await pipeline.on_message(topic, apple_payload)

        pipeline.backend_api_client.enrich.assert_called_once()
        pipeline.backend_api_client.store.assert_called_once()
        store_call = pipeline.backend_api_client.store.call_args
        assert store_call[0][0] == "my-tenant"
        record: CardioTraceRecord = store_call[0][1]
        assert record.heart_rate == 80.0
        assert record.sdnn == 13.5
        assert record.rmssd == 35.5
        assert record.measurement_session_id == "sess-uid-1"

    async def test_invalid_payload_swallowed(self, pipeline: MessagePipeline) -> None:
        topic = "cardio-trace/t1/d1"
        await pipeline.on_message(topic, b'{"foo": 1}')

        pipeline.backend_api_client.enrich.assert_not_called()
        pipeline.backend_api_client.store.assert_not_called()

    async def test_session_not_found_drops_frame(
        self, pipeline: MessagePipeline, apple_payload: bytes
    ) -> None:
        topic = "cardio-trace/t1/d1"
        pipeline.redis_client.get = AsyncMock(
            side_effect=["dev-from-redis", SESSION_NOT_FOUND_SENTINEL]
        )

        await pipeline.on_message(topic, apple_payload)

        pipeline.backend_api_client.enrich.assert_not_called()
        pipeline.backend_api_client.store.assert_not_called()

    async def test_null_measurements_are_handled_and_stored(
        self, pipeline: MessagePipeline, garmin_payload: bytes
    ) -> None:
        topic = "cardio-trace/t1/d1"
        pipeline.redis_client.get = AsyncMock(return_value=None)
        data = json.loads(garmin_payload)
        data["data"]["heart_rate_bpm"] = None
        data["data"]["sdnn_ms"] = None
        data["data"]["rmssd_ms"] = None

        await pipeline.on_message(topic, json.dumps(data).encode())

        pipeline.backend_api_client.enrich.assert_called_once()
        pipeline.backend_api_client.store.assert_called_once()
        store_call = pipeline.backend_api_client.store.call_args
        assert store_call[0][0] == "t1"
        record: CardioTraceRecord = store_call[0][1]
        assert record.heart_rate is None
        assert record.sdnn is None
        assert record.rmssd is None
