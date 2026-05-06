from app.config import AppSettings
from app.mqtt_ingress import MqttIngress
from redis.asyncio import Redis
from app.backend_api_client import BackendApiClient
import logging
from app.models import CardioTraceContext, CardioTraceRecord
from app.parsers import ParsersChain
from app.exceptions import (
    DeviceIdentityNotFoundError,
    PipelineStageError,
    SensorHubException,
    TenantIdentificationError,
)
import re

logger = logging.getLogger(__name__)
DEVICE_NOT_FOUND_SENTINEL = "NONE"


class SensorHub:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.mqtt_ingress = MqttIngress(
            settings.mqtt_host,
            settings.mqtt_port,
            settings.mqtt_subscribe_pattern,
            self,
        )
        self.redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        self.backend_api_client = BackendApiClient(settings.backend_api_base_url)
        self.parsers_chain = ParsersChain()

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self.mqtt_ingress.stop()
        await self.redis_client.aclose()
        await self.backend_api_client.shutdown()

    async def __aenter__(self) -> "SensorHub":
        await self.mqtt_ingress.start()
        return self

    async def is_ready(self) -> dict[str, bool]:
        return {
            "redis": await self.redis_client.ping(),
            "mqtt_ingress": self.mqtt_ingress.connected,
            "backend_api_client": await self.backend_api_client.is_ready(),
        }

    async def on_message(self, topic: str, payload: bytes) -> None:
        # Execute pipeline
        try:
            context = CardioTraceContext(raw=payload, topic=topic)
            self.identify_tenant(context)
            self.discover_device_specifics(context)
            await self.backend_identification(context)
            await self.save_record(context)
        except DeviceIdentityNotFoundError as e:
            logger.warning(f"Frame dropped on topic {topic}: {e}")
        # Fallback
        except SensorHubException as e:
            logger.exception(f"Error processing message on topic {topic}: {e}")

    def identify_tenant(self, context: CardioTraceContext) -> None:
        match = re.match(self.settings.tenant_extraction_regex, context.topic)
        if match:
            context.tenant_id = match.group(1)
        else:
            raise TenantIdentificationError(
                f"Could not extract tenant_id from topic '{context.topic}' using pattern '{self.settings.mqtt_subscribe_pattern}'"
            )

    def discover_device_specifics(self, context: CardioTraceContext) -> None:
        self.parsers_chain.parse(context)

    async def backend_identification(self, context: CardioTraceContext) -> None:
        if (
            context.tenant_id is None
            or context.serial_number is None
            or context.brand is None
        ):
            raise PipelineStageError(
                stage="backend_identification",
                message="Missing tenant_id, serial number, or brand for enrichment",
            )

        device_map_key = (
            f"device_map:{context.tenant_id}:{context.brand}:{context.serial_number}"
        )
        device_uid = await self.redis_client.get(device_map_key)
        if device_uid == DEVICE_NOT_FOUND_SENTINEL:
            raise DeviceIdentityNotFoundError(
                f"Device not registered: {context.brand}/{context.serial_number}"
            )

        if device_uid is not None:
            device_session_key = f"device_session:{context.tenant_id}:{device_uid}"
            session_uid = await self.redis_client.get(device_session_key)
            if session_uid is not None:
                context.device_id = device_uid
                context.session_id = session_uid
                return

        enriched = await self.backend_api_client.enrich(
            serial_number=context.serial_number,
            brand=context.brand,
            tenant_id=context.tenant_id,
        )
        if enriched.device_uid is None:
            raise DeviceIdentityNotFoundError(
                f"Device not registered: {context.brand}/{context.serial_number}"
            )
        context.device_id = enriched.device_uid
        context.session_id = enriched.session_uid

    async def save_record(self, context: CardioTraceContext) -> None:
        if (
            context.tenant_id is None
            or context.session_id is None
            or context.timestamp is None
        ):
            raise PipelineStageError(
                stage="save_record",
                message="Missing one or more required context fields",
            )

        record = CardioTraceRecord(
            measurement_session_id=context.session_id,
            timestamp=context.timestamp,
            heart_rate=context.hr,
            sdnn=context.sdnn,
            rmssd=context.rmssd,
        )
        await self.backend_api_client.store(context.tenant_id, record)
