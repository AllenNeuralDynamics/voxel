# Station setup

Written on 2026-11-19 from what was agreed so far, not built. It collects the pieces of `records.md`, `proxy.md`,
`feed.md`, `interface.md`, `acquisition.md` and `lab.md` into 1 picture. The detail stays in those notes.
`notes/platform/station.md` (2026-11-08) is older than all of this.

## Processes on a station computer

```text
                         station computer
┌─────────────────────────────────────────────────────────────────────────┐
│  station  (Station, its instrument, the records)                         │
│    ├─ operations: HTTP, from each UI ◀───────────────── station UIs      │
│    └─ 1 feed ──▶ feed proxy ──▶ station UIs and lab screens (live)       │
│                                                                          │
│  records.sqlite3 (WAL) ──▶ share service ──▶ the lab (stored data)       │
│                                                                          │
│  device nodes (vxl node start), here or on camera computers              │
└─────────────────────────────────────────────────────────────────────────┘
images and acquisition.json / acquisition.log.jsonl ──▶ storage (disk or S3)
```

| Process | Does | Started by | Status |
| --- | --- | --- | --- |
| **station** | `Station`: 1 instrument session at a time, the records, the log journal; serves the instrument's operations over HTTP and sends 1 feed | `vxl station start` | `Station` built; `open()` / `close()` built; HTTP not built |
| **feed proxy** | Takes the station's 1 feed and fans it out to every screen; read-only | `vxl station start` | not built (`proxy.md`: Python first, then Rust) |
| **share service** | Serves stored data from the records database: history, `acquisition.json`, full logs | `vxl station start`, when `station.yaml` has `share:` | not built |
| **device nodes** | Run devices on another computer, over ZMQ | `vxl node start <node_id>` on each computer | built |
| **lab** | Index of every station's acquisitions, and the Lab app | `vxl lab start`, on a station or a lab server | not built (`lab.md`) |

## What each part owns

- **The station process owns the hardware and the records.** Nothing outside it changes either. It runs no outside
  request except the instrument's operations, which a person sends from a station UI.
- **The feed proxy owns the screens.** The station always has 1 subscriber, however many people watch
  (`proxy.md`). A slow screen costs only the proxy.
- **The share service owns outside reads.** It reads the database in WAL mode, in its own capped process, so a lab's
  query never waits on, or slows, the station (`records.md`).
- **Storage owns the pixels.** Images never pass through the station, the proxy or the share service.

## What goes through where

| Data | Path |
| --- | --- |
| A person's edit or command | UI → station (HTTP; `ETag` / `If-Match`, `202` for long actions; `interface.md`) |
| Instrument state, activities, progress (`AcquisitionInfo`) | station view → feed → proxy → screens |
| Live frames | station → feed (frame socket) → proxy → screens |
| Acquisition revisions | `AcquisitionStore.subscribe` → feed (records topic) → proxy → screens |
| Log lines | `LogJournal.subscribe` → feed (append topic, `seq` cursor) → proxy → screens |
| History, full logs, `acquisition.json` | records database → share service → the lab |
| Images | cameras → storage; readers go to storage |

## Start and stop

`vxl station start`, in order:

1. Load `station.yaml` (`StationConfig.load()`); refuse to start when it has problems.
2. `Station.open()`: start the log journal, then end each acquisition an earlier run left open as interrupted.
3. Start serving: the station's HTTP and its feed.
4. Start the feed proxy, pointed at the feed.
5. Start the share service, when `station.yaml` has `share:` and `--no-share` is not given.
6. With `--with-lab`, start the lab server too, on this computer.
6. Wait. A person opens an instrument session from a UI (`open_session`).

On Ctrl-C or a stop signal, in reverse: stop the share service and the proxy, stop serving, `Station.close()` (closes
the session, which stops any acquisition; stops the journal).

## Settings

`station.yaml` (`StationConfig`) holds the station's id, name, storage, remotes and metadata forms today. To add:

- **The station's address and port** for HTTP and the feed.
- **`proxy:`** its address and port for screens.
- **`share:`** its address and port; off when the section is missing.

Not decided: the section names and their fields.

## The CLI around it

Agreed so far (product, then action):

| Command | Does | Status |
| --- | --- | --- |
| `vxl station init` | Writes `station.yaml` | built |
| `vxl station check` | Checks `station.yaml` and every instrument folder it finds, and shows the paths it found | built (2026-11-20) |
| `vxl station info` | Shows the station: id, name, folder, instruments, storage | not built |
| `vxl station start` | Starts the processes above. `--with-lab` also starts the lab server; `--no-share` skips the share service even when `station.yaml` has `share:` (decided 2026-11-19) | not built |
| `vxl node start <node_id>` | Starts a device node | built |
| `vxl devices shell` | Tries devices from a rig file | built |
| `vxl lab start` | Starts the lab server | not built |
| `vxl legacy web\|qt\|check\|init\|import-catalog` | The legacy apps, frozen | built |

## Where it will live

Picked on 2026-11-19, for now. Each folder is made with its first code, not before.

| Part | Where |
| --- | --- |
| Station HTTP server | `vxl.station.http` |
| Feed (exists) | `vxl.station.feed` |
| Feed proxy, Python | `vxl.station.proxy` |
| Feed proxy, Rust | `proxy/`, workspace member `vxl-proxy` (maturin, `bindings = "bin"`) |
| Share service | `vxl.station.share` |
| Lab server | `vxl.lab`; its own package only when a lab server must install without the station |
| Lab browser app | `web/lab/`, on `@voxel/kit` |
| CLI | `vxl/cli/station.py` (exists), `vxl/cli/lab.py` |
| Station browser app (new) | `web/app/`; the legacy `web/station/` stays until it is removed |

The station parts sit under `vxl.station` because they run only under `vxl station start`.

## Open

- **1 process or several.** Whether the station's HTTP runs in the station process or as its own process that talks
  to it (for example over ZMQ). This note assumes the station process serves HTTP itself.
- **How processes are started and watched:** child processes of `vxl station start`, or a process manager. What
  happens when the proxy or the share service dies while the station runs.
- **Settings:** the names of the `proxy:` and `share:` sections, and where the station's own address goes.
- **Login and who may see what:** later, with the lab.
