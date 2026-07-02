"""FastAPI dependencies: the app-scoped ``VoxelApp`` + ``MsgBus`` + log buffer, and the active ``Instrument``."""

from collections import deque
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from vxl.app import VoxelApp
from vxl.instrument import Instrument

from .live import LogMessage
from .wire import MsgBus


def get_app(request: Request) -> VoxelApp:
    return request.app.state.voxel_app


def get_bus(request: Request) -> MsgBus:
    return request.app.state.bus


def get_log_buffer(request: Request) -> deque[LogMessage]:
    return request.app.state.log_buffer


def get_instrument(request: Request) -> Instrument:
    """The launched instrument, or 404 if none is active."""
    instrument = get_app(request).active.value
    if instrument is None:
        raise HTTPException(status_code=404, detail="No instrument is launched")
    return instrument


AppDep = Annotated[VoxelApp, Depends(get_app)]
BusDep = Annotated[MsgBus, Depends(get_bus)]
LogBufferDep = Annotated[deque[LogMessage], Depends(get_log_buffer)]
InstrumentDep = Annotated[Instrument, Depends(get_instrument)]
