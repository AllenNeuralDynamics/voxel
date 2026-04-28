from typing import Annotated

from fastapi import Depends, HTTPException

from vxl_web.router._deps import AppDep, BusDep, _app
from vxl_web.service import AppService
from vxl_web.service.session import DevicesService, SessionService


def _session(app: Annotated[AppService, Depends(_app)]) -> SessionService:
    if app.session_service is None:
        raise HTTPException(status_code=503, detail="No active session")
    return app.session_service


def _devices(svc: Annotated[SessionService, Depends(_session)]) -> DevicesService:
    return svc.devices


SessionDep = Annotated[SessionService, Depends(_session)]
DevicesDep = Annotated[DevicesService, Depends(_devices)]

__all__ = ["AppDep", "BusDep", "DevicesDep", "SessionDep"]
