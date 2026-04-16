# Camera Preview Flow Documentation

This document describes the execution flow when the rig calls `camera.start_preview()` on a camera service, including the tile-based preview system.

## Architecture Overview

- **Rig Process**: Orchestrates multiple cameras, runs preview hub
- **Camera Service Process**: One per camera, handles device control
- **Communication**: ZMQ sockets (REQ/REP for RPC, PUB/SUB for frames/tiles)
- **Threading**: asyncio event loop + ThreadPoolExecutor (4 workers) for blocking SDK calls and parallel tile generation

## Preview System Design

### Tile Pyramid

The preview system generates two types of output per camera frame:

1. **Overview Frame** (`preview` topic): Full sensor downsampled to ~1024px. Always sent. Carries histogram for auto-levels. Used as rendering fallback.
2. **Tiles** (`preview_tile` topic): Grid of smaller images at the appropriate resolution for the current viewport zoom level. Used for sharp rendering during pan/zoom.

```
Scale 0: (implicit) — the overview frame covers this
Scale 1:  2x2   grid — each tile covers 1/2 of sensor per axis
Scale 2:  4x4   grid — each tile covers 1/4 of sensor per axis
Scale 3:  8x8   grid — each tile covers 1/8 of sensor per axis
Scale 4: 16x16  grid — each tile covers 1/16 of sensor per axis
Scale 5: 32x32  grid — near-native resolution tiles
```

### Viewport Model

The viewport `{x, y, w, h}` defines the visible sensor region in normalized coordinates [0, 1]:

- `x, y`: top-left corner of the visible region
- `w, h`: width and height of the visible region (1.0 = full sensor, smaller = zoomed in)

The backend is **canvas-agnostic** — it picks the tile scale based on the viewport and sensor dimensions only, not the client's display size.

### Scale Selection

`select_scale(viewport, sensor_w, sensor_h, tile_size)` picks the pyramid scale:

- Prefers finer resolution (`math.ceil` for ideal scale)
- Allows one level beyond the strict no-upsample threshold (tiles at that level output at native resolution, smaller than `tile_size`)
- At full viewport (no zoom), returns scale 1 (2x2 grid)

### Parallel Tile Generation

`PreviewGenerator` uses a `ThreadPoolExecutor` with 4 workers. On each raw frame:

1. Overview generated in one worker, sent immediately
2. Visible tiles (+ 1-tile neighborhood padding) generated in parallel across workers
3. Tiles sent progressively via `asyncio.as_completed` as each completes
4. All expensive operations (numpy slicing, cv2.resize, JPEG encode) release the GIL

### Viewport Change Reprocessing

When a viewport update arrives between camera grabs, `reprocess_viewport()` immediately regenerates tiles from the cached raw frame (`_current_frame`) without waiting for the next camera grab. This halves perceived latency during panning.

## Complete Flow: `camera.start_preview()`

### Phase 1: RPC Request (Rig -> Camera Service)

```
[Rig Process]
|- rig calls: await camera_handle.start_preview(trigger_mode, trigger_polarity)
|- CameraHandle serializes command via RPC
|- Sends ZMQ REQ message
|- Blocks waiting for ZMQ REP response
```

### Phase 2: Camera Service Receives Command

```
[Camera Service Process - Event Loop Thread]
|- DeviceAgent receives command via REQ/REP
|- Calls: await CameraController.start_preview(trigger_mode, trigger_polarity)
```

### Phase 3: start_preview() Executes

```
[Camera Service Process - Event Loop Thread]
|- Validation: if mode != IDLE: raise RuntimeError
|- arm camera (executor thread - blocks for SDK calls)
|- start camera acquisition (executor thread)
|- mode = PREVIEW, frame_idx = 0
|- create _preview_task = asyncio.create_task(_preview_loop())
|- return "preview" (topic name)
```

### Phase 4: Preview Loop Runs

```
[Camera Service Process]
|- _preview_loop():
|  while mode == PREVIEW:
|    |- frame = await _run_sync(device.grab_frame)  # executor thread, blocks until frame
|    |- await _previewer.new_frame(frame, idx)
|    |   |
|    |   |- [Worker Thread 1] _generate_overview(frame, idx)
|    |   |   |- cv2.resize to target_width (1024px)
|    |   |   |- compute 1024-bin histogram
|    |   |   |- _apply_processing (levels + colormap)
|    |   |   |- JPEG encode
|    |   |   -> frame_sink(PreviewFrame) -> publish("preview", packed)
|    |   |
|    |   |- select_scale(viewport, sensor_w, sensor_h)
|    |   |- compute_visible_tiles(viewport, scale, padding=1)
|    |   |
|    |   |- [Workers 1-4 in parallel] _generate_tile(frame, idx, viewport, scale, col, row)
|    |   |   |- numpy slice raw_frame[y0:y1, x0:x1]  (O(1) view)
|    |   |   |- cv2.resize to tile_size (512px max, capped to raw region)
|    |   |   |- _apply_processing (levels + colormap)
|    |   |   |- JPEG encode
|    |   |   -> tile_sink(PreviewTile) -> publish("preview_tile", packed)
|    |   |
|    |   |- tiles sent progressively via asyncio.as_completed
|    |
|    |- frame_idx += 1
|    |- loop continues
```

### Phase 5: Frame Distribution (Rig -> Clients)

```
[Rig Process - RigPreviewHub]
|- Subscribed to both "preview" and "preview_tile" topics per camera
|- _make_callback(camera_id, topic) creates topic-aware callback
|- callback(data) -> frame_callback(topic, channel, data)

[Web Service - RigService]
|- _distribute_frames(topic, channel, packed_data)
|   |- wire_topic = "preview/frame" if topic == "preview" else "preview/tile"
|   |- envelope = JSON {"topic": wire_topic, "channel": channel}
|   |- broadcast(envelope + "\n" + packed_data)

[WebSocket Clients]
|- Receive hybrid binary message: JSON envelope + newline + msgpack
|- Decode JPEG to ImageBitmap
|- Dispatch to PreviewState handlers
```

### Phase 6: Viewport Update (Client -> Backend)

```
[Frontend]
|- User pans/zooms -> compute viewport {x, y, w, h}
|- Throttle (100ms) -> client.updateViewport(x, y, w, h)
|- WebSocket: {"topic": "preview/viewport", "payload": {x, y, w, h}}

[Web Service]
|- RigService._handle_preview_viewport(payload)
|- rig.update_preview_viewport(viewport)
|- Broadcasts to all streaming cameras in parallel

[Camera Service]
|- CameraController.update_preview_viewport(viewport)
|- _previewer.reprocess_viewport(viewport)
|   |- viewport = new viewport
|   |- if _current_frame exists:
|   |   |- regenerate tiles from cached raw frame immediately
|   |   |- (overview NOT regenerated - only tiles)
|   |- tiles sent to frontend without waiting for next camera grab
```

## Data Models

### PreviewViewport

```python
class PreviewViewport(SchemaModel):
    x: float  # top-left X [0, 1]
    y: float  # top-left Y [0, 1]
    w: float  # width (0, 1]
    h: float  # height (0, 1]
```

### PreviewInfoBase (shared fields)

```python
class PreviewInfoBase(SchemaModel):
    frame_idx: int
    width: int          # output pixel width
    height: int         # output pixel height
    full_width: int     # sensor width
    full_height: int    # sensor height
    levels: PreviewLevels
    fmt: PreviewFmt     # jpeg, png, raw, zlib
    colormap: str | None
```

### PreviewFrameInfo (overview)

Extends `PreviewInfoBase` with:
- `histogram: list[int] | None` — 1024-bin histogram for auto-levels

### PreviewTileInfo (tile)

Extends `PreviewInfoBase` with:
- `scale: int` — pyramid scale (1 = 2x2, 2 = 4x4, etc.)
- `col: int` — tile column index
- `row: int` — tile row index
- `viewport: PreviewViewport` — the viewport that triggered this tile set

## Concurrency Details

### What Runs Concurrently

1. **Camera SDK calls** - Different cameras in different processes, each with executor threads
2. **Preview loops** - Each camera has its own `_preview_loop()` task
3. **Tile generation** - 4 executor workers generate tiles in parallel per camera
4. **RPC command handling** - Command loop continues accepting commands during preview
5. **Frame publishing** - Non-blocking ZMQ PUB sends
6. **State publishing** - Camera property streaming continues

### What Blocks

1. **Individual SDK calls** - Block their executor thread (but not event loop)
2. **Frame grab** - Blocks one executor thread until camera has next frame ready
3. **Tile generation** - Each tile blocks one executor thread (~2-3ms per tile)

### What Doesn't Block

1. **Asyncio event loop** - Always free to handle other tasks
2. **Other cameras** - Each camera runs in a separate process
3. **Preview publishing** - Non-blocking ZMQ send
4. **Viewport updates** - Processed immediately, tiles regenerated from cache

## Performance Characteristics

### Tile Generation Budget

For a 14000x10500 sensor with `tile_size=512`:

| Scale | Grid | Tiles per axis | Raw px per tile | Output px | Downsample |
|-------|------|----------------|-----------------|-----------|------------|
| 1 | 2x2 | 2 | 7000 | 512 | 13.7x |
| 2 | 4x4 | 4 | 3500 | 512 | 6.8x |
| 3 | 8x8 | 8 | 1750 | 512 | 3.4x |
| 4 | 16x16 | 16 | 875 | 512 | 1.7x |
| 5 | 32x32 | 32 | 437 | 437 | ~native |

Visible tiles per frame: ~16 (4x4 viewport + 1-tile padding)
Generation time per tile: ~2-3ms
Total with 4 workers: ~12ms (fits in 5-15fps budget)

### Bandwidth

Per frame per channel:
- Overview: ~200KB (1024px JPEG)
- Tiles: 16 x ~40KB = ~640KB
- Total: ~840KB at ~15fps = ~12MB/s per channel

## State Transitions

```
          start_preview()
IDLE ──────────────────────> PREVIEW
  ^                            |
  |     stop_preview()         |
  <────────────────────────────┘
         |
         | During PREVIEW:
         |   update_preview_viewport() -> reprocess tiles
         |   update_preview_levels()   -> affects next frame
         |   update_preview_colormap() -> affects next frame
```

## Thread Safety

- **Event Loop Thread**: Handles all async operations (commands, preview loop, state updates)
- **Executor Threads (4)**: Handle blocking SDK calls and tile generation
- **ZMQ I/O Threads**: Handle socket communication (managed by ZMQ internally)

All state mutations happen in the event loop thread. The executor threads only read shared state (`viewport`, `levels`, `_lut`) which is safe due to Python's GIL for simple attribute reads. `_current_frame` is a numpy array reference — assignment is atomic under the GIL.
