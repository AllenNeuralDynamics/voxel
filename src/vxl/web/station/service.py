"""The station as a service: the station, the feed it publishes and its HTTP operations, on 1 local address."""

from collections.abc import Awaitable, Callable
from functools import partial
from types import TracebackType
from typing import TYPE_CHECKING, Annotated, Any, Self

from fastapi import Body, FastAPI, Request, Response
from starlette.types import Receive, Scope, Send

from vxl.instrument.folder import InstrumentInspection
from vxl.metadata import resolve_metadata_class
from vxl.records import Records
from vxl.station.config import StationConfig
from vxl.station.errors import BusyError
from vxl.station.station import SessionInfo, Station, StationStatus
from vxl.web.feed import FeedPublisher
from vxl.web.problems import ProblemDetails
from vxl.web.sockets import FeedSockets, Listener
from vxl.web.station.instrument import InstrumentRouter
from vxl.web.station.topics import StationTopics

if TYPE_CHECKING:
    from uuid import UUID

DEFAULT_PORT = 5600
"""The local port of the station service, when none is given."""


class StationService:
    """Runs a station as a service from ``async with`` until its end: it opens the station, publishes it as feed
    topics, and serves them and the HTTP operations under :attr:`url`, on ``127.0.0.1`` only. Its 1 client is its
    server. ``port`` 0 takes a free port. Entering raises :class:`OSError` when the port is taken, before it opens
    the station.

    Under ``/api/stations/<id>`` it serves the feed sockets (``/feed/state``, ``/feed/frames``), the installed
    instruments (``GET /instruments``), the session's open and close (``POST /session:open`` with the name as
    ``instrument``, ``POST /session:close``), and the routes of the open instrument under ``/instrument``. Each answer
    to a request that is not a read carries ``Vxl-Feed-Cursor``, the place in the state feed at which the change is
    visible."""

    def __init__(self, config: StationConfig, *, port: int = DEFAULT_PORT, records: Records | None = None) -> None:
        self.station = Station(config, records=records)
        self._publisher = FeedPublisher(f"stations.{config.id}")
        self._topics: StationTopics | None = None
        self._router: tuple[UUID, InstrumentRouter] | None = None
        self._prefix = f"/api/stations/{config.id}"
        app = FastAPI(title=config.name, responses=ProblemDetails.described(), redirect_slashes=False)
        ProblemDetails.install(app, InstrumentRouter.statuses)
        app.router.routes.extend(FeedSockets(self._publisher).routes(self._prefix))
        app.add_api_route(f"{self._prefix}/instruments", self._instruments, methods=["GET"])
        app.add_api_route(f"{self._prefix}/instruments/{{name}}:inspect", self._inspect, methods=["GET"])
        app.add_api_route(f"{self._prefix}/metadata-forms", self._metadata_forms, methods=["GET"])
        app.add_api_route(f"{self._prefix}/session:open", self._open, methods=["POST"])
        app.add_api_route(f"{self._prefix}/session:close", self._close, methods=["POST"], status_code=204)
        app.mount(f"{self._prefix}/instrument", self._instrument)
        app.middleware("http")(self._stamp)
        self._listener = Listener(app, port=port)

    @property
    def url(self) -> str:
        """The address of the service, which its server takes as its upstream."""
        return f"http://{self._listener.host}:{self._listener.port}{self._prefix}"

    async def __aenter__(self) -> Self:
        # The address comes first. When it is taken, this station runs already, and a second open would end the
        # acquisition that runs there.
        await self._listener.__aenter__()
        try:
            await self.station.open()
        except BaseException:
            await self._listener.__aexit__(None, None, None)
            raise
        self._topics = StationTopics(
            self.station.config.info, self.station.view, self.station.live, self.station.records, self._publisher
        )
        await self._topics.show_newest()
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None
    ) -> None:
        try:
            await self.station.close()  # readers see the station close before their sockets end
        finally:
            if self._topics is not None:
                self._topics.close()
            self._publisher.close()
            await self._listener.__aexit__(kind, error, trace)

    async def _instruments(self) -> dict[str, InstrumentInspection]:
        """Each installed instrument, with whether its folder is in order and the problems found in it."""
        return {name: folder.inspection() for name, folder in self.station.discover_instruments().items()}

    async def _inspect(self, name: str) -> InstrumentInspection:
        """1 installed instrument, as :meth:`_instruments` gives it, with the content of its 3 files as read."""
        return self.station.inspect(name).inspection(files=True)

    async def _metadata_forms(self) -> dict[str, dict[str, Any]]:
        """The metadata forms that this station offers, by name: the dotted ``path`` of each class, and its JSON
        ``schema``."""
        return {
            name: {"path": path, "schema": resolve_metadata_class(path).model_json_schema()}
            for name, path in self.station.config.metadata_menu().items()
        }

    async def _open(self, instrument: Annotated[str, Body(embed=True)]) -> SessionInfo:
        """Open an installed instrument as the station's session."""
        return await self.station.open_session(instrument)

    async def _close(self) -> None:
        """Close the open session."""
        session = self.station.view.value.session
        if session is None:
            raise BusyError("no instrument session is open")
        await self.station.close_session(session.info.id)

    async def _instrument(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass a request on to the routes of the open instrument. They are made at the first request of a session."""
        if scope["type"] != "http":
            return
        view = self.station.view.value
        if view.session is None or view.status is not StationStatus.ACTIVE:
            raise BusyError("no instrument session is open")
        session_id = view.session.info.id
        if self._router is None or self._router[0] != session_id:
            lease = partial(self.station.instrument, session_id)
            async with lease() as instrument:
                self._router = (session_id, InstrumentRouter(instrument, lease=lease))
        await self._router[1](scope, receive, send)

    async def _stamp(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Add ``Vxl-Feed-Cursor`` to the answer of each request that is not a read: an RFC 9651 string."""
        response = await call_next(request)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            cursor = self._publisher.snapshot().cursor
            response.headers["Vxl-Feed-Cursor"] = f'"{cursor.stream_id}:{cursor.seq}"'
        return response


__all__ = ["DEFAULT_PORT", "StationService"]
