from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.types import Lifespan

from app.config import AppSettings
from app.error_handlers import hub_not_ready_handler
from app.exceptions import HubNotReadyError
from app.routes import router
from app.sensor_hub import SensorHub


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    settings = AppSettings.from_env()
    sensor_hub = SensorHub(settings)
    app.state.sensor_hub = sensor_hub
    yield
    await sensor_hub.shutdown()


def create_app(*, lifespan: Lifespan[FastAPI] | None = None) -> FastAPI:
    app = FastAPI(title="Cardio Trace Sensor Hub", lifespan=lifespan)
    app.add_exception_handler(HubNotReadyError, hub_not_ready_handler)
    app.include_router(router)
    return app


app = create_app(lifespan=lifespan)
