from typing import Any


class BackendApiClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    async def send_message(self, message: str) -> None: ...
    async def enrich(self, *args: Any, **kwargs: Any) -> None: ...
    async def store(self, *args: Any, **kwargs: Any) -> None: ...
