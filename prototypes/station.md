# Station setup

Written on 2026-11-19, reworked on 2026-11-20 for the server model. Built on 2026-11-20, except the lab and
`vxl station info`. It collects the pieces of
`records.md`, `server.md`, `feed.md`, `interface.md`, `acquisition.md` and `lab.md` into 1 picture. The detail stays
in those notes. `notes/platform/station.md` (2026-11-08) is older than all of this.

## Processes on a station computer

```text
                         station computer
┌─────────────────────────────────────────────────────────────────────────┐
│  station service  (Station, its instrument, the records)  127.0.0.1 only │
│    ├─ 1 feed ─────────────▶ server ──▶ windows, and the lab service      │
│    └─ HTTP operations ◀──── server ◀── operations from windows (HTTP)    │
│                                                                          │
│  records.sqlite3 (WAL) ──▶ server (history, full logs, acquisition.json) │
│                                                                          │
│  device nodes (vxl node start), here or on camera computers              │
└─────────────────────────────────────────────────────────────────────────┘
images and acquisition.json / acquisition.log.jsonl ──▶ storage (disk or S3)
```

| Process | Does | Started by | Status |
| --- | --- | --- | --- |
| **station service** | `Station`: 1 instrument session at a time, the records, the log journal; sends 1 feed and answers operations, both to its server only | `vxl station start` | built: `Station`, its topics (`vxl.web.station.topics`), and `StationService` (`vxl.web.station.service`), which serves them and the HTTP operations on 1 local address |
| **server** | The feed to windows, operations passed on, records history, local `/data`, web app files (`server.md`) | `vxl station start`, unless `--headless` | built (`vxl.web.server`) |
| **device nodes** | Run devices on another computer, over ZMQ | `vxl node start <node_id>` on each computer | built |

The lab service runs on its own computer, or on a station computer, with `vxl lab start` (`lab.md`). It has its own
server.

## What each part owns

- **The station service owns the hardware and the records.** Nothing outside it changes either. Its only client is
  its server; it runs no outside request except the operations the server passes on.
- **The server owns everything outside, and no state.** Windows, the lab service and readers of stored data all go
  through it. A slow window costs only the server. It reads the records database in WAL mode, in its own capped
  process, so a query never waits on, or slows, the station (`records.md`).
- **Storage owns the pixels.** Images never pass through the station. Remote storage serves itself; local files are
  served by the server on the machine that has the disk.

## What goes through where

| Data | Path |
| --- | --- |
| A person's edit or command | window → server → the station service (HTTP; `ETag` / `If-Match`, `202` for long actions; `interface.md`) |
| Instrument state, activities, progress (`AcquisitionInfo`) | station view → feed → server → windows |
| Live frames | station → feed (frame socket) → server → windows |
| The acquisition that ran last | `AcquisitionStore.subscribe` → feed (`acquisition.*` topics) → server → windows |
| Log lines | `LogJournal.subscribe` → feed (the `log` topic: the newest line, with its `seq`) → server → windows; missed lines from the server's records history |
| History, full logs, `acquisition.json` | records database → server → windows and the lab |
| Small topics for the lab | server → the lab service, which reads them as any reader does (`lab.md`) |
| Images | cameras → storage; readers go to storage, or to the server for local files |

## Start and stop

`vxl station start`, in order:

1. Load `station.yaml` (`StationConfig.load()`); refuse to start when it has problems.
2. Take the local address of the service (`StationService`, `127.0.0.1:5600`), for the feed sockets and the HTTP
   operations. When the port is taken, this station runs already: say so and end with exit code 3. This comes
   before step 3, because a second `Station.open()` would end the acquisition that runs in the first station.
3. `Station.open()`: start the log journal, then end each acquisition an earlier run left open as interrupted.
4. Start the server as a child process (unless `--headless`), pointed at the service, the records database, the
   storage and the web app. Print the address windows open, when the server takes connections.
5. Watch the server and start it again when it stops, after a wait that doubles from 1 s to 30 s while it stops
   early. When another program holds the server's port, say so and try again. The run does not stop.
6. Wait. A person opens an instrument session from a window (`open_session`).

On Ctrl-C, `SIGTERM` or `SIGHUP`, in reverse: stop the server, `Station.close()` (closes the session, which stops
any acquisition; stops the journal), stop serving. Checked in a real run on 2026-11-21. On Windows only Ctrl-C does
this.

## Settings

`station.yaml` (`StationConfig`) holds the station's id, name, storage, remotes and metadata forms today. To add:

```yaml
server:
  port: 8000                      # optional, default 8000
  command: vxl-server             # optional: another server program
  web: /path/to/the/built/app     # optional: the web app to serve
```

Built (`ServerSettings` in `vxl.station.config`); `vxl station init` writes the section. The station service's own
port is local only (`5600`, 1 port for its feed sockets and its API); it has no setting yet.

## The CLI around it

Agreed so far (product, then action):

| Command | Does | Status |
| --- | --- | --- |
| `vxl station init` | Writes `station.yaml` | built |
| `vxl station check` | Checks `station.yaml` and every instrument folder it finds, and shows the paths it found | built (2026-11-20) |
| `vxl station info` | Shows the station: id, name, folder, instruments, storage | not built |
| `vxl station start` | Starts the station service and its server. `--headless` starts no server | built (2026-11-20) |
| `vxl lab start` | Starts the lab service and its server, from `lab.yaml` | not built |
| `vxl node start <node_id>` | Starts a device node | built |
| `vxl devices shell` | Tries devices from a rig file | built |
| `vxl legacy web\|qt\|check\|init\|import-catalog` | The legacy apps, frozen | built |

## Where it lives

Picked on 2026-11-20, changed on 2026-11-21 (`server.md` › Where the code lives).

```text
src/vxl/
├── station/            station.py (Station): no web code, and no feed
├── lab/                later: the lab, a peer of station
├── web/                the web layer: all that a window or another reader needs
│   ├── feed.py                   what all speak: the messages and the publisher
│   ├── sockets.py, client.py     the feed's 2 sockets, and the reader
│   ├── problems.py               the form of every failure answer
│   ├── server.py                 the server, and the program vxl-server
│   └── station/                  topics.py (StationTopics), service.py (StationService),
│                                 instrument.py (InstrumentRouter); later web/lab/
└── cli/                station.py, later lab.py: starts a service and its server together
web/kit, web/station, web/lab   the browser apps; web/lab later holds the Zarr viewer
web/legacy                      the old station app, frozen, until legacy goes
```

- `vxl.station` and `vxl.lab` never import each other, and neither do `web/station/` and `web/lab/`.
- `vxl.station` and `vxl.instrument` know nothing of the feed. `StationTopics` reads the station from outside: its
  view, its live frames and its records.
- `vxl.web.client` is for any Python caller: Qt, notebooks, scripts, tests, and the lab service.
- The server imports the 4 shared files of `web/` (feed, sockets, reader, problems), and nothing else of
  `vxl`, so a server in another language can replace it. 1 test keeps this rule.
- The feed spec is written down next to the code, for any server program (`server.md`).

## Open

- **A setting for the station's local port** (`5600`), if it clashes with something on a computer.
- **Login and who may see what:** later, with the lab.
