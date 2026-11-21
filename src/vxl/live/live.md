# Live frames

The live path carries what each camera sees to the screens as compressed raw intensity data. Camera nodes produce
source frames; they do not render JPEGs, apply display levels, or know about profiles or channels. The control
computer routes the packed frames without decoding or recompressing their pixels, and clients own display
processing and composition.

"Live" names the frames; "preview" names the instrument's mode of exploring by hand. Frames also flow during a run.

The new core (`vxl.station`) implements the path from the camera to the feed's frame topics, the planes, and the
viewport. The web layer and the Qt app still use the old instrument (`vxl._legacy.instrument`,
`vxl._legacy.station`); they move to the new core later.

## Ownership and routing

Live metadata is split at the boundary where it becomes known:

- The camera owns `camera_id`, source-stream identity, capture sequence, pixel geometry, valid bit depth, and
  encoding details.
- The instrument's `LiveRelay` (`vxl.instrument.live`) reads only each frame's header. It drops frames of an
  old stream and sends the packed frame on with the stage position from when that frame number was first seen,
  without decoding it. `Instrument.live` gives these frames out, keyed by camera; `Station.live` passes on those of
  the open instrument.
- `StationTopics` (`vxl.web.station.topics`) gives each frame of the active session to the `FeedPublisher`
  (`vxl.web.feed`)
  under the feed topic `instrument.frames.<camera>.<layer>`. The publisher links the frame to its current state
  cursor and sends the packed source frame on without decoding it.
- The client owns levels, color mapping, interpolation, layer composition, grouping pictures into panels, and other
  display state.

No histogram is carried on the source frame. A client that needs one can calculate it from the decoded pixels.

Each camera capture can produce two independently replaceable layers:

| Layer | Camera topic | Instrument output | Station | Feed topic | Source region |
| --- | --- | --- | --- | --- | --- |
| `overview` | `live` | `Instrument.live` | `Station.live` | `instrument.frames.<camera>.overview` | The read-out region, up to 2048 pixels wide |
| `viewport` | `live_viewport` | `Instrument.live` | `Station.live` | `instrument.frames.<camera>.viewport` | Current viewport plus overscan, up to 2048 pixels wide |

A camera topic is a rigup device topic. A feed topic is the dotted name that the readers of the feed get, under the
publisher's prefix (`stations.<id>.`).

The overview stays at a constant maximum width regardless of zoom. At the full viewport there is no separate
viewport layer to generate.

## Planes

`LiveView` (`Instrument.view.live`) tells a screen where each camera's picture lies:

- `planes`: the planes of the specimen that the active profile's cameras see. A `Plane` has `right` and `down`,
  its 2 screen directions as unit vectors in the specimen's axes, and a `Picture` for each camera in it. A
  `Picture` is the camera's read-out region in that plane: `corner`, `width` and `height`, in µm from the stage
  position. Cameras whose planes differ by less than 1° share a plane. A plane follows the stage: of the 2 stage
  axes that lie most in it, the first of x, y, z points right.
- `stream_revision`: it goes up whenever older frames are no longer valid.

The instrument keeps the planes as a `Computed` over what the devices last reported: the active profile, each
area camera's `sensor` and `roi`, and each router's `state`. Each router counts where it says it is, falling back to
the profile's position while it has not said or is between slots. So a hand-moved objective or a new region changes
the planes at once, without restarting the preview. A camera that no light path reaches, or that has not reported
its sensor and region yet, has no picture. Binning is not an input: it changes a pixel's size, not where the
picture lies.

The planes describe the picture being seen. The planner describes what a run images, from the saved positions,
region and binning. The 2 can differ when a device was moved by hand.

## Viewport

`Instrument.update_viewport(cameras, box)` zooms the cameras that a screen shows together. `box` is left, top,
width and height in µm in their shared plane, from the stage position; `None` shows each whole picture. The call is
refused when the cameras do not lie in 1 plane. For each camera, `Picture.viewport(box)` turns the box into fractions
of that camera's read-out frame, which go to the camera's `live_viewport`. The handle coalesces updates, so the
latest zoom wins with 1 call in flight. The instrument keeps each camera's box and sends it again after new streams
or new planes, since the same box can then cover another part of the sensor. The call changes only what the live
image shows, so it waits for no command and restarts no activity.

For a viewport layer, the generator expands the requested viewport by `OVERSCAN_MARGIN`, currently 5% on each side,
and clamps it to the frame. `source_rect_px` records the actual integer sensor footprint represented by the pixels
after expansion and clamping. It is therefore not necessarily identical to the viewport the screen asked for.

The rectangle uses an inclusive floor for its origin and an exclusive ceiling for its end so partially covered
sensor pixels are not lost.

## Source-frame construction

`LiveFrame.from_source()` performs the complete sensor-frame transformation:

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

The prefix contains the `VXSF` magic (Voxel source frame), framing version, and MessagePack header length. The
source header contains:

- source schema version and encoding identifier
- `camera_id`, `source_stream_id`, `frame_idx`, and `layer`
- optional `captured_at_unix_us`, when a true camera capture timestamp is available
- rendered `width` and `height`
- `sensor_width`, `sensor_height`, and `source_rect_px`
- `valid_bits` and uncompressed byte length

It intentionally excludes `channel_id`, histograms, levels, color maps, and display state.

A `FrameMessage` (`vxl.web.feed`) carries complete source packets to the readers of the feed, without parsing or
modifying them, as a `VXFP` packet (Voxel frame packet):

```text
9-byte prefix | MessagePack header | 1 complete VXSF source packet for each topic
```

The prefix contains the `VXFP` magic, the framing version, and the MessagePack header length. The header contains the
message's `cursor` (`stream_id` and `seq`), `sent_at_unix_us`, and `topics`: for each frame topic, its `state`
cursor, its `position_um`, and its `frame_byte_length`. The source packets follow the header in the order of its
topics. A message usually holds 1 topic, and more only when frames waited for a slow reader. `state` is the
publisher's state cursor when it took the frame. The message `seq` increases across messages; gaps are expected,
since only the newest frame of each topic waits for a reader. Camera-owned fields such as `layer` are not duplicated
in the header; the topic name ends with the layer. VXFP carries camera frames only.

The legacy apps have their own packet, `VXLP` (`VoxelLivePacket` in `vxl._legacy.live`), which holds 1 source frame
under a `channel_id`. A reader of 1 packet refuses the other by its magic.

Each topic's nullable `position_um: {x, y, z}` is the stage position that the stage last reported when the
relay first saw that frame number. This is not synchronized exposure-time positioning. The relay keeps the latest
16 frame positions per camera and reuses them for overview and regenerated viewport packets, also after the preview
stops, so a zoom of a stopped image keeps its place. A position is unknown until every stage axis has reported.
Stream resets and instrument close clear these associations. The camera-owned VXSF packet is unchanged.

A screen places each picture from its plane's `Picture` and the frame's `position_um`, so a stopped image keeps its
true place when the stage moves. A new `stream_revision` clears the old images.

`FeedPublisher.connect_frames()` gives the frame messages. Consumers correlate each frame's `state` cursor with the
state messages, use the session identity and `stream_revision` to invalidate old display generations, and reject
stale or out-of-order frames.

Every layer, including `overview`, is positioned from `source_rect_px`. The `layer` field selects replacement
and composition behavior; it never implies that the represented rectangle covers the full sensor.

## Scheduling and backpressure

`LiveGenerator.submit_frame()` is synchronous and non-blocking. It caches the latest raw frame, then
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

`LiveHealth` owns generation and publication counters and timing. `snapshot()` returns the current values and
resets them for the next reporting interval.

## Stream lifecycle

`source_stream_id` identifies pixels that belong to one camera preview stream. Overview and viewport frames from
the same stream share it; `frame_idx` identifies the source capture within that stream.

`LiveGenerator.reset_stream()` cancels pending work, clears the cached raw frame, and creates a new
`source_stream_id`. The camera controller resets the stream when previewing starts and when an acquisition stack
opens.

The instrument starts new streams, through `LiveRelay.reset`, and raises `stream_revision`:

- when a preview starts, right after its cameras start and before the light, since a camera starts a new stream
  when it starts;
- when a profile is applied;
- when the planes change.

1 reset runs at a time, so the streams the relay keeps are always those of the last reset to run.

Stopping a stream cancels pending work. `close()` additionally shuts down both generation executors.

The generator's operational API is deliberately small:

- `submit_frame()` accepts a captured sensor frame without awaiting generation.
- `set_viewport()` updates the requested viewport and optionally returns a cached-regeneration task.
- `reset_stream()` establishes a new source-stream identity and discards old cached state.
- `cancel_pending()` invalidates scheduled work without changing stream identity or cache.
- `close()` releases generator resources.

## Consumers

Today both consumers take frames from the old instrument. Qt subscribes to its station feed, decodes each
`VoxelLivePacket` (`VXLP`) away from the UI thread, and composites the overview and viewport layers as
grayscale intensity images. The web client receives the same delivery packets over the dedicated live WebSocket,
decodes Zstandard in a worker, and uploads the shuffled byte planes to shared WebGPU textures. Both place every layer
from `source_rect_px`, correlate frames with station state, invalidate old generations, and treat sequence gaps as
expected frame drops. Moving them to the new core means reading `view.live` and zooming through
`update_viewport`.
