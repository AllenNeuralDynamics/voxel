"""The server: the web front of 1 service on the same computer, and the ``vxl-server`` program that runs it. It
carries what the service owns, and owns no state.

It imports the shared parts of :mod:`vxl.web` (feed, sockets, client, problems), and nothing else of ``vxl``, so
that a server in another language can take its place.
"""

import argparse
import asyncio
import datetime
import http.client
import json
import logging
import sqlite3
from collections.abc import AsyncGenerator, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import aclosing
from http import HTTPStatus
from ipaddress import IPv4Address
from pathlib import Path
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote, urlsplit

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

from vxl.web.client import FeedClient
from vxl.web.feed import FeedRelay
from vxl.web.problems import ProblemDetails
from vxl.web.sockets import FeedSockets, Listener

logger = logging.getLogger(__name__)

_API = "/api"
"""Every path of a service is under it. The other paths belong to the web app."""

_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

_OF_1_CONNECTION = frozenset(
    {
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)
"""The headers that describe 1 connection, not the call: they are not passed on."""

_OF_THIS_SERVER = frozenset({"date", "server"})
"""The headers that this server writes into each answer by itself."""

_TIMEOUT_S = 120.0

_CALLS_AT_ONCE = 32
"""How many calls wait for the service at once: more than the default thread pool, which the history also uses."""

_READ_AGAIN_S = 0.5
"""The first wait before the server reads the feed of its service again. The service is on the same computer."""

_READ_AGAIN_MAX_S = 5.0

_MAX_ROWS = 1000

_MAX_SEQ = 2**62
"""Above every place in the log that the database can hold."""

_ACQUISITIONS = """
    SELECT id, revision, instrument, status, created_at_us FROM acquisitions
    WHERE archived_at_us IS NULL
      AND (?1 IS NULL OR status = ?1)
      AND (?2 IS NULL OR instrument = ?2)
      AND (?3 IS NULL OR created_at_us >= ?3)
      AND (?4 IS NULL OR created_at_us < ?4)
    ORDER BY created_at_us DESC LIMIT ?5
"""


class History:
    """Reads the ``records.sqlite3`` of a station, read-only, and answers as JSON under ``<prefix>/history``. Each
    query opens its own connection in a thread, and at most ``at_once`` run together, so a slow query delays only
    other queries. A log line has the form of the feed's ``log`` topic."""

    def __init__(self, path: Path, *, at_once: int = 4) -> None:
        self._path = path.resolve()
        self._slots = asyncio.Semaphore(at_once)

    def routes(self, prefix: str = "") -> list[Route]:
        """The history routes, under ``prefix``."""
        return [
            Route(f"{prefix}/history/acquisitions", self._acquisitions),
            Route(f"{prefix}/history/acquisitions/{{acquisition_id}}", self._acquisition),
            Route(f"{prefix}/history/acquisitions/{{acquisition_id}}/log", self._acquisition_log),
            Route(f"{prefix}/history/logs", self._logs),
        ]

    async def _acquisitions(self, request: Request) -> Response:
        """The acquisitions that are not archived, newest first, with ``status``, ``instrument``, ``from`` and ``to``
        (ISO 8601 times of creation) and ``limit`` as filters."""
        asked = request.query_params
        try:
            values = (
                asked.get("status"),
                asked.get("instrument"),
                self._micros(asked["from"]) if "from" in asked else None,
                self._micros(asked["to"]) if "to" in asked else None,
                self._limit(request, 100),
            )
        except ValueError as error:
            return ProblemDetails.response(422, str(error), request.url.path)
        return await self._answer(
            request,
            lambda connection: [
                {
                    "id": row["id"],
                    "revision": row["revision"],
                    "instrument": row["instrument"],
                    "status": row["status"],
                    "created_at": self._time(row["created_at_us"]),
                }
                for row in connection.execute(_ACQUISITIONS, values)
            ],
        )

    async def _acquisition(self, request: Request) -> Response:
        """The stored record of 1 acquisition, with its ``status``."""

        def read(connection: sqlite3.Connection) -> dict[str, Any] | None:
            row = connection.execute(
                "SELECT acquisition_json, status FROM acquisitions WHERE id = ? AND archived_at_us IS NULL",
                (request.path_params["acquisition_id"],),
            ).fetchone()
            return None if row is None else {**self._loaded(row["acquisition_json"]), "status": row["status"]}

        return await self._answer(request, read)

    async def _acquisition_log(self, request: Request) -> Response:
        """The log lines of 1 acquisition, after ``after_seq``, in order."""
        try:
            after, limit = self._after(request), self._limit(request, _MAX_ROWS)
        except ValueError as error:
            return ProblemDetails.response(422, str(error), request.url.path)

        def read(connection: sqlite3.Connection) -> list[dict[str, Any]] | None:
            window = connection.execute(
                "SELECT log_start_seq, log_end_seq FROM acquisitions WHERE id = ? AND archived_at_us IS NULL",
                (request.path_params["acquisition_id"],),
            ).fetchone()
            if window is None:
                return None
            if window["log_start_seq"] is None:
                return []
            through = window["log_end_seq"] if window["log_end_seq"] is not None else _MAX_SEQ
            return self._lines(connection, max(after, window["log_start_seq"]), through, limit)

        return await self._answer(request, read)

    async def _logs(self, request: Request) -> Response:
        """The station's log lines after ``after_seq``, in order: what a reader of the ``log`` topic missed."""
        try:
            after, limit = self._after(request), self._limit(request, _MAX_ROWS)
        except ValueError as error:
            return ProblemDetails.response(422, str(error), request.url.path)
        return await self._answer(request, lambda connection: self._lines(connection, after, _MAX_SEQ, limit))

    async def _answer(self, request: Request, read: Callable[[sqlite3.Connection], Any]) -> Response:
        """The result of ``read`` as JSON; ``404`` when it finds nothing, ``503`` when the database cannot be read."""
        async with self._slots:
            try:
                found = await asyncio.to_thread(self._query, read)
            except sqlite3.Error as error:
                return ProblemDetails.response(503, f"the records cannot be read: {error}", request.url.path)
        if found is None:
            return ProblemDetails.response(404, "no such acquisition", request.url.path)
        return JSONResponse(found)

    def _query(self, read: Callable[[sqlite3.Connection], Any]) -> Any:
        connection = sqlite3.connect(f"{self._path.as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            return read(connection)
        finally:
            connection.close()

    @classmethod
    def _lines(cls, connection: sqlite3.Connection, after: int, through: int, limit: int) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT seq, emitted_at_us, recorded_at_us, level, logger, message, node_id, attributes_json, "
            "exception_json FROM logs WHERE seq > ? AND seq <= ? ORDER BY seq LIMIT ?",
            (after, through, limit),
        )
        return [
            {
                "seq": row["seq"],
                "emitted_at": cls._time(row["emitted_at_us"]),
                "recorded_at": cls._time(row["recorded_at_us"]),
                "level": row["level"],
                "logger": row["logger"],
                "message": row["message"],
                "node_id": row["node_id"],
                "attributes": cls._loaded(row["attributes_json"]),
                "exception": None if row["exception_json"] is None else cls._loaded(row["exception_json"]),
            }
            for row in rows
        ]

    @staticmethod
    def _loaded(text: str) -> Any:
        """Stored JSON, with ``None`` for each number that JSON cannot hold (NaN or an infinity)."""
        return json.loads(text, parse_constant=lambda _: None)

    @staticmethod
    def _time(micros: int) -> str:
        """A stored time as ISO 8601 in UTC, as the feed writes times."""
        moment = datetime.datetime.fromtimestamp(micros / 1_000_000, tz=datetime.UTC)
        return moment.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _micros(text: str) -> int:
        moment = datetime.datetime.fromisoformat(text)
        if moment.tzinfo is None:
            raise ValueError(f"'{text}' has no time zone")
        return int(moment.timestamp() * 1_000_000)

    @staticmethod
    def _after(request: Request) -> int:
        after = int(request.query_params.get("after_seq", "0"))
        if not 0 <= after <= _MAX_SEQ:
            raise ValueError(f"after_seq must be between 0 and {_MAX_SEQ}")
        return after

    @staticmethod
    def _limit(request: Request, default: int) -> int:
        limit = int(request.query_params.get("limit", str(default)))
        if not 1 <= limit <= _MAX_ROWS:
            raise ValueError(f"limit must be between 1 and {_MAX_ROWS}")
        return limit


class _Files(StaticFiles):
    """The files of a folder, read-only. While the folder does not exist, every path answers ``404``."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return
        await super().__call__(scope, receive, send)

    async def check_config(self) -> None:
        """Accept a folder that does not exist yet, such as a store before the first acquisition."""


class _AppFiles(_Files):
    """The files of a single-page web app: a path that is no file gets ``index.html``, so that the app's own routes
    load."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != HTTPStatus.NOT_FOUND:
                raise
            return await super().get_response("index.html", scope)


class Server:
    """Fronts the service at ``upstream``, such as ``http://127.0.0.1:5600/api/stations/<id>``, from ``async with``
    until its end. The path of a service is under ``/api``. :attr:`app` serves, under the same path as the service:

    - ``/feed/state`` and ``/feed/frames``: the feed of the service, to any number of readers;
    - ``/history/...``: the stored records in ``records``, when given;
    - ``/data/...``: the files under ``data``, read-only, when given;
    - any other path: passed on to the service and answered by it, both unchanged except the headers of 1
      connection. When the service does not answer, the answer is a ``502`` problem.

    ``GET /api`` answers the path of the service, as ``{"service": "/api/stations/<id>"}``, also while the service
    does not answer, and any other path under ``/api`` is not found. Every path outside ``/api`` belongs to the web
    app in ``web``, when given, so that its pages can have addresses such as ``/stations/<id>/run``.

    The server reads the feed of the service for as long as it runs, 1 connection at a time. Until the service's first
    full message arrives, and again from the moment that connection ends, its feed sockets refuse readers with
    ``503`` and close the open ones. So a closed socket and a refused one, with ``GET /api`` answering, tell a window
    that the service has stopped. The server reads the feed again after a wait that doubles from 0.5 s to 5 s."""

    def __init__(
        self, upstream: str, *, records: Path | None = None, data: Path | None = None, web: Path | None = None
    ) -> None:
        address = urlsplit(upstream)
        prefix = address.path.rstrip("/")
        if not prefix.startswith(f"{_API}/"):
            raise ValueError(f"'{upstream}' is no address of a service: its path is under {_API}/")
        self._prefix = prefix
        self._service = address.netloc
        self._relay = FeedRelay()
        self._client = FeedClient("ws" + upstream.removeprefix("http"), reconnect=False)
        self._tasks: list[asyncio.Task[None]] = []
        self._calls = ThreadPoolExecutor(max_workers=_CALLS_AT_ONCE, thread_name_prefix="vxl-server-call")
        routes: list[BaseRoute] = [Route(_API, self._service_path), *FeedSockets(self._relay).routes(prefix)]
        if records is not None:
            routes += History(records).routes(prefix)
        if data is not None:
            routes.append(Mount(f"{prefix}/data", _Files(directory=data, check_dir=False)))
        routes.append(Route(f"{prefix}/{{path:path}}", self._pass_on, methods=_METHODS))
        routes.append(Route(f"{_API}/{{path:path}}", self._no_service, methods=_METHODS))
        if web is not None:
            routes.append(Mount("/", _AppFiles(directory=web, html=True, check_dir=False)))
        self.app = Starlette(routes=routes)
        ProblemDetails.install(self.app)

    async def __aenter__(self) -> Self:
        self._tasks = [
            asyncio.create_task(self._keep_reading(self._client.state, self._relay.send, lost=self._lost)),
            asyncio.create_task(self._keep_reading(self._client.frames, self._relay.send_frames)),
        ]
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None
    ) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._relay.close()
        self._calls.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    async def _keep_reading[M](
        read: Callable[[], AsyncGenerator[M]], give: Callable[[M], None], *, lost: Callable[[str], None] | None = None
    ) -> None:
        """Give each message that the service sends to the relay, 1 connection at a time, and call ``lost`` with the
        reason each time a connection ends or cannot open. A message that does not follow the last one is dropped.
        The reading starts again after a wait that doubles from 0.5 s to 5 s while it fails."""
        wait = _READ_AGAIN_S
        while True:
            reason = "the service closed its feed"
            try:
                async with aclosing(read()) as messages:
                    async for message in messages:
                        wait = _READ_AGAIN_S
                        try:
                            give(message)
                        except ValueError as error:
                            logger.warning("Dropped a message of the service: %s", error)
            except Exception as error:  # such as a service that is gone, or that answers with something else
                reason = repr(error)
            if lost is not None:
                lost(reason)
            await asyncio.sleep(wait)
            wait = min(wait * 2, _READ_AGAIN_MAX_S)

    def _lost(self, reason: str) -> None:
        """The state feed of the service ended: close the windows' feed sockets until it is back."""
        if not self._relay.closed:
            logger.warning("Lost the feed of the service (%s); the windows wait for it", reason)
        self._relay.close()

    async def _service_path(self, _: Request) -> JSONResponse:
        """The path of the service that this server fronts: its own answer, also while the service is gone."""
        return JSONResponse({"service": self._prefix})

    async def _no_service(self, _: Request) -> Response:
        raise HTTPException(HTTPStatus.NOT_FOUND, f"this server fronts {self._prefix} only")

    async def _pass_on(self, request: Request) -> Response:
        """Pass ``request`` on to the service and give back its answer."""
        scope = request.scope
        target = (scope.get("raw_path") or quote(scope["path"]).encode()).decode("latin-1")
        if scope["query_string"]:
            target += "?" + scope["query_string"].decode("latin-1")
        headers = [
            (name.decode("latin-1"), value.decode("latin-1"))
            for name, value in request.headers.raw
            if name.decode("latin-1").lower() not in _OF_1_CONNECTION
        ]
        body = await request.body()
        loop = asyncio.get_running_loop()
        try:
            status, answered, content = await loop.run_in_executor(
                self._calls, self._send, request.method, target, headers, body
            )
        except (OSError, http.client.HTTPException) as error:
            return ProblemDetails.response(502, f"the service does not answer: {error!r}", request.url.path)
        response = Response(content, status_code=status)
        kept = [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in answered
            if name.lower() not in _OF_1_CONNECTION and name.lower() not in _OF_THIS_SERVER
        ]
        length = next((value for name, value in answered if name.lower() == "content-length"), None)
        if request.method == "HEAD" and length is not None:
            kept.append((b"content-length", length.encode("latin-1")))
        elif status not in (HTTPStatus.NO_CONTENT, HTTPStatus.NOT_MODIFIED):
            kept.append((b"content-length", str(len(content)).encode()))
        response.raw_headers = kept
        return response

    def _send(
        self, method: str, target: str, headers: list[tuple[str, str]], body: bytes
    ) -> tuple[int, list[tuple[str, str]], bytes]:
        connection = http.client.HTTPConnection(self._service, timeout=_TIMEOUT_S)
        try:
            connection.putrequest(method, target, skip_accept_encoding=True)
            for name, value in headers:
                connection.putheader(name, value)
            if body or method in ("POST", "PUT", "PATCH"):
                connection.putheader("Content-Length", str(len(body)))
            connection.endheaders(body or None)
            answer = connection.getresponse()
            return answer.status, answer.getheaders(), answer.read()
        finally:
            connection.close()


class ServerProgram:
    """1 run of ``vxl-server``, from its command-line arguments. The flags are the same for every server program,
    so that ``vxl`` can start another one in its place."""

    def __init__(self, argv: Sequence[str] | None = None) -> None:
        parser = argparse.ArgumentParser(prog="vxl-server", description="The web front of 1 Voxel service")
        parser.add_argument("--upstream", required=True, help="the service's local address, with its path")
        parser.add_argument("--port", type=int, default=8000, help="the port that windows open")
        parser.add_argument("--host", default=str(IPv4Address(0)), help="the address to listen on (default: all)")
        parser.add_argument("--records", type=Path, help="the service's records database")
        parser.add_argument("--data", type=Path, help="the folder of image files to serve under /data")
        parser.add_argument("--web", type=Path, help="the folder of the built web app")
        self._args = parser.parse_args(argv)

    async def run(self) -> None:
        """Serve until the program is stopped."""
        args = self._args
        server = Server(args.upstream, records=args.records, data=args.data, web=args.web)
        async with server, Listener(server.app, host=args.host, port=args.port):
            await asyncio.Event().wait()


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(ServerProgram(argv).run())
    except KeyboardInterrupt:
        return


__all__ = ["History", "Server", "ServerProgram", "main"]

if __name__ == "__main__":
    main()
