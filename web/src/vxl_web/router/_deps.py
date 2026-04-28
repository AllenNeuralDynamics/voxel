from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from vxl_web.service import AppService
from vxl_web.wire import MsgBus


def _app(connection: HTTPConnection) -> AppService:
    return connection.app.state.app_service


def _bus(app: Annotated[AppService, Depends(_app)]) -> MsgBus:
    return app.bus


AppDep = Annotated[AppService, Depends(_app)]
BusDep = Annotated[MsgBus, Depends(_bus)]

__all__ = ["AppDep", "BusDep"]
