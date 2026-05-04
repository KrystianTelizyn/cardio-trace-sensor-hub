from fastapi import Request
from app.exceptions import HubNotReadyError
from app.sensor_hub import SensorHub


def get_sensor_hub(request: Request) -> SensorHub:
    sensor_hub = getattr(request.app.state, "sensor_hub", None)
    if sensor_hub is None:
        raise HubNotReadyError(checks={"sensor_hub": False})
    return sensor_hub
