"""FastAPI dependencies for the app, log buffer, and active instrument."""

from collections import deque
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from vxl.app import VoxelApp
from vxl.instrument import Instrument

from .adapter import LogMessage


def get_app(request: Request) -> VoxelApp:
    return request.app.state.voxel_app


def get_log_buffer(request: Request) -> deque[LogMessage]:
    return request.app.state.log_buffer


def get_instrument(request: Request) -> Instrument:
    """The launched instrument, or 404 if none is active."""
    instrument = get_app(request).active.value
    if instrument is None:
        raise HTTPException(status_code=404, detail="No instrument is launched")
    return instrument


AppDep = Annotated[VoxelApp, Depends(get_app)]
LogBufferDep = Annotated[deque[LogMessage], Depends(get_log_buffer)]
InstrumentDep = Annotated[Instrument, Depends(get_instrument)]
