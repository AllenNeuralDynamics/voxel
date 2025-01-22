from fastapi import APIRouter
from pydantic import BaseModel

from voxel.devices.base import VoxelDeviceType
from voxel.instrument import VoxelInstrument
from voxel.server.device_router import DeviceRouter
from voxel.server.daq_router import DaqRouter


class ChannelInfo(BaseModel):
    name: str
    camera: str
    lens: str
    laser: str
    filter: str


class InstrumentDevices(BaseModel):
    cameras: list[str]
    lenses: list[str]
    lasers: list[str]
    filters: list[str]
    axes: list[str]
    others: list[str]


class InstrumentInfo(BaseModel):
    name: str
    devices: InstrumentDevices
    channels: list[ChannelInfo]
    daq_tasks: list[str]


class InstrumentRouter(APIRouter):
    def __init__(self, instrument: VoxelInstrument):
        super().__init__(prefix="/instrument")
        self.instrument = instrument

        @self.get("/")
        async def get_instrument_info():
            return InstrumentInfo(
                name=instrument.name,
                devices=self._get_device_names(),
                channels=self._get_channel_info(),
                daq_tasks=list(instrument.daq.tasks.keys()) if instrument.daq else [],
            )

        for device in instrument.devices.values():
            self.include_router(router=DeviceRouter(device=device), tags=["device"])

        if instrument.daq:
            self.include_router(router=DaqRouter(daq=instrument.daq), tags=["daq"])

    def _get_device_names(self) -> InstrumentDevices:
        cameras = list(self.instrument.cameras.keys())
        lenses = list(self.instrument.lenses.keys())
        lasers = list(self.instrument.lasers.keys())
        filters = list(self.instrument.filters.keys())
        axes = [
            name
            for name, device in self.instrument.devices.items()
            if device.device_type == (VoxelDeviceType.LINEAR_AXIS or VoxelDeviceType.ROTATION_AXIS)
        ]
        others = [name for name in self.instrument.devices if name not in cameras + lenses + lasers + filters + axes]
        return InstrumentDevices(
            cameras=cameras, lenses=lenses, lasers=lasers, filters=filters, axes=axes, others=others
        )

    def _get_channel_info(self) -> list[ChannelInfo]:
        channels = []
        for channel in self.instrument.channels.values():
            channels.append(
                {
                    "name": channel.name,
                    "camera": channel.camera.name,
                    "lens": channel.lens.name,
                    "laser": channel.laser.name,
                    "filter": channel.emmision_filter.name,
                }
            )
        return channels
