from app.config import AppSettings
from app.mqtt_ingress import MqttIngress
from redis.asyncio import Redis
from app.backend_api_client import BackendApiClient
import logging

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
        str_payload = payload.decode("utf-8")
        logger.info(f"Received message on topic {topic}: {str_payload}")
        await self.redis_client.incr("message_count")
