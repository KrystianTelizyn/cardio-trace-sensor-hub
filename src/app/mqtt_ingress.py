from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from aiomqtt import Client


logger = logging.getLogger(__name__)


class IngressLogic(Protocol):
    async def on_message(self, topic: str, payload: bytes) -> None: ...


class MqttIngress:
    def __init__(
        self,
        mqtt_host: str,
        mqtt_port: int,
        mqtt_subscribe_pattern: str,
        logic: IngressLogic,
    ) -> None:
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port
        self._mqtt_subscribe_pattern = mqtt_subscribe_pattern
        self._task: asyncio.Task[None] | None = None
        self.connected = False
        self._logic = logic

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._consume_loop(), name="mqtt-ingress")

    async def stop(self) -> None:
        if self._task is None or self._task.done():
            self._task = None
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self.connected = False

    async def _consume_loop(self) -> None:
        try:
            async with Client(
                hostname=self._mqtt_host,
                port=self._mqtt_port,
            ) as client:
                await client.subscribe(self._mqtt_subscribe_pattern)
                self.connected = True
                async for _message in client.messages:
                    await self._logic.on_message(_message.topic, _message.payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("MQTT ingress loop exited with an error")
            raise
        finally:
            self.connected = False
