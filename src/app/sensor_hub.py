from redis.asyncio import Redis

from app.backend_api_client import BackendApiClient
from app.config import AppSettings
from app.mqtt_ingress import MqttIngress
from app.pipeline import MessagePipeline


class SensorHub:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        self.backend_api_client = BackendApiClient(settings.backend_api_base_url)
        self.pipeline = MessagePipeline(
            settings, self.redis_client, self.backend_api_client
        )
        self.mqtt_ingress = MqttIngress(
            settings.mqtt_host,
            settings.mqtt_port,
            settings.mqtt_subscribe_pattern,
            self.pipeline,
        )

    async def __aenter__(self) -> "SensorHub":
        await self.mqtt_ingress.start()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self.mqtt_ingress.stop()
        await self.redis_client.aclose()
        await self.backend_api_client.shutdown()

    async def is_ready(self) -> dict[str, bool]:
        return {
            "redis": await self.redis_client.ping(),
            "mqtt_ingress": self.mqtt_ingress.connected,
            "backend_api_client": await self.backend_api_client.is_ready(),
        }
