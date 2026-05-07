from __future__ import annotations

from app.models import CardioTraceContext
from app.parsers import parse_frame
from app.pipeline_steps.base import DEVICE_DISCOVERY_STEP, PipelineStep


class DeviceDiscoveryStep(PipelineStep):
    name = DEVICE_DISCOVERY_STEP

    async def run(self, context: CardioTraceContext) -> None:
        parsed_frame = parse_frame(context.raw)
        context.serial_number = parsed_frame.serial_number
        context.brand = parsed_frame.brand
        context.timestamp = parsed_frame.timestamp
        context.heart_rate = parsed_frame.heart_rate
        context.sdnn = parsed_frame.sdnn
        context.rmssd = parsed_frame.rmssd
