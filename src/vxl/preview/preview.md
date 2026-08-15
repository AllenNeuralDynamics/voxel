# Camera preview

The camera preview path publishes compressed raw intensity data. Camera nodes produce source frames; they do
not render JPEGs, apply display levels, or know instrument channel IDs. The control computer routes the packed
frames without decoding or recompressing their pixels, and clients own display processing and composition.

The source-frame protocol, camera generation, Instrument channel mapping, Station delivery wrapping, Qt raw-frame
consumer, and browser worker/WebGPU consumer described here are implemented.

## Ownership and routing

Preview metadata is split at the boundary where it becomes known:

- The camera owns `camera_id`, source-stream identity, capture sequence, pixel geometry, valid bit depth, and
  encoding details.
- The `Instrument` rejects stale camera streams and maps `camera_id` to `channel_id`, then emits the packed source
  frame without decoding or wrapping it.
- `StationFeed` assigns the delivery sequence, stamps the frame against its current station-state cursor, and wraps
  the packed source frame without decoding it.
- The client owns levels, color mapping, interpolation, layer composition, and other display state.

No histogram is carried on the source frame. A client that needs one can calculate it from the decoded pixels.

Each camera capture can produce two independently replaceable layers:

| Layer | Camera topic | Instrument emitter | Station delivery | Browser delivery | Source region |
| --- | --- | --- | --- | --- | --- |
| `overview` | `preview` | `Instrument.preview` | `StationFeed.frames` | dedicated preview WebSocket | Full sensor, up to 2048 pixels wide |
| `viewport` | `preview_viewport` | `Instrument.preview` | `StationFeed.frames` | dedicated preview WebSocket | Current viewport plus overscan, up to 2048 pixels wide |

The overview stays at a constant maximum width regardless of zoom. At the full viewport there is no separate
viewport layer to generate.

## Viewport coordinates

The UI viewport is normalized to the stage view. The `Instrument` transforms it into each camera's sensor
coordinates, accounting for camera rotation, before calling `PreviewGenerator.set_viewport()`.

For a viewport layer, the generator expands that sensor-space viewport by `OVERSCAN_MARGIN`, currently 5% on
each side, and clamps it to the sensor. `source_rect_px` records the actual integer sensor footprint represented
by the pixels after expansion and clamping. It is therefore not necessarily identical to the viewport originally
requested by the UI.

The rectangle uses an inclusive floor for its origin and an exclusive ceiling for its end so partially covered
sensor pixels are not lost.

## Source-frame construction

`PreviewFrame.from_source()` performs the complete sensor-frame transformation:

1. Resolve the normalized viewport to `source_rect_px` and crop the sensor array.
2. Keep native pixels if the crop fits the target width; otherwise resize to the exact target width while
   preserving aspect ratio, using OpenCV `INTER_NEAREST_EXACT`.
3. Normalize samples to canonical little-endian, right-aligned `uint16`.
4. Byte-shuffle the samples into a low-byte plane followed by a high-byte plane.
5. Compress the shuffled bytes with Zstandard level 1 and a frame checksum.
6. Construct the camera-owned header and payload.

The current limits are `OVERVIEW_WIDTH = 2048` and `RENDER_CAP = 2048`. `valid_bits` describes meaningful
sample bits independently of the 16-bit transport container.

## Wire format

Every source frame is independently decodable:

```text
9-byte prefix | MessagePack source header | Zstandard payload
```

The prefix contains the `VXPS` magic, framing version, and MessagePack header length. The source header contains:

- source schema version and encoding identifier
- `camera_id`, `source_stream_id`, `frame_idx`, and `layer`
- optional `captured_at_unix_us`, when a true camera capture timestamp is available
- rendered `width` and `height`
- `sensor_width`, `sensor_height`, and `source_rect_px`
- `valid_bits` and uncompressed byte length

It intentionally excludes `channel_id`, histograms, levels, color maps, and display state.

`VoxelPreviewPacket` wraps that complete source packet without parsing or modifying it:

```text
9-byte prefix | MessagePack delivery header | complete VXPS source packet
```

The `VXPD` delivery header contains `delivery_schema_version`, `channel_id`, `seq`, `state_cursor`,
`stamped_at_unix_us`, and `frame_byte_length`. `state_cursor` contains the `StationFeed` stream ID and sequence.
It identifies the latest materialized station state when `StationFeed` wrapped the camera frame; the timestamp
records when that association was made. The delivery `seq` increases across wrapped frames. Sequence gaps are
expected when latest-only queues replace frames. Camera-owned fields such as `layer` are not duplicated in this
header.

`StationFeed.frames` emits the packed `VXPD` packets. Qt subscribes in process, while the web adapter forwards them
over the dedicated preview WebSocket. Consumers correlate `state_cursor` with the reliable station-state stream,
use the session identity and `preview_revision` to invalidate old display generations, and reject stale or
out-of-order frames.

Every layer, including `overview`, is positioned from `source_rect_px`. The `layer` field selects replacement
and composition behavior; it never implies that the represented rectangle covers the full sensor.

## Scheduling and backpressure

`PreviewGenerator.submit_frame()` is synchronous and non-blocking. It caches the latest raw frame, then
schedules layer generation on separate single-worker executors:

- The overview lane is skip-if-busy. If an overview is already being generated, the next overview is dropped
  instead of queued.
- The viewport lane is latest-wins. A new camera frame or viewport request cancels stale pending viewport work.
  Work already executing in its thread may finish, but its result is discarded.
- Overview and viewport generation do not block each other.

The controller also applies independent publication backpressure per layer. If the previous publication for a
layer is still in flight, that layer's new result is dropped without affecting the other layer. This produces the
best achievable preview rate without allowing generation or transport queues to grow unbounded.

`set_viewport()` normally affects subsequent frames. While the camera is idle, it can instead regenerate a
viewport layer from the cached raw frame. The controller admits that requested result while rejecting unrelated
late preview work after streaming has stopped.

`PreviewHealth` owns generation and publication counters and timing. `snapshot()` returns the current values and
resets them for the next reporting interval.

## Stream lifecycle

`source_stream_id` identifies pixels that belong to one camera preview stream. Overview and viewport frames from
the same stream share it; `frame_idx` identifies the source capture within that stream.

`PreviewGenerator.reset_stream()` cancels pending work, clears the cached raw frame, and creates a new
`source_stream_id`. The camera controller resets the stream when previewing starts and when an acquisition stack
opens. Profile changes also ask each active camera to reset its stream before new settings are applied, preventing
cached pixels from the old profile from being regenerated under the new one.

Stopping a stream cancels pending work. `close()` additionally shuts down both generation executors.

The generator's operational API is deliberately small:

- `submit_frame()` accepts a captured sensor frame without awaiting generation.
- `set_viewport()` updates the requested viewport and optionally returns a cached-regeneration task.
- `reset_stream()` establishes a new source-stream identity and discards old cached state.
- `cancel_pending()` invalidates scheduled work without changing stream identity or cache.
- `close()` releases generator resources.

## Consumers

Qt subscribes to `StationFeed.frames`, decodes each `VoxelPreviewPacket` away from the UI thread, and composites
the overview and viewport layers as grayscale intensity images. The web client receives the same delivery packets
over the dedicated preview WebSocket, decodes Zstandard in a worker, and uploads the shuffled byte planes to shared
WebGPU textures. Both consumers place every layer from `source_rect_px`, correlate frames with station state,
invalidate old session/preview generations, and treat sequence gaps as expected frame drops.
