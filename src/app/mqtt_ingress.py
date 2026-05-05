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
        self.host = mqtt_host
        self.port = mqtt_port
        self.subscribe_pattern = mqtt_subscribe_pattern
        self.task: asyncio.Task[None] | None = None
        self.connected = False
        self.ingress_logic = logic

    async def start(self) -> None:
        if self.task is not None:
            return
        self.task = asyncio.create_task(self.consume_loop(), name="mqtt-ingress")

    async def stop(self) -> None:
        if self.task is None or self.task.done():
            self.task = None
            return
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        self.task = None
        self.connected = False

    async def consume_loop(self) -> None:
        try:
            async with Client(
                hostname=self.host,
                port=self.port,
            ) as client:
                await client.subscribe(self.subscribe_pattern)
                self.connected = True
                async for message in client.messages:
                    await self.ingress_logic.on_message(message.topic, message.payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("MQTT ingress loop exited with an error")
            raise
        finally:
            self.connected = False
