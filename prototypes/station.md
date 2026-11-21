# Station setup

Written on 2026-11-19, reworked on 2026-11-20 for the gateway model. Not built. It collects the pieces of
`records.md`, `gateway.md`, `feed.md`, `interface.md`, `acquisition.md` and `lab.md` into 1 picture. The detail stays
in those notes. `notes/platform/station.md` (2026-11-08) is older than all of this.

## Processes on a station computer

```text
                         station computer
┌─────────────────────────────────────────────────────────────────────────┐
│  station  (Station, its instrument, the records)          127.0.0.1 only │
│    ├─ 1 feed ─────────────▶ gateway ──▶ windows, and the lab machine     │
│    └─ vxl.station.api ◀──── gateway ◀── operations from windows (HTTP)   │
│                                                                          │
│  records.sqlite3 (WAL) ──▶ gateway (history, full logs, acquisition.json)│
│                                                                          │
│  device nodes (vxl node start), here or on camera computers              │
└─────────────────────────────────────────────────────────────────────────┘
images and acquisition.json / acquisition.log.jsonl ──▶ storage (disk or S3)
```

| Process | Does | Started by | Status |
| --- | --- | --- | --- |
| **station** | `Station`: 1 instrument session at a time, the records, the log journal; sends 1 feed and answers operations, both to its gateway only | `vxl station start` | `Station` built; `open()` / `close()` built; feed and API not built |
| **gateway** | Topic cache, fan-out, routing of operations, records history, local `/data`, web app files (`gateway.md`) | `vxl station start`, unless `--no-gateway` | not built |
| **device nodes** | Run devices on another computer, over ZMQ | `vxl node start <node_id>` on each computer | built |

The lab runs on its own computer, or on a station computer, with `vxl lab start` (`lab.md`).

## What each part owns

- **The station process owns the hardware and the records.** Nothing outside it changes either. Its only client is
  its gateway; it runs no outside request except the operations the gateway passes on.
- **The gateway owns everything outside.** Windows, the lab machine and readers of stored data all go through it. A
  slow window costs only the gateway. It reads the records database in WAL mode, in its own capped process, so a query
  never waits on, or slows, the station (`records.md`).
- **Storage owns the pixels.** Images never pass through the station. Remote storage serves itself; local files are
  served by the gateway on the machine that has the disk.

## What goes through where

| Data | Path |
| --- | --- |
| A person's edit or command | window → gateway → `vxl.station.api` (HTTP; `ETag` / `If-Match`, `202` for long actions; `interface.md`) |
| Instrument state, activities, progress (`AcquisitionInfo`) | station view → feed → gateway → windows |
| Live frames | station → feed (frame socket) → gateway → windows |
| Acquisition revisions | `AcquisitionStore.subscribe` → feed (records topic) → gateway → windows |
| Log lines | `LogJournal.subscribe` → feed (append topic, `seq` cursor) → gateway → windows |
| History, full logs, `acquisition.json` | records database → gateway → windows and the lab |
| Small topics for the lab | gateway → gateway on the lab machine (connects out) |
| Images | cameras → storage; readers go to storage, or to the gateway for local files |

## Start and stop

`vxl station start`, in order:

1. Load `station.yaml` (`StationConfig.load()`); refuse to start when it has problems.
2. `Station.open()`: start the log journal, then end each acquisition an earlier run left open as interrupted.
3. Start the feed end and `vxl.station.api`, on `127.0.0.1` only.
4. Start the gateway as a child process (unless `--no-gateway`), pointed at the feed, the records database, the
   storage and the web app. Print the address windows open.
5. Watch the gateway and start it again when it stops. The run does not stop.
6. Wait. A person opens an instrument session from a window (`open_session`).

On Ctrl-C or a stop signal, in reverse: stop the gateway, stop serving, `Station.close()` (closes the session, which
stops any acquisition; stops the journal).

## Settings

`station.yaml` (`StationConfig`) holds the station's id, name, storage, remotes and metadata forms today. To add:

```yaml
gateway:
  port: 8000                      # optional, default 8000
  upstream: wss://<lab-host>:8000 # optional: the lab machine to join
  command: vxl-gateway            # optional: another gateway program
```

The station's own feed and API ports are local only; their defaults need no setting.

## The CLI around it

Agreed so far (product, then action):

| Command | Does | Status |
| --- | --- | --- |
| `vxl station init` | Writes `station.yaml` | built |
| `vxl station check` | Checks `station.yaml` and every instrument folder it finds, and shows the paths it found | built (2026-11-20) |
| `vxl station info` | Shows the station: id, name, folder, instruments, storage | not built |
| `vxl station start` | Starts the station and its gateway. `--no-gateway` runs it headless | not built |
| `vxl lab start` | Starts the lab and its gateway, from `lab.yaml` | not built |
| `vxl node start <node_id>` | Starts a device node | built |
| `vxl devices shell` | Tries devices from a rig file | built |
| `vxl legacy web\|qt\|check\|init\|import-catalog` | The legacy apps, frozen | built |

## Where it will live

Picked on 2026-11-20. Each folder is made with its first code, not before.

```text
src/vxl/
├── feed/               the protocol: messages, the publisher end, vxl.feed.client
├── station/            publisher: station.py, topics.py (today's feed.py), api.py (FastAPI)
├── lab/                publisher, a peer of station: lab.py, topics.py, api.py (with its first operation)
└── cli/                station.py, lab.py: the only place that starts a publisher and a gateway together
gateway/                vxl_gateway, its own workspace package; imports only vxl.feed
web/kit, web/station, web/lab   the browser apps; web/lab later holds the Zarr viewer
web/legacy                      the old station app, frozen, until legacy goes
```

- `vxl.station` and `vxl.lab` have the same shape and never import each other.
- `vxl.feed.client` is for any Python caller: Qt, notebooks, scripts, tests.
- `vxl_gateway` may import `vxl.feed` and the public records schema, nothing else, so a gateway in another language can
  replace it. If imports slip, `vxl.feed` becomes its own small package.
- The feed spec is written down next to the code, for any gateway program (`gateway.md`).

## Open

- **Settings of the station's local ports**, if the defaults clash with something on a computer.
- **Login and who may see what:** later, with the lab.
