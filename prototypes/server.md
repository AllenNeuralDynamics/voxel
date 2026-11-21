# Server

Agreed on 2026-11-20. **Built** on that day, now in `src/vxl/web/server.py`, tested in `tests/web/`; what is built and
what is left is in "As built", and what a battle test found on 2026-11-21 is in "Battle test". Until that day this note
was `gateway.md`: the name, the role and the layout changed (see "Decided on 2026-11-20"). Replaces the feed proxy and
the share service (`proxy.md` and the share service of `records.md`, 2026-11-19). See `feed.md` for the feed itself and
`station.md` for how the processes fit together.

## Why

The station feed is push-only, but each client still costs the station: 1 send per client, a queue and merge for
each slow client, and 1 task per WebSocket on the event loop that runs the acquisition. The UI is for many people
on many computers, and the lab watches too. A history search, a file read or a slow window must never run in the
process that runs the acquisition.

## The idea

**A server is the web front of 1 service, on the same computer. Services own state; the server only carries it.**

- **Services:** the station service (`vxl.station`) and the lab service (`vxl.lab`). They are peers with the same
  shape: their main object, the topics they publish, and an `api` module with their FastAPI operations. Neither
  imports the other. A service publishes 1 feed and answers operations, both on `127.0.0.1` only.
- **Server:** 1 program, `vxl-server`. Each service has its own running server, on its own port. The program does not
  know which kind of service it fronts; only its settings differ.
- **A server never talks to another server.**

```text
station computer                       lab computer
  station service                        lab service ── reads small topics ──▶ each station's server
    └─ its server ◀── windows              └─ its server ◀── the lab page
```

- **A service has exactly 1 client: its server.** The station never fans out.
- **A window talks to 1 address:** the server of the service that it shows. A browser, a Qt app and a notebook are the
  same kind of client; none has its own path to a service.
- **The lab service is an ordinary reader of each station's server** (`vxl.web.client`), as a notebook is. It reads
  the small topics (status, run progress, alerts) and publishes the stations as lab topics (`lab.md`).
- **Opening a station from the lab sends the browser to that station's server.** Frames, commands and history then
  pass 1 server. The lab must be able to reach each station computer, as in a VPN.
- **A lab and a station on 1 computer** run 2 servers on 2 ports.

## What a server does

1. **The feed to windows:** it keeps the last value of each topic of its service, so a new window gets `full: true`
   from the server and the service never sees it. 1 message goes to many readers; a frame is shared, never copied per
   window. Frames keep only the newest per topic; state never drops (the rules in `feed.md`). 1 task per window
   filters the topics that the window subscribed to.
2. **Commands:** it passes each HTTP call on to its service (`vxl.web.station.service`, later the lab's). It changes
   nothing in the call.
3. **Records history:** it serves stored data from `records.sqlite3` (WAL, read-only): history, `acquisition.json`,
   full logs. It runs in its own capped process, so a query never waits on, or slows, the station. Only a station has
   a records database.
4. **Local data:** it serves image files on its own machine at `/data/...`, read-only, with HTTP Range requests, no
   cache and no changes. Remote storage (S3, MinIO, a file server) serves itself; the record holds its URL.
5. **Web app files:** it serves the built browser app, since the browser knows only the server's address.

The server opens only the message envelope (topics, cursor, `full`). Frames (VXSF bytes) pass through unopened.

**A server never renames, and it owns no state.** Topic names are global: the service adds its own prefix
(`stations.<id>.`, `lab.`). HTTP follows the same rule: a station's server serves `/api/stations/<id>/...`, the
lab's server `/api/lab/...`. A window uses the same topics and paths wherever it runs, and a later setup with more
than 1 service behind a server, or with servers in a row, needs no new names (`feed.md`).

## The station computer

```bash
uv run vxl station start
```

1. Load `~/.voxel/station.yaml`; refuse to start when it has problems.
2. Start the station service in this process. Its feed sockets and its HTTP operations listen only on `127.0.0.1`.
3. Start the server as a child process, for example
   `vxl-server --upstream http://127.0.0.1:5600/api/stations/<id> --port 8000 --records ~/.voxel/records.sqlite3 --data <store> --web <app>`.
4. Print `Open http://<host>:8000`.
5. Watch the server and start it again when it stops. The run does not stop.
6. On Ctrl-C, `SIGTERM` or `SIGHUP`: stop the server, then close the station.

The full order, with the checks of the 2 ports, is in `station.md` › Start and stop.

`vxl station start --headless` starts no server: no windows, the run only.

## The lab computer

```bash
uv run vxl lab start
```

1. Load `~/.voxel/lab.yaml`.
2. Start the lab service in this process, listening only on `127.0.0.1`. It connects to each station's server as a
   reader.
3. Start a server for it.
4. Print `Open http://<lab-host>:8000`.

## Settings

```yaml
# station.yaml
server:
  port: 8000                      # optional, default 8000
  command: vxl-server             # optional: another server program, for example a Rust one
  web: /path/to/the/built/app     # optional: the web app to serve
```

`lab.yaml` has the same `server:` section. On a computer that runs both, the 2 servers need 2 ports.

## Any server program

A server in another language (for example Rust) can replace the Python one when 4 things hold:

1. **The feed is a written spec**, not Python code: the envelope, the frame message (a VXFP packet: prefix, envelope,
   VXSF bytes), topic names, the version, and how HTTP calls pass. The Python types in `vxl.web.feed` follow the spec.
2. **The records read schema is public.** The server reads `records.sqlite3` directly (`records.md`).
3. **The command-line flags are part of the spec:** `--upstream` (the service's local address), `--port`, `--records`,
   `--data` and `--web`. `vxl` starts whatever `server.command` names with the same flags.
4. **The server tests are black-box tests:** they start any server program, connect over sockets, and check what
   comes out.

The Rust plan from `proxy.md` (deleted in `d74219bf`, kept in git) still applies: `tokio`, `tokio-tungstenite`
upstream, `axum` for windows, `tokio::sync::broadcast` with `bytes::Bytes` for the fan-out, shipped with `maturin`
(`bindings = "bin"`).

## As built

2026-11-20. `Server` (`src/vxl/web/server.py`) builds 1 app from the parts below; the same file holds the
`vxl-server` program.

- **A service has 1 local address** for its feed sockets and its operations, with its own path:
  `http://127.0.0.1:5600/api/stations/<id>`. That address is the server's `--upstream`. The server serves the same
  path.
- **Data is under `/api`, and every other path is a page of the web app** (decided 2026-11-21). So a page has an
  address such as `/stations/<id>/run`, with the station's id in it: a link names its station by itself, and keeps
  its form if 1 host ever serves many stations. Topic names do not change.
- **`GET /api`** answers `{"service": "/api/stations/<id>"}`: the path of the service that this server fronts. It is
  the server's own answer, so it also comes while the service is gone. The start page `/` reads it to send the
  browser to `/stations/<id>/run`; the name of the station is in the feed topic `stations.<id>.station`. Any other
  path under `/api` that is not the service's answers a `404` problem, never the app's page.
- **Paths under `/api/stations/<id>`:**

  | Path | Served by |
  | --- | --- |
  | `/feed/state`, `/feed/frames` | the server, from the feed it reads from the service |
  | `/history/acquisitions` (filters `status`, `instrument`, `from`, `to`, `limit`), `/history/acquisitions/<id>`, `/history/acquisitions/<id>/log`, `/history/logs` (`after_seq`, `limit`) | the server, from `--records` |
  | `/data/...` | the server, from `--data`, read-only, with Range requests |
  | any other path | the service; the server passes the call on |

  Outside `/api`, the server serves the web app from `--web`; a path that is no file gets `index.html`.
- **The feed job reuses the feed code:** the server reads the service with `FeedClient` and gives each message,
  unchanged, to a `FeedRelay`, which `FeedSockets` serves. The service's cursors reach the windows as they are.
  When the reading fails for any reason, such as a service that refuses the socket, the server logs it and reads
  again, after a wait that doubles from 1 s to 30 s.
- **Operations pass through Python's `http.client`, in the server's own pool of 32 threads,** so the server needs
  no new dependency and a slow service cannot hold up the history. The path and the query pass as the bytes that
  the window sent (`a%2Fb` stays `a%2Fb`), and a header that is given more than once stays that way, in both
  directions. A call that the service does not answer, or answers with something else than HTTP, gets a `502`
  problem.
- **History** opens a read-only connection for each query, at most 4 at once. A log line has the form of the feed's
  `log` topic. An acquisition is the stored record with its `status`; an archived one is not found. A number in a
  stored record that is not finite is given as `null`.
- **`/data` and the web app answer `404` while their folder does not exist,** such as a store before the first
  acquisition. Every failure answer of the server itself is a problem (`ProblemDetails`).
- **`--upstream` must have a path under `/api/`** (`/api/stations/<id>`): the server refuses to start without one.
- **`vxl station start`** starts the server with `python -m vxl.web.server`, or with `server.command`, and starts it
  again when it stops (`station.md` › Start and stop). Checked in a real run: a killed server came back, the session
  stayed open, and a reader connected again by itself and got a full message.

Not built, or known and left:

- A window cannot subscribe to only some topics (`feed.md` › Later).
- The cap on the process: a lower OS priority.
- The public read schema of the records: the history gives the stored record, which has no status for each visit.
- The server always reads the frame socket of its service, also when no window watches.
- A window does not learn that the service is gone: the server keeps the last values. A topic for it would be state
  that the server owns.
- Where the built web app lives when `vxl` is installed: `server.web` names a folder by hand today.

## Battle test

2026-11-21. 3 runs against the real code: a whole session through the server on a simulated SPIM microscope (every
kind of route, a preview with frames, an acquisition, the history and a 43 MB file read by Range), a real
`vxl station start`, and 2 reviews that tried to break the feed and the server, and the station service.

Fixed that day, each with a test or a real run:

- A second `vxl station start` on the same computer ended the acquisition of the first one (`Station.open()` ran
  before the port check). The service now takes its port first.
- `SIGTERM` ended `vxl station start` with no cleanup: the server stayed, and the instrument was not closed.
- A taken port: the listener ended the whole program (`SystemExit`), and a server whose port was taken was started
  again without end, with `Open http://...` printed each time.
- The server stopped reading the feed for good after 1 failure that was no lost connection.
- The pass-through decoded the path, joined repeated headers, and answered `500` for an answer that was no HTTP.
- An operation that gives back an id (`POST /acquisition:start`) answered `500`.
- `NaN` and `Infinity` were accepted in a request body, and written to the state feed as they are.
- An activity that holds a resource (`ActivityBusyError`) answered `500`; it answers `409`.
- A keyed action on a state collection answered `404` for a key that the collection does not hold yet, such as
  `POST /state/positions/{device_id}:set`.
- `PATCH /devices/{id}` ignored `If-Match`. A path with a `/` at its end answered a redirect to the service's local
  address; it answers `404`.
- A data folder that does not exist yet answered `500`.

Found in the core, and fixed on the same day: a bad position rule was saved, and the instrument could not open
again; and ordinary bad input answered `500` (an instrument name that is no folder name, a stage move outside the
limits, a metadata form that is no class, a power that is no number). What is left of the core findings is in
`TODO.md` › Found in the battle test.

Not tested: a client that disappears without a close, many readers at once, a slow reader with frames of several
MB, a bad `server:` section, `--headless`, the routes of 2 kinds in 1 process, and a session that closes while a
request runs.

## Where the code lives

Decided on 2026-11-21, and built.

```text
src/vxl/
├── instrument/    ...                                       no web library, no feed
├── station/       station.py                                no web library, no feed
└── web/           the web layer; all but feed.py needs the `web` install option
    ├── feed.py             the messages and the publisher
    ├── problems.py         ProblemDetails
    ├── sockets.py          FeedSockets, Listener
    ├── client.py           FeedClient
    ├── server.py           Server, History, and the vxl-server program
    └── station/            the station's web side; the lab gets web/lab/ later
        ├── topics.py       StationTopics
        ├── service.py      StationService
        └── instrument.py   InstrumentRouter
```

- **`src/vxl/web/` is the only place that imports a web library** (FastAPI, Starlette, uvicorn, websockets). The
  instrument and the station work with none installed.
- **The feed and the station's topics are in `web/`** (moved on 2026-11-21 from `src/vxl/feed.py` and
  `src/vxl/station/topics.py`): only the web layer uses them. The instrument and the station know nothing of the
  feed; `StationTopics` reads the station's view, live frames and records from outside. `feed.py` itself imports no
  web library.
- **Rule: the server (`web/server.py`) imports the 4 shared files of `web/` (`feed.py`, `sockets.py`,
  `client.py`, `problems.py`), and nothing else of `vxl`.** It never imports `web/station/`. 1 test keeps it: a
  process that imports only the server loads only those modules.
- **A Rust server costs nothing here:** delete `web/server.py` and name the program in `server.command`. The
  services need the rest in both cases.
- **An instrument gives a router, not an app.** `InstrumentRouter(instrument, lease=...)` is the routes of 1 open
  instrument. The station service owns the 1 app: it adds its own 3 routes and the feed sockets, passes each
  `/instrument/...` request to the router of the open session, and answers every failure in 1 place
  (`ProblemDetails.install`). The web library makes the failure answers and describes them in the API page.
- **`ProblemDetails` knows no error of `vxl`.** The service gives it the status of each kind of error
  (`InstrumentRouter.statuses`), so the server uses the same class for its own failure answers.
- Rejected: the server as its own package that imports the feed code (`vxl` must install the server to start it, so the
  2 packages need each other); the feed code in the server's package (`vxl` then needs the Python server's package also
  when a Rust server runs); the feed code in `vxlib` (Voxel's wire format in a general library that `rigup` also
  carries); the feed code as its own package (1 more package for a rule that a test can keep); the web code spread over
  `vxl.station` (`api.py`, `service.py`), a `vxl.feed` package (sockets, client) and `vxl.server`, as first built on
  2026-11-20 (7 classes in 3 files for 1 service; a helper class that was not a real thing; 1 app for the station and 1
  more for each session); 1 route for all operations (it gives up the agreed HTTP rules).

## Measured

2026-11-20, Apple M4 Pro, Python 3.13, `websockets` 17, separate processes, 30 frames per second, 5 s per case. The
station sent frames directly to clients, or to a server that sent them on.

| Frame | Clients | Path | p50 | p99 | Station CPU |
| --- | --- | --- | --- | --- | --- |
| 0.5 MB | 1 | direct | 0.36 ms | 1.4 ms | 0.9 % |
| 0.5 MB | 1 | server | 0.63 ms | 2.3 ms | 0.9 % |
| 2 MB | 4 | direct | 2.4 ms | 7.8 ms | 10.9 % |
| 2 MB | 4 | server | 2.3 ms | 7.3 ms | 2.4 % |
| 8 MB | 4 | direct | 6.2 ms | 10.2 ms | 17.8 % |
| 8 MB | 4 | server | 8.3 ms | 12.0 ms | 5.0 % |

The local hop adds about 0.3–2 ms per frame (a frame at 30 fps lasts 33 ms). With 4 clients the station uses 3–4
times less CPU. Not covered: an acquisition running at the same time, newest-only dropping, real browsers. Measure
again when the real feed exists.

## Prior art

The same job has other names elsewhere.

- EPICS [Channel Access and PV Access gateways](https://mdavidsaver.github.io/p4p/gw.html): many clients share 1
  connection to the server that owns a value; the gateway buffers values, joins subnets and adds access control.
- WebRTC [SFU](https://bloggeek.me/webrtcglossary/sfu/): forwards each stream only to the viewers who want it, and
  can be chained.
- ROS [Foxglove bridge](https://docs.foxglove.dev/docs/connecting-to-data/ros-foxglove-bridge): robot topics to
  browsers over WebSocket. A bridge translates between 2 systems; the server does not translate.
- NATS [leaf nodes](https://docs.nats.io/learn/topologies/leaf-nodes): connect out to a hub and chain into trees.

## Decided on 2026-11-20

- **The name is "server"**, not "gateway": "the station's server", "the lab's server". It fits what people say ("Is
  the server down?", "Which port does the server listen on?", "The server serves the history"), and it has no meaning
  as lab hardware. Its 2 costs are handled in words: "the server is down" does not mean that the run stopped, and the
  rule "the server owns no state" is written here and in its code. Only this process is called the server; the
  station and the lab are services.
- **Names considered:** `gateway` (fits each sentence; not liked), `relay` (says "passes on, changes nothing", but
  not the 3 jobs that serve, and a relay is also a lab part), `hub` (a USB hub in a lab, and 6 driver classes),
  `broker` (topics only), `proxy` (the name before; not the cache or the history), `bridge` (it translates),
  `router` (the HAL's optical routers), "web service" (not a word of its own in this repo).
- **1 server fronts 1 service.** Before, 1 program was chained at every level: a station's gateway connected out to
  a gateway on the lab machine. That gave 1 program 2 roles, and only the lab's role needed the hard parts:
  connections from other servers, frames passed up only while someone watches, commands carried back down to a
  station, and a token for each station. All 4 are dropped.
- **Later, for a station that the lab cannot reach:** servers in a row. Topic names and paths already carry the
  service's name, so the feed does not change.
- **`--headless`** replaces `--no-gateway`.

## Decided on 2026-11-21

- **Data paths are under `/api`,** so that the pages of the web app can use `/stations/<id>/...` (see "As built").
  The rule "the server serves the same path as the service, and never renames" stays.
- **The station's id stays a UUID.** It must be unique with no one to check it, and it is in the records. A readable
  station id was considered and dropped.

## Open

- **How the lab learns each station's address:** a list in `lab.yaml`, or each station tells the lab.
- **Login and who may see what:** a window at the lab talks to a station's server directly, so each station's server
  must check who the person is. Later, with the lab.
- **The lab page's history across stations:** from the lab service's index, or from each station's server.
- **Local data during a run:** reading the station disk that the run writes to. The server may refuse or slow
  `/data` reads while a run is active.
- Whether the station limits how many operations it takes at once.
