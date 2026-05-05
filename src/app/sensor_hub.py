from app.config import AppSettings
from app.mqtt_ingress import MqttIngress
from redis.asyncio import Redis
from app.backend_api_client import BackendApiClient
import logging
from app.models import CardioTraceContext
from app.parsers import ParsersChain
from app.exceptions import SensorHubException, TenantIdentificationError
import re

logger = logging.getLogger(__name__)


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
        if context.serial_number is None or context.brand is None:
            raise SensorHubException("Missing serial number or brand for enrichment")
        enriched = await self.backend_api_client.enrich(
            serial_number=context.serial_number, brand=context.brand
        )
        context.device_id = enriched.device_uid
        context.session_id = enriched.session_uid

    async def save_record(self, context: CardioTraceContext) -> None:
        await self.backend_api_client.store(context)
