from functools import wraps
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from voxel.daq.daq import PinInfo
from voxel.daq.tasks.wavegen import WaveGenChannel, WaveGenTask
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voxel.daq.daq import VoxelDaq, VoxelDaqTask


def handle_exceptions(endpoint_function):
    @wraps(endpoint_function)
    async def wrapper(*args, **kwargs):
        try:
            return await endpoint_function(*args, **kwargs)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except KeyError as ke:
            raise HTTPException(status_code=404, detail=str(ke))
        except Exception as e:
            # General exception handling
            raise HTTPException(status_code=500, detail=str(e))

    return wrapper


class DaqInfo(BaseModel):
    name: str
    model: str
    tasks: list[str]
    pins: dict[str, PinInfo]
    assigned: list[str]


class DaqRouter(APIRouter):
    def __init__(self, daq: "VoxelDaq"):
        super().__init__(prefix="/daq")
        self.daq = daq

        @self.get("/")
        async def get_daq_info() -> DaqInfo:
            return DaqInfo(
                name=self.daq.name,
                model=self.daq.model,
                tasks=list(self.daq.tasks.keys()),
                pins=self.daq.channel_map,
                assigned=list(self.daq.assigned_channels),
            )

        for task in self.daq.tasks.values():
            if isinstance(task, WaveGenTask):
                self.include_router(router=WaveGenTaskRouter(task=task), tags=["daq"])
            else:
                self.include_router(router=DaqTaskRouter(task=task), tags=["daq"])


class DaqTaskInfo(BaseModel):
    name: str
    pins: list["PinInfo"]


class DaqTaskRouter(APIRouter):
    def __init__(self, task: "VoxelDaqTask"):
        super().__init__(prefix=f"/{task.name}")
        self.task = task

        @self.get("/")
        async def get_task_info() -> DaqTaskInfo:
            return DaqTaskInfo(name=self.task.name, pins=self.task.pins)

        @self.put("/start")
        @handle_exceptions
        async def start_wavegen():
            self.task.start()

        @self.put("/stop")
        @handle_exceptions
        async def stop_wavegen():
            self.task.stop()


class WaveGenTaskRouter(DaqTaskRouter):
    def __init__(self, task: WaveGenTask):
        self.task = task
        super().__init__(task)

        @self.get("/channels")
        @handle_exceptions
        async def get_channel_names() -> list[str]:
            return list(self.task.channels.keys())

        @self.get("/period")
        @handle_exceptions
        async def get_period() -> float:
            return self.task.period_ms

        @self.put("/period")
        @handle_exceptions
        async def set_period(period: float):
            self.task.period_ms = period

        @self.get("/sampling_rate")
        @handle_exceptions
        async def get_sampling_rate() -> float:
            return self.task.sampling_rate

        @self.put("/sampling_rate")
        @handle_exceptions
        async def set_sampling_rate(sampling_rate: float):
            self.task.sampling_rate = sampling_rate

        @self.put("/write")
        @handle_exceptions
        async def write_waveforms():
            self.task.write()

        for channel in self.task.channels.values():
            self.include_router(router=WaveGenChannelRouter(channel=channel), tags=["daq"])


class TrapezoidalWaveAnchorsModel(BaseModel):
    rise: float | None = None
    high: float | None = None
    fall: float | None = None
    low: float | None = None


class WaveGenChannelRouter(APIRouter):
    def __init__(self, channel: WaveGenChannel):
        super().__init__(prefix=f"/{channel.task.name}/{channel.name}")
        self.channel = channel

        @self.get("/")
        async def get_channel_info():
            return {
                "name": self.channel.name,
                "task": self.channel.task.name,
                "peak": self.channel.peak_voltage,
                "trough": self.channel.trough_voltage,
                "amplitude": self.channel.amplitude,
                "apply_filter": self.channel.apply_filter,
                "anchors": self.channel.anchors,
                "waveform": list(self.channel.get_downsampled_waveform()),
            }

        @self.put("/anchors")
        @handle_exceptions
        async def set_anchors(anchors: TrapezoidalWaveAnchorsModel):
            self.channel.update_anchors(**anchors.model_dump())
            return self.channel.anchors
