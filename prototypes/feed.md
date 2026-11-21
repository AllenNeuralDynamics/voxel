# Station feed with topics

Agreed on 2026-11-17. **Built** on 2026-11-20, all in `src/vxl/web/` since 2026-11-21: the messages and the
publisher (`feed.py`), the station's topics (`station/topics.py`), the 2 sockets (`sockets.py`) and the reader
(`client.py`), tested in `tests/web/`. Not built: the written spec, and a typed view on the reader's
side. The feed is spoken at each hop: service → server → window (`server.md`).

## Why

Until 2026-11-20, `StationFeed` (`src/vxl/station/feed.py`, deleted) sent a **complete** `StationFeedView` to every
connection on **every** change. The view holds the whole instrument view: `config` (fixed for the session), `state` and
`default_state` (2 full copies of profiles and tasks), every device's properties, `live`, `history`, and so on. The
old feed (`station_legacy`) did the same, with even more in it (`planned_volumes`, `profile_fovs`).

So 1 changed reading, such as a camera's buffer count, resent everything. How a reading travels to the view:

1. The device controller polls each stream tier (fast 0.05 s by default, normal 1 s, slow 10 s; the area camera
   sets fast to 0.5 s) and publishes only the properties that changed (`props.update`).
2. The handle (`DeviceProps._adopt`) merges them into its cache, notifies the `PropView`s that changed, then its
   subscribers with a deep copy of **all** of the device's properties.
3. The HAL (`_show_props`) builds a new `DeviceView` for that device and replaces `device_views`.
4. The instrument view (`Computed`) rebuilds the whole view; the old feed sent it whole.

## Topics

A **topic** is a field of the view; a map keyed by id is split 1 level, per id. No hand-made groups: a new field,
such as one an instrument kind adds, is a topic by existing. Each view field already has its own source in
`_view_sources()`, so the feed knows which topic changed without comparing views.

Station topics: `station` (id and name, only in a full message), `status`, `error`, `session` (its id and instrument
name, or `null`), the acquisition topics and `log` (below).

Instrument topics, for SPIM:

| Topic | Sent |
| --- | --- |
| `instrument.config` | only in a full message: fixed for the session |
| `instrument.state.<field>`, with `instrument.state.profiles.<id>` per profile | on edits |
| `instrument.default_state.<field>`, split the same way | on edits |
| `instrument.history`, `instrument.active_profile`, `instrument.power_mode`, `instrument.activities`, `instrument.remote_stores`, `instrument.metadata_schema`, `instrument.operation` | when they change |
| `instrument.live` (planes, stream revision), `instrument.alerts` | when what they come from changes |
| `instrument.preview_channels` | a SPIM field |
| `instrument.devices.<id>.interface` | only in a full message: fixed for the session |
| `instrument.devices.<id>.props.<name>` | per property, when it changes |

The view field is `devices` (`InstrumentView`, `_view_sources()`). The HAL keeps `device_views`, since its other
names give handles.

"Feed topics" are not rigup's device topics (`live`, `props.update`); the dotted form keeps them apart. The docstring
of `vxl.web.feed` and `src/vxl/live/live.md` say so.

### Records and log topics

Decided and built on 2026-11-20.

- **The acquisition that ran last:** `acquisition.<field>` and `acquisition.visits.<index>`, in the form of
  `acquisition.json` (`Acquisition.for_readers()`), from `AcquisitionStore.subscribe`. A progress save sends 2 small
  topics, the revision and the visit that runs; the frozen config and state go out 1 time. Past acquisitions are not
  on the feed: they come from the server's records history.
- **The log:** 1 topic, `log`, whose value is the newest line with its `seq`, from `LogJournal.subscribe`. A reader
  adds the line when its `seq` is the next one, and gets the lines it missed from the server's records history. So
  "the newest value wins" holds, and no line is lost. Rejected: a message kind that only adds, which needs a second
  merge rule and has no limit on what waits for a slow reader.

### How a change is found

Decided on 2026-11-20. `StationTopics` listens to `Station.view` only. On each change it lists the view's parts by
topic (`_view_parts`) and compares each with the last one: an unchanged part is the same object, so the check stops at
once. The view's own serializer then writes only the changed topics, since a topic's name is its path in the view
(the topics, put back together, equal the whole view). Rejected: listening to each source of `_view_sources()`. It
needs a public door on `Instrument` and on `Station` and a second path next to the station view, and `state` and
`devices` are 1 source each, so their parts still need the compare.

A map with no entries, such as the properties of a device that has none, has no topic; a reader takes it as empty.

Measured on the simulated `z-step.yaml` (16 devices) with 1 topic for each device (43 topics), for each change of
the view: 30 µs to find what changed (21 µs when listening to each source), 68 µs to write the changed topics as
JSON, and 1.4 ms to write the whole view as the old feed did. Building the instrument view and the station view again,
before the feed, takes 23 µs.

### Device topics

Decided and built on 2026-11-20, from a measurement: a device is 1 topic for its interface and 1 for each property.
With 1 topic for each device, a camera's topic was 22.2 kB, of which 19.7 kB was the interface, which never changes
in a session; and a generator's was 463.5 kB once a cycle was loaded, since its `loaded` property holds the cycle as
a list of volts (`tuning-knobs.md` › Related findings).

| Split | Topics | Find what changed | 1 camera property changes | 1 small generator property changes |
| --- | --- | --- | --- | --- |
| 1 topic for each device | 43 | 6.6 µs | 22.2 kB, 101 µs to write | 463.5 kB, 1690 µs |
| interface + props | 59 | 7.4 µs | 2.5 kB, 16 µs | 459.8 kB, 1659 µs |
| interface + 1 topic for each property (built) | 151 | 18.2 µs | 0.1 kB, 3 µs | 2.8 kB, 19 µs |

Still large: `instrument.devices.<generator>.props.loaded`, about 460 kB, goes out each time a cycle loads. It is a
candidate for bytes, or for a cycle that is not a property.

## Every hop

- **Services** (the station, the lab) send 1 feed to their server. A server sends the same feed on to windows and to
  other readers. A reader cannot tell if it reads a service or a server.
- **The feed is a written spec**, so a server in another language can speak it: envelope, frame message, topic
  names, version, and the HTTP routes it passes on. The Python types in `vxl.web.feed` follow the spec.
- **Topic names are global, and the publisher adds its own prefix** (decided 2026-11-20): the station always
  publishes `stations.<id>.<topic>`, the lab `lab.<topic>`. A server never renames a topic; it only caches, merges
  and filters, so 1 service behind a server and several behave the same. A station window strips the
  prefix it knows. The topics below are written without the prefix.
- **`vxl.web.client`** connects any Python caller (Qt, notebooks, scripts, tests, the lab service) to a server.
- **The publisher has no transport** (`FeedPublisher`): `publish` sends the topics that changed, `replace` sends 1
  full message, and `connect()` and `connect_frames()` give the messages for 1 reader.
- **`FeedRelay`** is the part of the publisher that gives ready messages to every reader, unchanged: the last value
  of each topic, and 1 merged message for a slow reader. `FeedPublisher` is a relay that also makes the messages.
  The server uses a relay alone, so the service's cursors pass as they are.
- **`FeedSockets`** serves a relay on 2 WebSockets, `<prefix>/feed/state` (JSON text) and `<prefix>/feed/frames`
  (VXFP packets), as routes for any Starlette or FastAPI app. A message is written 1 time for the readers that get
  it together. **`Listener`** serves an app on 1 address inside the running event loop.
- **`FeedClient`** reads both sockets of 1 service, from the service or from its server, and connects again by
  itself. It gives the messages; a caller keeps the topics with `merge`.

## Messages

2 WebSockets for each service that a window watches: state and live frames (decided 2026-11-20; before, "2 per window").
The address names the service, as the HTTP routes do: `/api/stations/<id>/...` and `/api/lab/...`. So a cursor is always
1 service's own, a frame's `state` link holds at each hop, and `full` means every topic of that service. A station
window opens 2 sockets on the station's server. The lab page opens 2 on the lab's server, since the lab service
publishes each station's small topics as lab topics (`lab.md`). A Preview window opens its own 2, subscribed only to
what it shows. Different rules (state never drops, frames keep only the newest), and neither blocks the other. Both
share 1 envelope and 1 merge rule (`StateMessage.merge`, `FrameMessage.merge`).

Measured for the sockets on 2026-11-20 (20 publishers, each 10 messages of 500 bytes a second, both ends in 1 Python
process): 1 socket for all against 1 socket each costs 2.3 % against 3.8 % CPU, the same delay (about 1 ms), and
about 120 kB of memory for each idle socket. Not measured: real browsers, TLS, a real network.

```yaml
# both sockets
cursor: {stream_id, seq}        # this socket's own order; the frame socket gains a stream id
sent_at_unix_us: ...
topics: {...}                   # topic -> value; null removes the topic

# state socket only
full: false                     # true: every topic is here, and the client starts over from this message
```

State topic values are pieces of the view. A frame topic is `instrument.frames.<camera>.<layer>`, and its value is:

```yaml
instrument.frames.camera.overview:
  state: {stream_id, seq}       # the state this frame belongs to (was state_cursor)
  position_um: {x, y, z}        # null only when the stage position is unknown
  frame: <VXSF bytes>           # the camera's packet, unopened
```

- On the wire, a state message is JSON text and a frame message is a `VXFP` packet (Voxel frame packet): the 9-byte
  prefix (magic, version 1, header length), a MessagePack header with the envelope and each topic's `state`,
  `position_um` and `frame_byte_length`, then the frames in the order of the header's topics (`FrameMessage.pack`).
  Each frame is a `VXSF` packet (Voxel source frame; `VXLF` until 2026-11-20). The legacy apps keep their own packet,
  `VXLP` (`vxl._legacy.live`); a reader of 1 packet refuses the other by its magic. VXFP is for camera frames only;
  other data that needs bytes later, such as a generator's cycle, changes the header then.
- Names considered for the packet: `VXLP` version 2 (1 name for 2 shapes, and a version 2 left without a version 1
  when legacy goes), `VXLM`, and `VXLFP` (5 bytes, and its first 4 are the frame's magic).
- `channel_id` is gone: it had held a camera id since channels were keyed by name.
- The layer is the last part of the topic, so the latest-only queue's key is the topic, and a screen can subscribe
  to 1 layer (a thumbnail wants only `overview`).
- A frame message usually holds 1 topic; more only when frames were waiting for a slow client. Nothing waits to be
  bundled.
- Only the state socket needs `full`: there a missing topic means "unchanged", and after a reconnect or a session
  change it must mean "gone". Old frames are cleared by the state (a new session, or a higher `stream_revision`),
  through each frame's `state` link.

## Rules

- **1 step, 1 message.** `Computed` values recompute in the same step as their trigger, so a state change and what
  is derived from it go out together. Reactions that run later, such as new streams after the planes change, go out
  as their own later message.
- **A full message:** on connect, on reconnect, and on every session change.
- **Slow clients:** the feed merges what waits for a connection, keeping the newest value per topic. A backlog is at
  most 1 value per topic, so a connection is never cut for being slow (`FeedConnection`; `FeedLaggedError` is gone).
  A connection must never silently miss a message. A fast reader can also get 2 messages merged into 1.
- **The client** keeps the last value of each topic, applies messages in order, starts over on `full: true`, and
  rebuilds its typed view from the topics.
- **Frames and state stay linked** by each frame's `state` cursor, the feed's global sequence number. A client that
  sees only some topics still sees numbers that only go up.
- **A number that is not finite is `null`.** JSON has no `NaN` or `Infinity` (RFC 8259 §6), so the publisher sends
  `null` in its place, at any depth. A topic whose whole value is such a number is removed.
- **A frame holds at least 1 byte,** and a relay refuses a frame message that does not come after the last one of
  its stream, as it does for a state message.

## Later

- **Per-screen subscription:** a screen subscribes to the topics it shows, such as the preview window to
  `instrument.live`, `instrument.preview_channels` and its cameras' `instrument.frames.<camera>`. The biggest gain is
  on the frame socket: today every client gets every camera's frames.
- **Stage position when `LiveRelay` starts:** read each axis once (`position.get()`) when the instrument opens, so a
  frame's position is only unknown when an axis really fails.

## Issues in the view

- `vxlib.issues`: `Issue`, `Problem(Issue)` (setup data, always an error, refuses an open or an edit) and
  `Alert(Issue)` (wrong now, started at `since`, ends by itself). Built.
- Alerts are worked out in the core as a `Computed` over cached state, and go out as `instrument.alerts`. Built
  (2026-11-20), with `instrument.operation`, the name of the operation that runs now; see `TODO.md`.
- "A camera sends no frames" needs a watchdog in `LiveRelay` (`vxl.instrument.live`) that keeps a set of stalled cameras (a `Cell`) as 1 more
  trigger. Prototype it first, to see how much code it adds.
- The app keeps its own request failures (`request.failed`, `action.failed`, `command.failed`) as a separate feature,
  and adds actions, such as Restore, to alert rows.
