"""FastAPI dependencies for the app and active instrument."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from vxl.app import VoxelApp
from vxl.instrument import Instrument


def get_app(request: Request) -> VoxelApp:
    return request.app.state.voxel_app


def get_instrument(request: Request) -> Instrument:
    """The launched instrument, or 404 if none is active."""
    instrument = get_app(request).active.value
    if instrument is None:
        raise HTTPException(status_code=404, detail="No instrument is launched")
    return instrument


AppDep = Annotated[VoxelApp, Depends(get_app)]
InstrumentDep = Annotated[Instrument, Depends(get_instrument)]
