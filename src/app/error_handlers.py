from fastapi import Request
from fastapi.responses import JSONResponse

from app.exceptions import HubNotReadyError


async def hub_not_ready_handler(
    _request: Request,
    exc: HubNotReadyError,
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": exc.message, "checks": exc.checks},
    )
