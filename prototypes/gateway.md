# Gateway

Agreed on 2026-11-20, not built. Replaces the feed proxy and the share service (`proxy.md` and the share service of
`records.md`, 2026-11-19). See `feed.md` for the feed itself and `station.md` for how the processes fit together.

## Why

The station feed is push-only, but each client still costs the station: 1 send per client, a queue and merge for
each slow client, and 1 task per WebSocket on the event loop that runs the acquisition. The UI is for many people
on many computers, and the lab watches too.

The earlier plan had 4 kinds of links leaving the station (feed, HTTP, a lab push, a share service), and a window had
to know 2 or 3 addresses. The gateway puts all outside traffic behind 1 kind of process, at every level.

## The idea

**Publishers own state; the gateway is transport.**

- **Publishers:** the station (`vxl.station`) and the lab (`vxl.lab`). They are peers with the same shape: their main
  object, the topics they publish, and an `api` module with their FastAPI operations. Neither imports the other.
- **Gateway:** 1 kind of process, the same code everywhere. Its settings decide where it sits.
- **Every hop speaks the feed** (`feed.md`): topics over WebSocket, operations over HTTP.

```text
simple:  station ──feed──▶ gateway ──▶ windows (browser, Qt, notebooks)

lab:     station A ──▶ gateway A ──┐
         station B ──▶ gateway B ──┼──▶ gateway on the lab machine ──▶ windows, lab page
         lab ──────────────────────┘
```

- **A publisher has exactly 1 client: its gateway.** The station never fans out, even in the simple setup.
- **A window talks to 1 address:** the nearest gateway. A browser, a Qt app and a notebook are the same kind of
  client; none has its own path to the station.
- **There is no "lab gateway".** The gateway on the lab machine is an ordinary gateway with many upstreams.

## What a gateway does

1. **Topic cache:** keeps the last value of each topic from each upstream. A new window gets `full: true` from the
   cache; the publisher never sees it.
2. **Fan-out:** 1 message, many readers. A frame is shared, never copied per window. Frames keep only the newest per
   topic; state never drops (the rules in `feed.md`).
3. **1 task per window:** filters the topics the window subscribed to, and sends `full: true` from the cache when the
   window falls behind.
4. **Routing:** passes each HTTP call on to the publisher that owns it: `/stations/<id>/...` to that station's
   `vxl.station.api`, `/lab/...` to `vxl.lab.api`. It changes nothing in the call.
5. **Records history:** serves stored data from `records.sqlite3` (WAL, read-only): history, `acquisition.json`, full
   logs. It runs in its own capped process, so a query never waits on, or slows, the station.
6. **Local data:** serves image files on its own machine at `/data/...`, read-only, with HTTP Range requests, no cache
   and no changes. Remote storage (S3, MinIO, a file server) serves itself; the record holds its URL.
7. **Web app files:** serves the built browser app, since the browser knows only the gateway's address.

The gateway opens only the message envelope (topics, cursor, `full`). Frames (VXLF bytes) pass through unopened.

**A gateway never renames.** Topic names are global: the publisher adds its own prefix (`stations.<id>.`, `lab.`),
also with only 1 upstream. HTTP follows the same rule: every gateway, the local one too, serves `/stations/<id>/...`
and `/lab/...`. A window uses the same topics and paths at home and at the lab (`feed.md`).

## Upstreams

- A gateway has 1 or more upstreams. Its first upstream is the publisher on its own machine.
- It may also connect out to 1 gateway further up (`gateway.upstream`). It connects out, so it passes firewalls that
  block incoming connections, and the station decides when it joins.
- A station's gateway connects only to the lab machines listed in its settings.
- On the link up, small topics (status, run progress, alerts) always flow. Frames and other big topics flow only while
  a window further up subscribes to them. With nobody watching, no frames leave the station machine.
- When the link drops, the lower gateway reconnects by itself and the lab page shows the station as offline. The run
  does not stop.

## The station computer

```bash
uv run vxl station start
```

1. Load `~/.voxel/station.yaml`; refuse to start when it has problems.
2. Start the station in this process. Its feed end and `vxl.station.api` listen only on `127.0.0.1`.
3. Start the gateway as a child process, for example
   `vxl-gateway --upstream ws://127.0.0.1:5600 --port 8000 --records ~/.voxel/records.sqlite3 --data <storage> --web <app>`.
4. Print `Open http://<host>:8000`.
5. Watch the gateway and start it again when it stops. The run does not stop.
6. On Ctrl-C: stop the gateway, then close the station.

`vxl station start --no-gateway` runs the station headless: no windows, the run only.

## The lab computer

```bash
uv run vxl lab start
```

1. Load `~/.voxel/lab.yaml`.
2. Start the lab publisher in this process, listening only on `127.0.0.1`.
3. Start a gateway with the lab as its first upstream. It also takes station gateways that connect in, each under
   `/stations/<id>/`.
4. Print `Open http://<lab-host>:8000`.

Each station sets `gateway.upstream: wss://<lab-host>:8000` in its `station.yaml`. A window at the lab opens a station
through the lab machine; a window on the station computer uses that station's own gateway.

## Settings

```yaml
# station.yaml
gateway:
  port: 8000                      # optional, default 8000
  upstream: wss://<lab-host>:8000 # optional: the lab machine to join
  command: vxl-gateway            # optional: another gateway program, for example a Rust one
```

`lab.yaml` has the same `gateway:` section without `upstream`.

## Any gateway program

A gateway in another language (for example Rust) can replace the Python one when 4 things hold:

1. **The feed is a written spec**, not Python code: the envelope, the frame message (length, envelope, VXLF bytes),
   topic names, the version, and HTTP routing. The Python types in `vxl.feed` follow the spec.
2. **The records read schema is public.** The gateway reads `records.sqlite3` directly (`records.md`).
3. **The command-line flags are part of the spec:** `--upstream`, `--port`, `--records`, `--data`, `--web`, and the
   flags for upstreams that connect in. `vxl` starts whatever `gateway.command` names with the same flags.
4. **The gateway tests are black-box tests:** they start any gateway program, connect over sockets, and check what
   comes out.

The Rust plan from `proxy.md` (deleted in `d74219bf`, kept in git) still applies: `tokio`, `tokio-tungstenite`
upstream, `axum` for windows, `tokio::sync::broadcast` with `bytes::Bytes` for the fan-out, shipped with `maturin`
(`bindings = "bin"`).

## Measured

2026-11-20, Apple M4 Pro, Python 3.13, `websockets` 17, separate processes, 30 frames per second, 5 s per case. The
station sent frames directly to clients, or to a gateway that sent them on.

| Frame | Clients | Path | p50 | p99 | Station CPU |
| --- | --- | --- | --- | --- | --- |
| 0.5 MB | 1 | direct | 0.36 ms | 1.4 ms | 0.9 % |
| 0.5 MB | 1 | gateway | 0.63 ms | 2.3 ms | 0.9 % |
| 2 MB | 4 | direct | 2.4 ms | 7.8 ms | 10.9 % |
| 2 MB | 4 | gateway | 2.3 ms | 7.3 ms | 2.4 % |
| 8 MB | 4 | direct | 6.2 ms | 10.2 ms | 17.8 % |
| 8 MB | 4 | gateway | 8.3 ms | 12.0 ms | 5.0 % |

The local hop adds about 0.3–2 ms per frame (a frame at 30 fps lasts 33 ms). With 4 clients the station uses 3–4
times less CPU. Not covered: an acquisition running at the same time, newest-only dropping, real browsers. Measure
again when the real feed exists.

## Prior art

The same job has other names elsewhere. "Gateway" follows EPICS, the closest in our field.

- EPICS [Channel Access and PV Access gateways](https://mdavidsaver.github.io/p4p/gw.html): many clients share 1
  connection to the server that owns a value; the gateway buffers values, joins subnets and adds access control.
- WebRTC [SFU](https://bloggeek.me/webrtcglossary/sfu/): forwards each stream only to the viewers who want it, and
  can be chained.
- ROS [Foxglove bridge](https://docs.foxglove.dev/docs/connecting-to-data/ros-foxglove-bridge): robot topics to
  browsers over WebSocket. A bridge translates between 2 systems; the gateway does not translate.
- NATS [leaf nodes](https://docs.nats.io/learn/topologies/leaf-nodes): connect out to a hub and chain into trees,
  like a station gateway joining the lab machine.

## Open

- **Trust:** the lab gives each station a token, and the gateway on the lab machine checks it. To flesh out later.
- **Local data during a run:** reading the station disk that the run writes to. The gateway may refuse or slow
  `/data` reads while a run is active.
- **Login and who may see what:** later, with the lab.
- Whether the station limits how many operations it takes at once.

## Where it will live

See the table in `station.md`.
