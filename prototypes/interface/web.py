"""Try-out of HTTP routes made from the interface of an open instrument: its declared operations, as
``vxl.instrument.interface`` checks and routes them, run through ``Instrument.execute``.

Standard intents follow Google AIP-133 to 135 and RFC 9110: create is ``POST`` on the collection and answers ``201``
with the item and a ``Location``; update is ``PATCH`` and answers the changed item; delete is ``DELETE`` and answers
``204``. Other intents are custom methods (AIP-136) at ``<target>:<name>``: ``GET`` for a query, ``POST`` for an action
or a failsafe, answering ``204`` when the method returns nothing. Reads of the state are ``GET``s of the view; only a
collection has item reads (AIP-156). Keys never contain ``/`` or ``:``, so an item path and a custom method on it
never match each other.

Errors follow RFC 9457: ``application/problem+json`` with ``type``, ``title``, ``status``, ``detail`` and ``instance``,
and an ``errors`` member listing each refused argument. ``400`` for a body that is not a JSON object, ``404`` for an
unknown item or device, ``409`` when the instrument is busy, ``412`` when ``If-Match`` names an old version, ``422`` for
arguments or edits it refuses, ``500`` for anything else.

Every read and every answer that holds an item carries an ``ETag``: a hash of that item, so an edit to 1 item leaves
the tags of the others valid. ``If-Match`` on an update or a delete refuses the change with ``412`` when the item has
changed since (RFC 9110 §13.1.1); without ``If-Match`` the change applies. ``If-None-Match`` on a read answers ``304``
when nothing changed."""

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from rigup.interface import OperationInfo
from starlette.convertors import Convertor, register_url_convertor
from starlette.exceptions import HTTPException
from vxlib.schema import key_field

from vxl.instrument.base import Instrument
from vxl.instrument.interface import Target, in_state, route_of, target_of
from vxl.station.errors import BusyError, NotFoundError, RejectedError

logger = logging.getLogger(__name__)

type Endpoint = Callable[[Request], Awaitable[Response]]

_REF = "#/components/schemas/{model}"
_PROBLEM = {"application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}}
_ERRORS = {
    code: {"description": text, "content": _PROBLEM}
    for code, text in (
        ("400", "The body is not a JSON object of arguments"),
        ("404", "No such item"),
        ("409", "The instrument is busy"),
        ("412", "The item changed since the version named in If-Match"),
        ("422", "The arguments or the edit are refused"),
    )
}
_PROBLEM_SCHEMA = {
    "type": "object",
    "description": "RFC 9457 problem details",
    "properties": {
        "type": {"type": "string", "format": "uri-reference", "default": "about:blank"},
        "title": {"type": "string"},
        "status": {"type": "integer"},
        "detail": {"type": "string"},
        "instance": {"type": "string", "format": "uri-reference"},
        "errors": {"type": "array", "items": {"type": "object"}},
    },
}


def problem(status: int, detail: str, instance: str, errors: list[Any] | None = None) -> JSONResponse:
    """An RFC 9457 problem answer. ``errors`` lists the refused arguments, each with its ``loc`` and ``msg``."""
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "detail": detail,
        "instance": instance,
    }
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def etag(value: object) -> str:
    """A strong entity tag of ``value``: a hash of its JSON."""
    text = json.dumps(_dump(value), sort_keys=True, separators=(",", ":"))
    return '"' + hashlib.sha256(text.encode()).hexdigest()[:20] + '"'


def _tagged(value: object, status: int = 200, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(_dump(value), status_code=status, headers={"ETag": etag(value), **(headers or {})})


def _matches(header: str | None, value: object) -> bool:
    """Whether an ``If-Match`` or ``If-None-Match`` header names the current version of ``value``."""
    if header is None:
        return False
    tags = {tag.strip() for tag in header.split(",")}
    return "*" in tags or etag(value) in tags or ("W/" + etag(value)) in tags


class _KeyConvertor(Convertor[str]):
    """A key in a path: anything but ``/`` and ``:``."""

    regex = "[^/:]+"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return value


register_url_convertor("key", _KeyConvertor())


class _RefusedError(Exception):
    """An answer other than success, raised inside an endpoint."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


def _dump(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list | tuple):
        return [_dump(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _dump(item) for key, item in value.items()}
    return value


def _state_at(instrument: Instrument[Any, Any, Any], path: str) -> object:
    here: object = instrument.view.value.state
    for name in path.split("."):
        here = getattr(here, name)
    return here


def _item(collection: object, key: str) -> object | None:
    if isinstance(collection, Mapping):
        return collection.get(key)
    if isinstance(collection, list):
        for item in collection:
            if isinstance(item, BaseModel) and str(getattr(item, key_field(type(item)))) == key:
                return item
    return None


def _guarded(handler: Endpoint) -> Endpoint:
    """Answer every refusal and failure of ``handler`` as ``{"detail": ...}`` with its status."""

    async def endpoint(request: Request) -> Response:
        where = request.url.path
        try:
            return await handler(request)
        except _RefusedError as refused:
            return problem(refused.status, refused.detail, where)
        except ValidationError as error:
            found = error.errors(include_url=False, include_context=False, include_input=False)
            return problem(422, f"{len(found)} argument(s) refused", where, list(found))
        except NotFoundError as error:
            return problem(404, str(error), where)
        except RejectedError as error:
            return problem(422, str(error), where)
        except BusyError as error:
            return problem(409, str(error), where)
        except Exception:
            logger.exception("%s %s failed", request.method, where)
            return problem(500, "the instrument failed; see the station log", where)

    return endpoint


async def _body(request: Request) -> dict[str, Any]:
    if not await request.body():
        return {}
    try:
        body = await request.json()
    except json.JSONDecodeError as error:
        raise _RefusedError(400, f"the body is not JSON: {error.msg}") from error
    if not isinstance(body, dict):
        raise _RefusedError(400, "the body is a JSON object of arguments")
    return body


def _read(request: Request, value: object) -> Response:
    """``value`` with its ``ETag``, or ``304`` when ``If-None-Match`` names it."""
    if _matches(request.headers.get("if-none-match"), value):
        return Response(status_code=304, headers={"ETag": etag(value)})
    return _tagged(value)


def _query(request: Request) -> dict[str, Any]:
    """The query string as arguments: a name given more than once becomes a list."""
    found: dict[str, Any] = {}
    for name, value in request.query_params.multi_items():
        if name in found:
            found[name] = [*found[name], value] if isinstance(found[name], list) else [found[name], value]
        else:
            found[name] = value
    return found


def route_table(instrument: Instrument[Any, Any, Any]) -> dict[tuple[str, str], OperationInfo]:
    """The HTTP method and path of each operation, as ``vxl`` names them. Each key in a path takes the ``key``
    convertor, so it never takes in a ``:verb``."""
    state = type(instrument).state_cls
    found: dict[tuple[str, str], OperationInfo] = {}
    for info in type(instrument).operations.values():
        method, path = route_of(info, state)
        if info.key is not None:
            path = path.replace(f"{{{info.key}}}", f"{{{info.key}:key}}")
        found[method, path] = info
    return found


def _schema(written: dict[str, Any], schemas: dict[str, Any]) -> dict[str, Any]:
    """``written`` with its ``$defs`` moved to the document's components and its references pointed there."""
    moved = json.loads(json.dumps(written).replace('"#/$defs/', '"#/components/schemas/'))
    schemas |= moved.pop("$defs", {})
    return moved


class _Routes:
    """Builds the routes of 1 instrument."""

    def __init__(self, instrument: Instrument[Any, Any, Any]) -> None:
        self.instrument = instrument
        self.state = type(instrument).state_cls
        self.schemas: dict[str, Any] = {}

    def collect(self, made: dict[str, Any]) -> dict[str, Any]:
        """``made`` with its models moved to the document's components."""
        self.schemas |= made.pop("$defs", {})
        return made

    def operation(self, info: OperationInfo) -> tuple[Endpoint, dict[str, Any], int]:
        """The endpoint of 1 operation, its OpenAPI details, and its success status."""
        standard = info.intent in ("create", "update", "delete")
        target = target_of(self.state, info.resource) if standard and info.resource else None
        on_state = info.resource is not None and in_state(self.state, info.resource)
        returns_nothing = info.returns.get("type") == "null"

        async def handler(request: Request) -> Response:
            args = _query(request) if info.intent == "query" else await _body(request)
            if info.key is not None and info.intent != "create":
                key = request.path_params[info.key]
                if on_state and info.resource is not None:
                    found = _item(_state_at(self.instrument, info.resource), key)
                    if found is None:
                        raise _RefusedError(404, f"no '{key}' in {info.resource}")
                    if info.intent in ("update", "delete"):
                        self.precondition(request, found)
                args[info.key] = key
            elif info.intent == "update" and info.resource:
                self.precondition(request, _state_at(self.instrument, info.resource))
            result = await self.instrument.execute(info.name, args)
            return self.answer(info, target, args, result)

        status = {"create": 201, "update": 200, "delete": 204}.get(info.intent, 204 if returns_nothing else 200)
        extra: dict[str, Any] = {"operationId": info.name}
        params = _schema(info.params, self.schemas)
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
        if status != 204:
            if target and info.intent in ("create", "update"):
                shown = _schema(target.item.model_json_schema(), self.schemas)
            else:
                shown = _schema(info.returns, self.schemas)
            answer["content"] = {"application/json": {"schema": shown}}
        extra["responses"] = {str(status): answer, **_ERRORS}
        return _guarded(handler), extra, status

    @staticmethod
    def precondition(request: Request, current: object) -> None:
        """Refuse with ``412`` when ``If-Match`` names a version other than ``current`` (RFC 9110 §13.1.1)."""
        header = request.headers.get("if-match")
        if header is not None and not _matches(header, current):
            raise _RefusedError(412, f"changed since {header}; read it again and resend")

    def answer(self, info: OperationInfo, target: Target | None, args: dict[str, Any], result: Any) -> Response:
        if info.intent == "create" and info.resource and target:
            new = next(value for name, value in args.items() if name != info.key)
            key = args[info.key] if info.key else new[key_field(target.item)]
            found = _item(_state_at(self.instrument, info.resource), str(key))
            location = f"/state/{info.resource.replace('.', '/')}/{key}"
            return _tagged(found, 201, {"Location": location})
        if info.intent == "update" and info.resource:
            here = _state_at(self.instrument, info.resource)
            return _tagged(_item(here, str(args[info.key])) if info.key else here)
        if result is None:
            return Response(status_code=204)
        return JSONResponse(_dump(result))

    def reads(self, app: FastAPI, resource: str) -> None:
        path = "/state/" + resource.replace(".", "/")
        target = target_of(self.state, resource)

        async def whole(request: Request) -> Response:
            return _read(request, _state_at(self.instrument, resource))

        app.add_api_route(path, _guarded(whole), methods=["GET"], operation_id=f"get_{resource}")
        if target.key is None:
            return

        async def one(request: Request) -> Response:
            found = _item(_state_at(self.instrument, resource), request.path_params["key"])
            if found is None:
                raise _RefusedError(404, f"no '{request.path_params['key']}' in {resource}")
            return _read(request, found)

        key = {"name": "key", "in": "path", "required": True, "schema": {"type": "string"}}
        app.add_api_route(
            path + "/{key:key}",
            _guarded(one),
            methods=["GET"],
            operation_id=f"get_{resource}_item",
            openapi_extra={"parameters": [key], "responses": {"404": _ERRORS["404"]}},
        )

    def devices(self, app: FastAPI) -> None:
        """Device routes, each through the instrument: it decides whether a device may be used now."""
        instrument = self.instrument

        def known(device_id: str) -> None:
            if device_id not in instrument.view.value.devices:
                raise _RefusedError(404, f"no device '{device_id}'")

        async def read(request: Request) -> Response:
            known(device_id := request.path_params["id"])
            return _read(request, instrument.view.value.devices[device_id])

        async def write(request: Request) -> Response:
            known(device_id := request.path_params["id"])
            results = await instrument.set_device_properties(device_id, await _body(request))
            if not results.is_ok:
                refused = [{"loc": [name], "result": _dump(r)} for name, r in results.results.items() if not r.is_ok]
                return problem(422, f"'{device_id}' refused {len(refused)} propert(ies)", request.url.path, refused)
            return JSONResponse(_dump(results))

        async def operation(request: Request) -> Response:
            known(device_id := request.path_params["id"])
            name = request.path_params["operation"]
            if name not in instrument.view.value.devices[device_id].interface.operations:
                raise _RefusedError(404, f"'{device_id}' has no operation '{name}'")
            result = await instrument.execute_device_command(device_id, name, kwargs=await _body(request))
            if not result.is_ok:
                return problem(422, f"'{device_id}' refused '{name}'", request.url.path, [_dump(result)])
            value = result.unwrap()
            return Response(status_code=204) if value is None else JSONResponse(_dump(value))

        device_id = {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
        name = {"name": "operation", "in": "path", "required": True, "schema": {"type": "string"}}
        routes: list[tuple[str, Endpoint, str, list[dict[str, Any]]]] = [
            ("/devices/{id:key}", read, "GET", [device_id]),
            ("/devices/{id:key}", write, "PATCH", [device_id]),
            ("/devices/{id:key}:{operation:key}", operation, "POST", [device_id, name]),
        ]
        for path, handler, method, params in routes:
            app.add_api_route(
                path,
                _guarded(handler),
                methods=[method],
                operation_id=f"device_{handler.__name__}",
                openapi_extra={"parameters": params, "responses": _ERRORS},
            )


def build_app(instrument: Instrument[Any, Any, Any]) -> FastAPI:
    """An app with 1 route per operation of the instrument's kind, the reads of each state resource, the devices, and
    ``/interface``."""
    app = FastAPI(title=instrument.view.value.config.name)

    async def unrouted(request: Request, error: Exception) -> Response:
        status = error.status_code if isinstance(error, HTTPException) else 500
        return problem(status, str(getattr(error, "detail", "")) or HTTPStatus(status).phrase, request.url.path)

    app.add_exception_handler(HTTPException, unrouted)
    routes = _Routes(instrument)
    routes.schemas["Problem"] = _PROBLEM_SCHEMA
    table = route_table(instrument)
    for (method, path), info in table.items():
        endpoint, extra, status = routes.operation(info)
        app.add_api_route(
            path,
            endpoint,
            methods=[method],
            status_code=status,
            summary=info.label,
            description=info.desc or "",
            openapi_extra=extra,
        )
    standard = ("create", "update", "delete")
    for resource in sorted({info.resource for info in table.values() if info.intent in standard and info.resource}):
        routes.reads(app, resource)
    routes.devices(app)

    async def described(_: Request) -> Response:
        return JSONResponse(instrument.interface.model_dump(mode="json"))

    app.add_api_route("/interface", _guarded(described), methods=["GET"], operation_id="get_interface")

    base = app.openapi

    def openapi() -> dict[str, Any]:
        document = base()
        document.setdefault("components", {}).setdefault("schemas", {}).update(routes.schemas)
        return document

    app.openapi = openapi
    return app
