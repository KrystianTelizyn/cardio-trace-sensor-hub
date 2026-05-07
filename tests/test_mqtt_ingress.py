from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

from app.mqtt_ingress import MqttIngress


@dataclass
class FakeMessage:
    topic_value: str
    payload: bytes

    @property
    def topic(self) -> SimpleNamespace:
        return SimpleNamespace(value=self.topic_value)


class AsyncMessageStream:
    def __init__(
        self, messages: list[FakeMessage] | None = None, error: Exception | None = None
    ) -> None:
        self._messages = messages or []
        self._error = error
        self._index = 0

    def __aiter__(self) -> AsyncMessageStream:
        return self

    async def __anext__(self) -> FakeMessage:
        if self._index < len(self._messages):
            msg = self._messages[self._index]
            self._index += 1
            return msg
        if self._error is not None:
            raise self._error
        await asyncio.Event().wait()
        raise RuntimeError("unreachable")


class FakeClient:
    def __init__(
        self,
        *,
        messages: AsyncMessageStream | None = None,
        enter_error: Exception | None = None,
    ) -> None:
        self.messages = messages or AsyncMessageStream()
        self._enter_error = enter_error
        self.subscribe = AsyncMock()

    async def __aenter__(self) -> FakeClient:
        if self._enter_error is not None:
            raise self._enter_error
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


async def test_reconnects_after_connection_error() -> None:
    logic = AsyncMock()
    ingress = MqttIngress("localhost", 1883, "cardio/#", logic, initial_backoff=0.01)

    first_client = FakeClient(enter_error=RuntimeError("broker down"))
    subscribed = asyncio.Event()
    second_client = FakeClient(messages=AsyncMessageStream())
    second_client.subscribe = AsyncMock(side_effect=lambda *a, **kw: subscribed.set())
    clients = [first_client, second_client]

    def client_factory(**kwargs) -> FakeClient:
        if clients:
            return clients.pop(0)
        return second_client

    with (
        patch("app.mqtt_ingress.Client", side_effect=client_factory),
        patch(
            "app.mqtt_ingress.asyncio.sleep", new=AsyncMock(return_value=None)
        ) as sleep_mock,
    ):
        task = asyncio.create_task(ingress.consume_loop())
        await asyncio.wait_for(subscribed.wait(), timeout=1)
        assert task.done() is False
        assert sleep_mock.await_count >= 1
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert ingress.connected is False


async def test_backoff_resets_after_successful_connection() -> None:
    logic = AsyncMock()
    ingress = MqttIngress("localhost", 1883, "cardio/#", logic, initial_backoff=0.01)

    first_client = FakeClient(enter_error=RuntimeError("first failure"))
    second_client = FakeClient(
        messages=AsyncMessageStream(error=RuntimeError("drop after success"))
    )
    clients = [first_client, second_client]

    def client_factory(**kwargs) -> FakeClient:
        if clients:
            return clients.pop(0)
        return second_client

    sleep_mock = AsyncMock(side_effect=[None, asyncio.CancelledError()])

    with (
        patch("app.mqtt_ingress.Client", side_effect=client_factory),
        patch("app.mqtt_ingress.asyncio.sleep", new=sleep_mock),
    ):
        task = asyncio.create_task(ingress.consume_loop())
        await asyncio.gather(task, return_exceptions=True)

    assert sleep_mock.await_args_list == [call(0.01), call(0.01)]


async def test_stop_cancels_while_waiting_in_backoff() -> None:
    logic = AsyncMock()
    ingress = MqttIngress("localhost", 1883, "cardio/#", logic, initial_backoff=0.01)
    failing_client = FakeClient(enter_error=RuntimeError("always down"))
    entered_sleep = asyncio.Event()

    async def blocking_sleep(delay: float) -> None:
        entered_sleep.set()
        await asyncio.Event().wait()

    with (
        patch("app.mqtt_ingress.Client", return_value=failing_client),
        patch("app.mqtt_ingress.asyncio.sleep", side_effect=blocking_sleep),
    ):
        await ingress.start()
        await asyncio.wait_for(entered_sleep.wait(), timeout=1)
        await ingress.stop()

    assert ingress.task is None
    assert ingress.connected is False


async def test_messages_are_dispatched_to_logic() -> None:
    logic = AsyncMock()
    ingress = MqttIngress("localhost", 1883, "cardio/#", logic)
    message = FakeMessage("cardio/tenant-1/device-1", b'{"v":1}')
    client = FakeClient(messages=AsyncMessageStream(messages=[message]))

    with patch("app.mqtt_ingress.Client", return_value=client):
        task = asyncio.create_task(ingress.consume_loop())
        while logic.on_message.await_count == 0:
            await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    logic.on_message.assert_awaited_once_with(message.topic_value, message.payload)
