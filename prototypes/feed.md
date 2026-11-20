# Station feed with topics

Agreed on 2026-11-17, not built. For the web layer, after the acquisition capture in `spim.Microscope`.

## Why

`StationFeed` sends a **complete** `StationFeedView` to every connection on **every** change (`_view_unlocked()` in
`src/vxl/station/feed.py`). The view holds the whole instrument view: `config` (fixed for the session), `state` and
`default_state` (2 full copies of profiles and tasks), every device's properties, `live`, `history`, and so on. The
old feed (`station_legacy`) did the same, with even more in it (`planned_volumes`, `profile_fovs`).

So 1 changed reading, such as a camera's buffer count, resends everything. How a reading travels today:

1. The device controller polls each stream tier (fast 0.05 s by default, normal 1 s, slow 10 s; the area camera
   sets fast to 0.5 s) and publishes only the properties that changed (`props.update`).
2. The handle (`DeviceProps._adopt`) merges them into its cache, notifies the `PropView`s that changed, then its
   subscribers with a deep copy of **all** of the device's properties.
3. The HAL (`_show_props`) builds a new `DeviceView` for that device and replaces `device_views`.
4. The instrument view (`Computed`) rebuilds the whole view; the feed sends it whole.

## Topics

A **topic** is a field of the view; a map keyed by id is split 1 level, per id. No hand-made groups: a new field,
such as one an instrument kind adds, is a topic by existing. Each view field already has its own source in
`_view_sources()`, so the feed knows which topic changed without comparing views.

Station topics: `station` (id and name, only in a full message), `status`, `error`, `session` (its id and instrument
name, or `null`).

Instrument topics, for SPIM:

| Topic | Sent |
| --- | --- |
| `instrument.config` | only in a full message: fixed for the session |
| `instrument.state.<field>`, with `instrument.state.profiles.<id>` per profile | on edits |
| `instrument.default_state.<field>`, split the same way | on edits |
| `instrument.history`, `instrument.active_profile`, `instrument.power_mode`, `instrument.activities`, `instrument.remote_stores` | when they change |
| `instrument.live` (planes, stream revision), `instrument.alerts` | when what they come from changes |
| `instrument.preview_channels` | a SPIM field |
| `instrument.devices.<id>` | per device, when its properties change |

Rename on the way: the view field `device_views` becomes `devices` (`InstrumentView`, `_view_sources()`). The HAL
keeps `device_views`, since its other names give handles.

"Feed topics" are not rigup's device topics (`live`, `props.update`); the dotted form keeps them apart. Say so in the
feed's docstring and in `src/vxl/live/live.md`.

## Messages

2 websockets, as now: state and live frames. Different rules (state never drops, frames keep only the newest), and
neither blocks the other. Both share 1 envelope and 1 merge rule.

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
  frame: <VXLF bytes>           # the camera's packet, unopened
```

- `channel_id` goes away: it has held a camera id since channels were keyed by name.
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
  most 1 value per topic, so a connection is never cut for being slow (today it is dropped with `FeedLaggedError`).
  A connection must never silently miss a message.
- **The client** keeps the last value of each topic, applies messages in order, starts over on `full: true`, and
  rebuilds its typed view from the topics.
- **Frames and state stay linked** by each frame's `state` cursor, the feed's global sequence number. A client that
  sees only some topics still sees numbers that only go up.

## Later

- **Per-screen subscription:** a screen subscribes to the topics it shows, such as the preview window to
  `instrument.live`, `instrument.preview_channels` and its cameras' `instrument.frames.<camera>`. The biggest gain is
  on the frame socket: today every client gets every camera's frames.
- **Stage position when the relay starts:** read each axis once (`position.get()`) when the instrument opens, so a
  frame's position is only unknown when an axis really fails.

## Issues in the view

- `vxlib.issues`: `Issue`, `Problem(Issue)` (setup data, always an error, refuses an open or an edit) and
  `Alert(Issue)` (wrong now, started at `since`, ends by itself). Built.
- Alerts are worked out in the core as a `Computed` over cached state, and go out as `instrument.alerts`. Not built.
- "A camera sends no frames" needs a watchdog in the relay that keeps a set of stalled cameras (a `Cell`) as 1 more
  trigger. Prototype it first, to see how much code it adds.
- The app keeps its own request failures (`request.failed`, `action.failed`, `command.failed`) as a separate feature,
  and adds actions, such as Restore, to alert rows.
