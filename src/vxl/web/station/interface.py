"""The instrument interface as the web layer gives it: each operation with the HTTP route that reaches it."""

from typing import Any, Literal, Self

from pydantic import BaseModel
from rigup.interface import OperationInfo
from vxlib.schema import FrozenModel

from vxl.instrument.config import InstrumentId
from vxl.instrument.interface import InstrumentInterface, in_state


class HttpOperationInfo(OperationInfo):
    """An operation with how a client reaches it over HTTP: the method, and the path under the instrument's routes. A
    ``{name}`` in the path is the argument ``name``."""

    method: Literal["GET", "POST", "PATCH", "DELETE"]
    path: str

    @classmethod
    def of(cls, info: OperationInfo, state: type[BaseModel]) -> Self:
        """``info`` with its route. Standard intents follow Google AIP-133 to 135: create is ``POST`` on the
        collection, update ``PATCH``, delete ``DELETE``. Others are custom methods (AIP-136) at ``<target>:<verb>``:
        ``GET`` for a query, ``POST`` for an action or a failsafe. A target in ``state`` goes under ``/state``; another
        target, such as ``preview``, is a noun of its own, and ``instrument`` when the operation names none."""
        target = info.resource or "instrument"
        base = f"/state/{target.replace('.', '/')}" if in_state(state, target) else f"/{target}"
        item = f"{base}/{{{info.key}}}" if info.key and info.intent != "create" else base
        verb = info.verb or info.name
        method: Literal["GET", "POST", "PATCH", "DELETE"]
        match info.intent:
            case "create":
                method, path = "POST", base
            case "update":
                method, path = "PATCH", item
            case "delete":
                method, path = "DELETE", item
            case "query":
                method, path = "GET", f"{item}:{verb}"
            case "action" | "failsafe":
                method, path = "POST", f"{item}:{verb}"
        return cls(**info.model_dump(), method=method, path=path)


class HttpInstrumentInterface(FrozenModel):
    """An :class:`InstrumentInterface` with the HTTP route of each operation. No 2 operations share a route."""

    id: InstrumentId
    kind: str
    operations: dict[str, HttpOperationInfo]
    view: dict[str, Any]

    @classmethod
    def of(cls, interface: InstrumentInterface, state: type[BaseModel]) -> Self:
        """``interface`` with its routes, for a kind whose state model is ``state``. Raise ``TypeError`` when 2
        operations make 1 route."""
        operations = {name: HttpOperationInfo.of(info, state) for name, info in interface.operations.items()}
        taken: dict[tuple[str, str], str] = {}
        for name, operation in operations.items():
            route = (operation.method, operation.path)
            if route in taken:
                raise TypeError(f"{interface.kind}.{name} and .{taken[route]} both make {route[0]} {route[1]}")
            taken[route] = name
        return cls(**interface.model_dump(exclude={"operations"}), operations=operations)


__all__ = ["HttpInstrumentInterface", "HttpOperationInfo"]
