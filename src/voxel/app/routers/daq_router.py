from functools import wraps
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from voxel.daq.daq import PinInfo
from nidaqmx.constants import Level
from typing import TYPE_CHECKING
from voxel.daq.tasks.clockgen import ClockGenTask
from voxel.daq.tasks.wavegen import WaveGenTask
from voxel.utils.descriptors.deliminated import DeliminatedFloat

if TYPE_CHECKING:
    from voxel.daq.daq import VoxelDaq, VoxelDaqTask
    from voxel.daq.tasks.wavegen import WaveGenChannel


def handle_exceptions(endpoint_function):
    @wraps(endpoint_function)
    async def wrapper(*args, **kwargs):
        try:
            return await endpoint_function(*args, **kwargs)
        except ValueError as ve:
            print(f"ValueError: {ve}")
            raise HTTPException(status_code=400, detail=str(ve))
        except KeyError as ke:
            print(f"KeyError: {ke}")
            raise HTTPException(status_code=404, detail=str(ke))
        except Exception as e:
            print(f"Exception: {e}")
            # General exception handling
            raise HTTPException(status_code=500, detail=str(e))

    return wrapper


class DeliminatedFloatModel(BaseModel):
    value: float
    min: float | None = None
    max: float | None = None
    step: float | None = None


def get_deliminated_float_model(prop: DeliminatedFloat) -> DeliminatedFloatModel:
    return DeliminatedFloatModel(
        value=float(prop),
        min=prop.min_value,
        max=prop.max_value,
        step=prop.step,
    )


class WebSocketManager:
    def __init__(self):
        self.clients: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.clients.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        self.clients.remove(websocket)

    async def broadcast(self, message: dict):
        for client in self.clients:
            try:
                await client.send_json(message)
            except WebSocketDisconnect:
                self.clients.remove(client)

    async def shutdown(self):
        for client in self.clients:
            await client.close()


class DaqInfo(BaseModel):
    name: str
    model: str
    tasks: list[str]
    pins: dict[str, PinInfo]
    assigned: list[str]


class DaqRouter(APIRouter):
    def __init__(self, daq: "VoxelDaq"):
        super().__init__(prefix="/daq", tags=["daq"])
        self.daq = daq
        self.connections = WebSocketManager()

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
                self.include_router(router=WaveGenTaskRouter(task=task))
            elif isinstance(task, ClockGenTask):
                self.include_router(router=ClockGenTaskRouter(task=task))
            else:
                self.include_router(router=DaqTaskRouter(task=task))


class DaqTaskInfo(BaseModel):
    name: str
    pins: dict[str, "PinInfo"]
    properties: list[str] = []
    actions: list[str] = []


class DaqTaskRouter(APIRouter):
    def __init__(self, task: "VoxelDaqTask"):
        super().__init__(prefix=f"/{task.name}", tags=[task.name])
        self.task = task
        self.clients = WebSocketManager()

        @self.get("/")
        async def get_task_info() -> DaqTaskInfo:
            return DaqTaskInfo(name=self.task.name, pins=self.task.pins)

        @self.put("/restart")
        @handle_exceptions
        async def restart_task():
            self.task.stop()
            self.task.start()

        @self.put("/start")
        @handle_exceptions
        async def start_wavegen():
            self.task.start()

        @self.put("/stop")
        @handle_exceptions
        async def stop_wavegen():
            self.task.stop()

    @property
    def actions(self) -> list[str]:
        return ["start", "stop", "restart"]

    def _get_task_info(self) -> DaqTaskInfo:
        return DaqTaskInfo(
            name=self.task.name,
            pins=self.task.pins,
            properties=[],
            actions=self.actions,
        )


class WaveGenChannelInfo(BaseModel):
    name: str
    task: str
    period: float
    sample_rate: float
    peak: float
    trough: float
    amplitude: float
    cutoff: float
    filter_order: int
    anchors: list[float]
    waveform: list[float]


class WaveInfo(BaseModel):
    name: str
    peak: DeliminatedFloatModel
    trough: DeliminatedFloatModel
    cutoff: DeliminatedFloatModel
    filterOrder: int
    waveform: list[float]
    anchors: list[float]


class WaveGenTaskInfo(DaqTaskInfo):
    period: float
    sampleRate: float


class WaveGenTaskRouter(DaqTaskRouter):
    def __init__(self, task: "WaveGenTask"):
        self.task = task
        super().__init__(task)

        # remove the previous root endpoint
        self.routes.pop(0)

        @self.get("/")
        async def get_wavegen_task_info() -> WaveGenTaskInfo:
            return self._get_task_info()

        @self.websocket("/")
        async def task_endpoint(websocket: WebSocket):
            await self.clients.connect(websocket)
            try:
                while True:
                    msg = await websocket.receive_json()
                    self.task.log.info(f"Received message: {msg}")
            except WebSocketDisconnect:
                await self.clients.disconnect(websocket)
            except Exception as e:
                self.task.log.warning(f"Error in websocket: {e}")
                await self.clients.disconnect(websocket)

        @self.on_event("shutdown")
        async def shutdown():
            await self.clients.shutdown()

        @self.put("/write")
        @handle_exceptions
        async def write_waveforms():
            self.task.write()

        # Universal properties

        @self.get("/period")
        @handle_exceptions
        async def get_period() -> float:
            return self.task.period_ms

        @self.put("/period")
        @handle_exceptions
        async def set_period(value: float):
            self.task.period_ms = value
            await self.broadcastTaskProperty(name="period", value=self.task.period_ms)
            await self.broadcastWaves()

        @self.get("/sample-rate")
        @handle_exceptions
        async def get_sampling_rate() -> float:
            return self.task.sample_rate

        @self.put("/sample-rate")
        @handle_exceptions
        async def set_sampling_rate(value: float):
            self.task.sample_rate = value
            await self.broadcastTaskProperty(name="sampleRate", value=self.task.sample_rate)
            await self.broadcastWaves()

        # Channel properties

        @self.get("/wave/{name}")
        @handle_exceptions
        async def get_wave_info(name: str) -> WaveInfo:
            return self._get_wave_info(self.task.channels[name])

        @self.put("/wave/{name}/anchors")
        @handle_exceptions
        async def set_wave_anchors(name: str, value: list[float]):
            self.task.channels[name].anchors = value
            await self.broadcastWaves(names=[name])

        @self.put("/wave/{name}/peak")
        @handle_exceptions
        async def set_wave_peak(name: str, value: float):
            self.task.channels[name].peak_voltage = value
            await self.broadcastWaves(names=[name])

        @self.put("/wave/{name}/trough")
        @handle_exceptions
        async def set_wave_trough(name: str, value: float):
            self.task.channels[name].trough_voltage = value
            await self.broadcastWaves(names=[name])

        @self.put("/wave/{name}/cutoff")
        @handle_exceptions
        async def set_wave_cutoff(name: str, value: float):
            self.task.channels[name].lowpass_cutoff = value
            await self.broadcastWaves(names=[name])

        @self.put("/wave/{name}/filter-order")
        @handle_exceptions
        async def set_wave_filter_order(name: str, value: int):
            self.task.channels[name].lowpass_filter_order = value
            await self.broadcastWaves(names=[name])

    async def broadcastTaskProperty(self, name: str, value: float):
        await self.clients.broadcast({"type": "properties", "data": {name: value}})

    async def broadcastWaves(self, names: list[str] | None = None):
        names = names or list(self.task.channels.keys())
        await self.clients.broadcast(
            {
                "type": "waves",
                "data": [self._get_wave_info(channel=self.task.channels[name]).model_dump_json() for name in names],
            }
        )

    @property
    def actions(self) -> list[str]:
        return super().actions + ["write"]

    def _get_task_info(self) -> WaveGenTaskInfo:
        self.task.log.info("Getting wavegen task info")
        return WaveGenTaskInfo(
            name=self.task.name,
            pins=self.task.pins,
            period=self.task.period_ms,
            sampleRate=self.task.sample_rate,
            actions=self.actions,
        )

    def _get_wave_info(self, channel: "WaveGenChannel") -> WaveInfo:
        channel.regenerate_waveform()
        data = channel.get_downsampled_waveform(num_samples=int(self.task.period_ms))
        self.task.log.warning(f"Channel {channel.name} waveform length: {len(data)}")
        return WaveInfo(
            name=channel.name,
            peak=get_deliminated_float_model(channel.peak_voltage),
            trough=get_deliminated_float_model(channel.trough_voltage),
            cutoff=get_deliminated_float_model(channel.lowpass_cutoff),
            filterOrder=channel.lowpass_filter_order,
            waveform=list(data),
            anchors=channel.anchors,
        )


class ClockGenTaskInfo(BaseModel):
    name: str
    out_pin: PinInfo
    src_pin: PinInfo | None = None
    gate_pin: PinInfo | None = None
    aux_pin: PinInfo | None = None
    period: float
    freq_hz: float
    duty_cycle: float
    initial_delay_ms: float
    idle_state: bool


class ClockGenTaskRouter(DaqTaskRouter):
    def __init__(self, task: "ClockGenTask"):
        self.task = task
        super().__init__(task=task)

        @self.get("/")
        async def get_clockgen_task_info() -> ClockGenTaskInfo:
            return self._get_clockgen_task_info()

        @self.put("/freq-hz")
        @handle_exceptions
        async def set_freq_hz(freq: float) -> ClockGenTaskInfo:
            return self._set_freq_hz(freq)

        @self.put("/period-ms")
        @handle_exceptions
        async def set_period_ms(period: float) -> ClockGenTaskInfo:
            return self._set_freq_hz(1e3 / period)

        @self.put("/duty-cycle")
        @handle_exceptions
        async def set_duty_cycle(duty: float) -> ClockGenTaskInfo:
            self.task.duty_cycle = duty
            return self._get_clockgen_task_info()

        @self.put("/initial-delay-ms")
        @handle_exceptions
        async def set_initial_delay_ms(delay: float) -> ClockGenTaskInfo:
            self.task.initial_delay_ms = delay
            return self._get_clockgen_task_info()

        @self.put("/idle-state")
        @handle_exceptions
        async def set_idle_state(state: bool):
            self.task.idle_state = state

    def _set_freq_hz(self, freq: float) -> ClockGenTaskInfo:
        self.task.freq_hz = freq
        return self._get_clockgen_task_info()

    def _get_clockgen_task_info(self) -> ClockGenTaskInfo:
        return ClockGenTaskInfo(
            name=self.task.name,
            out_pin=self.task.out,
            src_pin=self.task._src,
            gate_pin=self.task._gate,
            aux_pin=self.task._aux,
            freq_hz=self.task.freq_hz,
            period=self.task.period_ms,
            duty_cycle=self.task.duty_cycle,
            initial_delay_ms=self.task.initial_delay_ms,
            idle_state=self.task.idle_state == Level.HIGH,
        )
