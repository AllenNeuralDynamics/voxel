import asyncio
from fastapi import APIRouter, WebSocket
from voxel.devices.base import VoxelDevice, VoxelDeviceModel, VoxelPropertyDetails
from pydantic import BaseModel
from typing import Any


class DeviceUpdateRequest(BaseModel):
    properties: dict[str, Any]


class BaseMessage(BaseModel):
    type: str
    request_id: str | None = None


class CommandMessage(BaseMessage):
    type: str = "command"
    command: str
    params: dict[str, Any] = {}


class EventMessage(BaseMessage):
    type: str = "event"
    event: str
    data: dict[str, Any] = {}


class ErrorMessage(BaseMessage):
    type: str = "error"
    message: str


class DeviceRouter(APIRouter):
    def __init__(self, device: VoxelDevice):
        super().__init__(prefix=f"/{device.name}")
        self.device = device
        self.signals_interval = 1

        @self.get("/")
        async def get_device_info() -> VoxelDeviceModel:
            return self.device.snapshot

        @self.put("/")
        async def update_device_properties(request: DeviceUpdateRequest) -> VoxelDeviceModel:
            for prop_name, prop_value in request.properties.items():
                if self.device.properties[prop_name].setter is not None:
                    setattr(self.device, prop_name, prop_value)
            return self.device.snapshot

        @self.get("/details")
        async def get_device_property_details() -> dict[str, VoxelPropertyDetails]:
            return self.device._details

        @self.websocket("/signals")
        async def signals_endpoint(websocket: WebSocket):
            await websocket.accept()
            self.device.log.info("Router accepted signals websocket connection")
            while True:
                await websocket.send_json(device.get_signals())
                await asyncio.sleep(self.signals_interval)


class CameraRouter(DeviceRouter):
    def __init__(self, device: VoxelDevice):
        super().__init__(device)
        self.streaming = False

        @self.websocket("/livestream")
        async def livestream(websocket: WebSocket):
            await websocket.accept()
            print("Accepted livestream connection")
            while True:
                data = await websocket.receive_json()
                print(f"Received data: {data}")
                await websocket.send_json({"message": "Hello World"})
