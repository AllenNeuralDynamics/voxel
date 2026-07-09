# Camera preview

This document describes how the live preview is produced and delivered — from a raw camera frame to
pixels on the web canvas and the Qt panel. The design rationale (and the history of the tile-based
system this replaced) lives in `notes/preview_viewport_first_plan.md`.

## Overview

Preview is **rendered server-side** (levels + colormap are applied on the camera, "the camera is the
renderer") and delivered to clients as **two coherent images per channel**:

| Layer | Topic | Role | Cadence |
|-------|-------|------|---------|
| **Overview** | `preview` | Full sensor, downsampled to `DEFAULT_PREVIEW_WIDTH` (~1500 px), with a 1024-bin histogram. The always-present backdrop and the fallback when a pan/zoom exceeds overscan. | every frame |
| **Viewport image** | `preview_view` | One coherent image of the zoomed region (expanded by overscan), rendered/cropped/resampled/level-mapped/colormapped as a **single unit** at up to `RENDER_CAP` px. | every frame while zoomed |

There are no tiles: the viewport is one image, so there are no seams, no per-tile tone differences, and
no discrete scale-stepping. Both layers are ordinary `PreviewFrame`s (same wire envelope); the viewport
image is distinguished only by its `info.rect` (the sub-region it covers). At a full (unzoomed) viewport
no viewport image is sent — the overview already covers it.

## Architecture

- **Instrument** (`vxl.instrument.Instrument`) orchestrates the active profile's cameras and owns the
  preview fan-out (`Instrument.frames`, `Instrument.views` — `Emitter[tuple[channel_id, packed_bytes]]`).
- **Camera** (`vxl.camera`) runs device control + `PreviewGenerator` in its own service (in-process for
  local rigs, a remote node over ZMQ for distributed rigs). It publishes on the rigup pub/sub topics
  `preview` and `preview_view`.
- **Web** (`vxl_web.live.InstrumentFeed`) bridges the instrument's emitters onto the WebSocket bus.
- **Qt** (`vxl_qt.preview`) consumes the instrument's emitters directly.
- **Threading**: an asyncio event loop per camera service + a `ThreadPoolExecutor` for the blocking
  numpy/OpenCV work (crop, resample, encode), so the event loop is never blocked.

## Viewport model

`PreviewViewport {x, y, w, h}` is the visible sensor region in normalized coordinates `[0, 1]`
(`x, y` = top-left, `w, h` = size; `1.0` = full sensor, smaller = zoomed in). It is a shared,
last-writer-wins state — one operator drives, other clients follow.

Clients express the viewport in **stage-normalized** coordinates. The instrument inverse-rotates it into
each camera's **sensor-normalized** frame via `PreviewViewport.to_sensor_space(rotation_deg)` before
handing it to that camera (`Instrument._apply_viewport`), so a rotated camera crops the correct region.
`rotation_deg` comes from the channel's detection config.

## Camera-side generation (`PreviewGenerator`)

On each raw frame, `new_frame()` dispatches two independent jobs:

- **Overview** — `_generate_overview`, **skip-if-busy**: if the previous overview hasn't finished, this
  frame's overview is dropped rather than queued. Downsamples the full sensor to `target_width`, computes
  the histogram on the resized data (pre-levels), applies levels + colormap, encodes. Sent every frame.
- **Viewport image** — `_generate_and_send_view` → `_generate_view`, **cancel-stale / latest-wins**: a
  new frame or viewport supersedes any in-flight render (`cancel_view_task`), so a fast pan never builds
  a backlog. No-op at a full viewport.

`_generate_view` is the single-image core:

1. `rect = viewport.expanded(OVERSCAN_MARGIN)` — grow the crop so small pans stay covered.
2. crop the raw frame to `rect` (clamped to sensor bounds).
3. resample **once** to `min(crop_px, RENDER_CAP)` (aspect-preserving) via `_downsample` (stride-based
   nearest — fast, GIL-releasing).
4. `_apply_processing` **once** — normalize by dtype max, apply `PreviewLevels` clip/stretch → uint8,
   apply the cached colormap LUT.
5. encode **once** (`PreviewFmt`, currently lossless PNG) and publish on `preview_view` with the exact
   rendered `rect` in `info`.

Rendering once (not per tile) is what removes seams and tone discontinuities. All heavy work runs on the
`ThreadPoolExecutor`; the last raw frame is cached (`_current_frame`) so an idle re-pan/re-level
re-renders from it without a recapture (`reprocess`, `reprocess_viewport`).

## Distribution: camera → clients

```
[Camera service]
  PreviewGenerator ── publish("preview", PreviewFrame.pack()) ─────────┐   (overview, every frame)
                   └─ publish("preview_view", PreviewFrame.pack()) ─────┤   (view, when zoomed)
                                                                        v
[Instrument]  _subscribe_camera(cam):
  camera.subscribe("preview",      forward_frames) -> self.frames.emit((channel_id, data))
  camera.subscribe("preview_view", forward_views)  -> self.views.emit((channel_id, data))

[Web: InstrumentFeed]                          [Qt: PreviewStore.start_feed]
  i.frames -> bus.broadcast("preview.frame.{ch}")  i.frames -> _on_frame -> set_frame
  i.views  -> bus.broadcast("preview.view.{ch}")   i.views  -> _on_view  -> set_view
                    |                                             |
              [WebSocket clients]                          (same process)
```

The payload is `msgpack{"info": PreviewFrameInfo, "data": <encoded image bytes>}`. Clients decode the
image (JPEG/PNG → `ImageBitmap` / `QImage`) **off the render/UI thread**.

## Control: clients → camera

Viewport / levels / colormap changes travel back over one inbound channel:

```
[Client] pan/zoom/level/colormap (throttled ~200 ms) -> send "preview.update" {viewport?, levels?, colormaps?}

[Web: InstrumentFeed._on_preview_update]
  -> instrument.update_viewport / update_levels / update_colormaps
  -> bus.broadcast("preview.updates", cmd, exclude=client_id)   # echo to *other* viewers (follow semantics)

[Instrument._apply_viewport / update_levels / update_colormaps]
  -> per active-profile camera: ch.camera.preview_viewport / preview_levels / preview_colormap  (Coalescers)
  -> drain to RPC update_preview_viewport / _levels / _colormap on the CameraController
  -> PreviewGenerator: store for the next frame, or reprocess the cached frame immediately when IDLE
```

The sender is excluded from the `preview.updates` echo so its own optimistic local state isn't fought.
Cross-viewer sync rides entirely on `preview.updates`; the viewport image's `rect` is a *render* region
(overscan-expanded), not a viewport, and is never adopted as one.

## Client rendering

Both clients hold, per channel: the **overview** image and the **latest viewport image + its `rect`**
(latest-wins by `frame_idx`). Compositing (`compositeViewFrames` on web, `PreviewPanel._composite` on Qt,
kept as mirrors of each other):

1. Contain-fit the rotation-aware channel bounding box into the canvas, scaled by the live `viewport`.
2. Draw the **overview** across the full sensor footprint (the never-blank floor).
3. Draw the **viewport image** positioned by its `rect` (sensor → stage via the channel rotation), on top.
4. Composite channels additively (`lighter` / `CompositionMode_Plus`) over black.

Because content is positioned in sensor space under the *live* viewport transform, the last viewport
image **tracks pan/zoom** (showing its overscan margin) until a fresh render lands; beyond the overscan
the overview shows through — never blank. Nearest-neighbor sampling while interacting, smooth when
settled; repaints are coalesced (~16 ms on Qt; a `requestAnimationFrame` loop on web).

## Data models (`preview.py`)

```python
class PreviewViewport(SchemaModel):      # normalized visible/rendered region
    x: float; y: float                   # top-left [0, 1]
    w: float; h: float                   # size (0, 1]
    def expanded(self, margin) -> PreviewViewport      # grow about center (overscan), clamped
    def to_sensor_space(self, rotation_deg) -> PreviewViewport

class PreviewInfoBase(SchemaModel):      # shared frame metadata
    frame_idx: int
    width: int; height: int              # rendered pixel dims
    full_width: int; full_height: int    # full sensor dims
    levels: PreviewLevels
    fmt: PreviewFmt                       # jpeg | png (live; png today) · raw | zlib (deferred 16-bit paths)
    colormap: str | None

class PreviewFrameInfo(PreviewInfoBase): # overview *and* viewport image
    rect: PreviewViewport                # rendered region: full frame (overview) or sub-rect+overscan (view)
    histogram: list[int] | None          # 1024-bin, overview only (None on the view)

@dataclass(frozen=True)
class PreviewFrame:                      # the wire payload for both topics
    info: PreviewFrameInfo
    data: bytes                          # encoded image
    # from_array / pack / from_packed  (msgpack + msgpack_numpy)

class PreviewLevels(SchemaModel):        # black/white points, [0, 1]
    min: float; max: float
    @classmethod def from_histogram(cls, histogram, percentile=1.0) -> PreviewLevels
```

## Concurrency & thread safety

- **Event loop (per camera service)**: all async work — RPC commands, the preview loop, property streaming.
- **Executor threads**: the overview render (1 dedicated worker, skip-if-busy) and the viewport render
  (crop/resample/encode); one viewport render is in flight at a time (cancel-stale supersedes the rest).
- **Cameras** run independently (separate processes when distributed).
- All state mutations happen on the event loop thread. Executor threads only *read* shared state
  (`viewport`, `levels`, `_lut`, `_current_frame`) — safe under the GIL (attribute reads; numpy-array
  reference assignment is atomic).

## Performance & WAN notes

- **Per frame per channel** (lossless PNG today): overview (~full-sensor, `DEFAULT_PREVIEW_WIDTH`) + one
  viewport image (≤ `RENDER_CAP`). One encode + one transfer + one decode per layer — no per-tile multiplication.
- **Settle latency**: after a pan/zoom settles there is one round-trip (crop + resample + level + colormap
  + encode + network + decode) before the sharp image lands. On LAN/Qt this is sub-frame; over WAN the
  ever-present overview + transform-tracked cached view cover the gap (never blank).
- **Overscan** multiplies the per-frame crop cost while live + zoomed — keep `OVERSCAN_MARGIN` tighter for
  live streaming than for idle re-pan comfort (tuning knob).
- The codec is lossless PNG (level 1 — chosen to match JPEG's bandwidth while dropping DCT artifacts).
  `PreviewFmt` also carries two deferred 16-bit paths, `raw` (uncompressed) and `zlib` (compressed uint16),
  shared with the client `fmt` vocabulary but not yet decodable there (needs a GPU upload path — design §11).
  Swapping the codec is a one-line change on this single encode path (see the plan doc, "codec swap").

## State transitions

```
          start_preview()
IDLE ───────────────────────> PREVIEW
  ^                              |
  |        stop_preview()        |
  └──────────────────────────────┘

During PREVIEW (or IDLE, via reprocess of the cached frame):
  update_preview_viewport()  -> re-render the viewport image
  update_preview_levels()    -> re-apply levels
  update_preview_colormap()  -> re-apply colormap
```
