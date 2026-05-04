from app.config import AppSettings
from app.mqtt_ingress import MqttIngress
from redis.asyncio import Redis
from app.backend_api_client import BackendApiClient


class SensorHub:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._mqtt_ingress = MqttIngress(
            settings.mqtt_host,
            settings.mqtt_port,
            settings.mqtt_subscribe_pattern,
            self,
        )
        self._redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        self._backend_api_client = BackendApiClient(settings.backend_api_base_url)

    async def shutdown(self) -> None:
        await self._mqtt_ingress.stop()
        await self._redis_client.aclose()
        await self._backend_api_client.shutdown()

    async def start(self) -> None:
        await self._mqtt_ingress.start()

    async def on_message(
        self, topic: str, payload: bytes
    ) -> None: ...  # TODO: normalize, enrich, forward to backend API
