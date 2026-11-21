"""The HTTP routes of an open instrument, made from the operations that its kind declares.

The routes are as ``vxl.instrument.interface`` names them, and each runs through ``Instrument.execute``. Standard
intents follow Google AIP-133 to 135 and RFC 9110: create is ``POST`` on the collection and answers ``201`` with the
item and a ``Location``; update is ``PATCH`` and answers the changed item; delete is ``DELETE`` and answers ``204``.
Other intents are custom methods (AIP-136) at ``<target>:<name>``: ``GET`` for a query, ``POST`` for an action or a
failsafe, answering ``204`` when the method returns nothing. Reads of the state are ``GET``s of the view; only a
collection has item reads (AIP-156). Keys never contain ``/`` or ``:``, so an item path and a custom method on it never
match each other.

Every read and every answer that holds an item carries an ``ETag``: a hash of that item, so an edit to 1 item leaves
the tags of the others valid. ``If-Match`` on an update or a delete refuses the change with ``412`` when the item has
changed since (RFC 9110 §13.1.1); without ``If-Match`` the change applies. ``If-None-Match`` on a read answers ``304``
when nothing changed.

Errors follow RFC 9457 (:class:`vxl.web.problems.ProblemDetails`): ``400`` for a body that is not a JSON object,
``404`` for an unknown item or device, ``409`` when the instrument or a part of it is busy, ``412`` when ``If-Match``
names an old version, ``422`` for arguments or edits it refuses, ``500`` for anything else.
"""

import contextlib
import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from http import HTTPStatus
from typing import Any, ClassVar, NoReturn

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from pydantic_core import to_jsonable_python
from rigup.activity import ActivityBusyError
from rigup.interface import OperationInfo
from starlette.convertors import Convertor, register_url_convertor
from starlette.exceptions import HTTPException
from vxlib.schema import key_field

from vxl.instrument.base import Instrument
from vxl.instrument.interface import Target, in_state, route_of, target_of
from vxl.station.errors import BusyError, NotFoundError, VoxelError
from vxl.web.problems import ProblemDetails, Statuses

type Lease = Callable[[], AbstractAsyncContextManager[Instrument[Any, Any, Any]]]
"""Gives the instrument for the time of 1 operation."""

type Endpoint = Callable[[Request], Awaitable[Response]]


class _KeyConvertor(Convertor[str]):
    """A key in a path: anything but ``/`` and ``:``."""

    regex = "[^/:]+"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return value


register_url_convertor("key", _KeyConvertor())


class InstrumentRouter(APIRouter):
    """The HTTP routes of 1 open instrument: 1 for each operation of its kind, the reads of each state resource, its
    devices, ``/interface`` and ``/openapi.json``. ``lease`` gives the instrument for the time of 1 operation; without
    it, each operation uses ``instrument`` itself. The app that includes these routes answers their failures:
    ``ProblemDetails.install(app, InstrumentRouter.statuses)``."""

    statuses: ClassVar[Statuses] = {
        NotFoundError: 404,
        BusyError: 409,
        ActivityBusyError: 409,
        VoxelError: 422,
        ValidationError: 422,
        RequestValidationError: 422,
    }
    """The HTTP status of each kind of failure that an instrument or a station raises."""

    def __init__(self, instrument: Instrument[Any, Any, Any], *, lease: Lease | None = None) -> None:
        super().__init__(responses=ProblemDetails.described(), redirect_slashes=False)
        self._kind = type(instrument)
        self._view = instrument.view
        self._interface = instrument.interface
        self._lease: Lease = lease or (lambda: contextlib.nullcontext(instrument))
        self._schemas: dict[str, Any] = {}
        resources: set[str] = set()
        for info in self._kind.operations.values():
            method, path = route_of(info, self._kind.state_cls)
            if info.key is not None:  # the key convertor never takes in a ``:verb``
                path = path.replace(f"{{{info.key}}}", f"{{{info.key}:key}}")
            endpoint, extra, status = self._operation(info)
            self.add_api_route(
                path,
                endpoint,
                methods=[method],
                status_code=status,
                summary=info.label,
                description=info.desc or "",
                openapi_extra=extra,
            )
            if info.intent in ("create", "update", "delete") and info.resource:
                resources.add(info.resource)
        for resource in sorted(resources):
            self._add_reads(resource)
        self.add_api_route("/devices/{device_id:key}", self._device, methods=["GET"])
        self.add_api_route("/devices/{device_id:key}", self._set_device, methods=["PATCH"])
        self.add_api_route("/devices/{device_id:key}:{operation:key}", self._run_device, methods=["POST"])
        self.add_api_route("/interface", self._described, methods=["GET"])
        self.add_api_route("/openapi.json", self._page, methods=["GET"], include_in_schema=False)

    def _operation(self, info: OperationInfo) -> tuple[Endpoint, dict[str, Any], int]:
        """The endpoint of 1 operation, its details for the API page, and its success status."""
        state = self._kind.state_cls
        standard = info.intent in ("create", "update", "delete")
        target = target_of(state, info.resource) if standard and info.resource else None
        on_state = info.resource is not None and in_state(state, info.resource)

        async def endpoint(request: Request) -> Response:
            args = self._query(request) if info.intent == "query" else await self._body(request)
            if info.key is not None and info.intent != "create":
                key = request.path_params[info.key]
                if on_state and info.resource is not None and info.intent in ("update", "delete"):
                    self._precondition(request, self._found(info.resource, key))
                args[info.key] = key
            elif info.intent == "update" and info.resource:
                self._precondition(request, self._at(info.resource))
            async with self._lease() as instrument:
                result = await instrument.execute(info.name, args)
            return self._answer(request, info, target, args, result)

        returns_nothing = info.returns.get("type") == "null"
        status = {"create": 201, "update": 200, "delete": 204}.get(info.intent, 204 if returns_nothing else 200)
        extra: dict[str, Any] = {"operationId": info.name}
        params = self._moved(info.params)
        properties: dict[str, Any] = params.get("properties", {})
        required: list[str] = params.get("required", [])
        if info.key is not None and info.intent != "create":
            key_schema = properties.pop(info.key, {"type": "string"})
            params["required"] = [name for name in required if name != info.key]
            extra["parameters"] = [{"name": info.key, "in": "path", "required": True, "schema": key_schema}]
        if info.intent == "query":
            extra.setdefault("parameters", []).extend(
                {"name": name, "in": "query", "required": name in required, "schema": schema}
                for name, schema in properties.items()
            )
        elif properties:
            extra["requestBody"] = {"required": True, "content": {"application/json": {"schema": params}}}
        answer: dict[str, Any] = {"description": info.label}
        if status != HTTPStatus.NO_CONTENT:
            shown = target.item.model_json_schema() if target and info.intent in ("create", "update") else info.returns
            answer["content"] = {"application/json": {"schema": self._moved(shown)}}
        extra["responses"] = {str(status): answer}
        return endpoint, extra, status

    def _answer(
        self, request: Request, info: OperationInfo, target: Target | None, args: dict[str, Any], result: object
    ) -> Response:
        if info.intent == "create" and info.resource and target:
            new = next(value for name, value in args.items() if name != info.key)
            key = args[info.key] if info.key else new[key_field(target.item)]
            location = f"{request.scope.get('root_path', '')}/state/{info.resource.replace('.', '/')}/{key}"
            return self._tagged(self._item(self._at(info.resource), str(key)), 201, {"Location": location})
        if info.intent == "update" and info.resource:
            here = self._at(info.resource)
            return self._tagged(self._item(here, str(args[info.key])) if info.key else here)
        if result is None:
            return Response(status_code=204)
        return JSONResponse(self._dump(result))

    def _add_reads(self, resource: str) -> None:
        """The reads of 1 state resource: the whole of it, and each item when it is a collection."""
        path = "/state/" + resource.replace(".", "/")

        async def whole(request: Request) -> Response:
            return self._read(request, self._at(resource))

        self.add_api_route(path, whole, methods=["GET"], operation_id=f"get_{resource}")
        if target_of(self._kind.state_cls, resource).key is None:
            return

        async def one(request: Request, key: str) -> Response:
            return self._read(request, self._found(resource, key))

        self.add_api_route(path + "/{key:key}", one, methods=["GET"], operation_id=f"get_{resource}_item")

    async def _device(self, request: Request, device_id: str) -> Response:
        return self._read(request, self._known(device_id))

    async def _set_device(self, request: Request, device_id: str) -> Response:
        """Set properties of a device, through the instrument: it decides whether the device may be used now."""
        self._precondition(request, self._known(device_id))
        async with self._lease() as instrument:
            results = await instrument.set_device_properties(device_id, await self._body(request))
        if not results.is_ok:
            refused = [{"loc": [name], "result": self._dump(r)} for name, r in results.results.items() if not r.is_ok]
            detail = f"'{device_id}' refused {len(refused)} propert(ies)"
            return ProblemDetails.response(422, detail, request.url.path, refused)
        return JSONResponse(self._dump(results))

    async def _run_device(self, request: Request, device_id: str, operation: str) -> Response:
        """Run an operation of a device, through the instrument."""
        if operation not in self._known(device_id).interface.operations:
            raise HTTPException(404, f"'{device_id}' has no operation '{operation}'")
        async with self._lease() as instrument:
            result = await instrument.execute_device_command(device_id, operation, kwargs=await self._body(request))
        if not result.is_ok:
            detail = f"'{device_id}' refused '{operation}'"
            return ProblemDetails.response(422, detail, request.url.path, [self._dump(result)])
        value = result.unwrap()
        return Response(status_code=204) if value is None else JSONResponse(self._dump(value))

    async def _described(self) -> JSONResponse:
        return JSONResponse(self._interface.model_dump(mode="json"))

    async def _page(self) -> JSONResponse:
        """The API page of these routes, with the models that the operations name."""
        page = get_openapi(title=self._view.value.config.name, version="1", routes=self.routes)
        page.setdefault("components", {}).setdefault("schemas", {}).update(self._schemas)
        return JSONResponse(page)

    def _known(self, device_id: str) -> Any:
        devices = self._view.value.devices
        if device_id not in devices:
            raise HTTPException(404, f"no device '{device_id}'")
        return devices[device_id]

    def _at(self, resource: str) -> object:
        here: object = self._view.value.state
        for name in resource.split("."):
            here = getattr(here, name)
        return here

    def _found(self, resource: str, key: str) -> object:
        found = self._item(self._at(resource), key)
        if found is None:
            raise HTTPException(404, f"no '{key}' in {resource}")
        return found

    def _moved(self, written: dict[str, Any]) -> dict[str, Any]:
        """``written`` with its ``$defs`` kept for the API page and its references pointed there."""
        moved = json.loads(json.dumps(written).replace('"#/$defs/', '"#/components/schemas/'))
        self._schemas |= moved.pop("$defs", {})
        return moved

    @staticmethod
    def _item(collection: object, key: str) -> object | None:
        if isinstance(collection, Mapping):
            return collection.get(key)
        if isinstance(collection, list | tuple):
            for item in collection:
                if isinstance(item, BaseModel) and str(getattr(item, key_field(type(item)))) == key:
                    return item
        return None

    @classmethod
    def _dump(cls, value: object) -> object:
        """``value`` as JSON: a model as the feed writes it, and a plain value, such as an id or a time, as text."""
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if isinstance(value, list | tuple):
            return [cls._dump(item) for item in value]
        if isinstance(value, Mapping):
            return {str(key): cls._dump(item) for key, item in value.items()}
        return to_jsonable_python(value)

    @classmethod
    def _etag(cls, value: object) -> str:
        """A strong entity tag of ``value``: a hash of its JSON."""
        text = json.dumps(cls._dump(value), sort_keys=True, separators=(",", ":"))
        return '"' + hashlib.sha256(text.encode()).hexdigest()[:20] + '"'

    @classmethod
    def _tagged(cls, value: object, status: int = 200, headers: dict[str, str] | None = None) -> JSONResponse:
        tagged = {"ETag": cls._etag(value), **(headers or {})}
        return JSONResponse(cls._dump(value), status_code=status, headers=tagged)

    @classmethod
    def _matches(cls, header: str | None, value: object) -> bool:
        """Whether an ``If-Match`` or ``If-None-Match`` header names the current version of ``value``."""
        if header is None:
            return False
        tags = {tag.strip() for tag in header.split(",")}
        return "*" in tags or cls._etag(value) in tags or ("W/" + cls._etag(value)) in tags

    @classmethod
    def _read(cls, request: Request, value: object) -> Response:
        """``value`` with its ``ETag``, or ``304`` when ``If-None-Match`` names it."""
        if cls._matches(request.headers.get("if-none-match"), value):
            return Response(status_code=304, headers={"ETag": cls._etag(value)})
        return cls._tagged(value)

    @classmethod
    def _precondition(cls, request: Request, current: object) -> None:
        """Refuse with ``412`` when ``If-Match`` names a version other than ``current`` (RFC 9110 §13.1.1)."""
        header = request.headers.get("if-match")
        if header is not None and not cls._matches(header, current):
            raise HTTPException(412, f"changed since {header}; read it again and resend")

    @classmethod
    async def _body(cls, request: Request) -> dict[str, Any]:
        """The arguments in the body. ``NaN`` and ``Infinity`` are not JSON (RFC 8259 §6) and are refused."""
        written = await request.body()
        if not written:
            return {}
        try:
            body = json.loads(written, parse_constant=cls._not_json)
        except (ValueError, RecursionError) as error:
            raise HTTPException(400, f"the body is not JSON: {error}") from error
        if not isinstance(body, dict):
            raise HTTPException(400, "the body is a JSON object of arguments")
        return body

    @staticmethod
    def _not_json(constant: str) -> NoReturn:
        raise ValueError(f"{constant} is not a JSON value")

    @staticmethod
    def _query(request: Request) -> dict[str, Any]:
        """The query string as arguments: a name given more than once becomes a list."""
        found: dict[str, Any] = {}
        for name, value in request.query_params.multi_items():
            if name in found:
                found[name] = [*found[name], value] if isinstance(found[name], list) else [found[name], value]
            else:
                found[name] = value
        return found


__all__ = ["InstrumentRouter"]
