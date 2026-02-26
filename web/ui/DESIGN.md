# Web UI Redesign Notes

Design decisions and context for the route 3 UI/UX redesign.

## Workflow System

### SessionWorkflow enum

The acquisition process follows four workflow steps: **Configure → Scout → Plan → Acquire**.

- `configure` — Rig-level setup: profile editing, DAQ timing/waveform composition, channel configuration, device health overview. Auto-skipped on session startup (jumps to Scout) but always navigable via its tab.
- `scout` — Explore sample with live preview, configure grid parameters (offset, overlap, tile order), bookmark positions
- `plan` — Select tiles, create stacks, configure per-stack and bulk settings (z-range, laser power, exposure, etc.)
- `acquire` — Run acquisition, monitor progress, review results

### Where workflow lives

`session.workflow` lives in the **backend Session** (not frontend-only) because:

- Resumed sessions need to restore workflow state (e.g., session with completed stacks → acquire mode)
- Multiple clients see the same state
- Backend can enforce constraints per workflow step (e.g., reject grid offset changes outside scout)
- Persisted in `.voxel.yaml` session file

### Workflow vs RigMode

These are orthogonal:

- `RigMode` (idle/previewing/acquiring) = what the **hardware** is doing
- `SessionWorkflow` (scout/plan/acquire) = where the **user** is in the process

You can be in `plan` workflow with rig `previewing` (checking positions with live view).

### Transition rules

- `configure → scout` — Auto-transition on session startup if profile is valid. Manual transition always allowed.
- `scout → configure` — Always allowed (no grid lock, no stacks yet)
- `scout → plan` — Locks grid params (offset, overlap, tile order)
- `plan → configure` — **Not allowed.** Stacks depend on the current profile/DAQ config. Must go Plan → Scout → Configure to reconfigure.
- `plan → acquire` — Requires at least one PLANNED stack
- `plan → scout` — Only if no non-PLANNED stacks exist (nothing acquired yet)
- `acquire → plan` — Only if rig is idle (no active stack), allows adding more stacks
- `acquire → configure` — **Not allowed.**

Grid locking becomes mode-based rather than derived from stack statuses.

### Configure step rationale

Scout was pulling double duty: "configure the rig" and "explore the sample." These are conceptually different. Configure answers **"how is this microscope set up?"** — profiles, channels, DAQ synchronization, waveforms, auxiliary devices. Scout answers **"where is my sample and how does it look?"**

Configure is auto-skipped on startup — the session loads with a valid profile from YAML and drops directly into Scout. Users can click the Configure tab at any time to go back (from Scout). Once in Plan or Acquire, rig config is locked because downstream state (stacks, tiles) depends on it. To reconfigure, unwind to Scout first.

## Layout

### Two-panel layout (revised)

Previous design used a three-column layout with a dedicated left sidebar. This has been revised to a two-panel split:

- **Left panel** — Control area: global header + workflow workspace + bottom panel
- **Right panel** — Viewer: PreviewCanvas (top) + GridCanvas (bottom)

The two panels are horizontally resizable (left: 50-70%, right: remainder). The left panel contains all controls, settings, and monitoring. The right panel is purely visual output.

There is **no dedicated sidebar/aside**. Device controls that previously lived in the sidebar now live in the bottom panel as a tab. The main workspace area is fully dedicated to settings and workflow content.

### Structure of the left panel

```
┌─────────────────────────────────────────┐
│  Header: profile selector, workflow     │
│  steps, preview start/stop             │
├─────────────────────────────────────────┤
│                                         │
│  Workspace: mode-dependent content      │
│  (settings, grid config, progress)      │
│                                         │
├─────────────────────────────────────────┤
│  Bottom panel (collapsible, tabbed):    │
│  Devices | Waveforms | Logs | Session   │
└─────────────────────────────────────────┘
```

### Bottom panel

Constant across all workflow modes. Tabs:

- **Devices** (default/primary tab) — camera controls, laser controls, DAQ status for all active devices in the current profile. Laid out horizontally since the panel has full width. No per-channel grouping — just the devices themselves.
- **Waveforms** — DAQ waveform viewer
- **Logs** — log stream
- **Session** — session info, stage position, grid summary

The Devices tab replaces both the old sidebar device controls and the separate Lasers tab.

### Entire UI is mode-aware

- **GridCanvas** behavior changes: navigation (scout) → tile selection (plan) → progress display (acquire)
- **PreviewCanvas** emphasis changes: primary (scout) → reference (plan) → monitoring (acquire)
- **Workspace** content changes per mode (see below)
- **Bottom panel** remains constant — always available regardless of mode

### Grid parameters belong in Scout, not Plan

Offset, overlap are part of exploring and framing the sample. Tile order is a planning concern.

## Settings Hierarchy

### Levels

Settings follow an inheritance model:

- **Profile settings** — defaults for the entire acquisition (exposure, laser power, channel config, etc.). Configured during scouting.
- **Tile settings** — per-tile overrides where a specific region needs different parameters.
- **Effective tile settings** — what actually gets applied during acquisition: tile settings if overridden, otherwise profile settings.
- **Live settings** — current hardware state, which may differ from saved profile/tile settings while scouting.

### Live vs saved

During scouting, the user adjusts device parameters via the bottom panel (live settings). These are real-time hardware changes. Profile settings are the "saved" defaults — the user explicitly saves live settings to the profile when satisfied. The UI needs to make this distinction clear: "you're tweaking live" vs "these are the profile defaults."

### Settings UI

Two complementary views, togglable:

- **Contextual view (default)** — shows profile settings as the base form. When a tile is selected in the grid canvas, shows that tile's effective settings with override indicators. Editing updates the profile or tile depending on context. Natural for focused work on individual tiles.
- **Table/matrix view** — rows are settings (exposure, laser power, etc.), columns are tiles (plus a "Profile Default" column). Overrides are visually distinct. Good for comparing across tiles and bulk editing. Toggle into this view when you need the full picture.

## Workflow UI

### Workspace content per mode

|                     | Configure                                                           | Scout                                                   | Plan                                                                | Acquire                          |
| ------------------- | ------------------------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------- | -------------------------------- |
| **Primary content** | Profile editor, DAQ timing/waveforms, channel config, device health | Grid config (offset, overlap), live device tuning       | Tile settings, tile order, stack config (z-range, step), stack list | Acquisition progress, controls   |
| **Key actions**     | Edit profile, compose waveforms, assign channels, verify devices    | Dial in live params, configure grid, bookmark positions | Select tiles, set z-range, add stacks, per-tile overrides           | Start/stop, pause/abort, monitor |
| **Settings focus**  | Rig-level: microscope configuration                                 | Profile-level: establishing defaults from live tuning   | Tile-level: overrides and stack params                              | Read-only: effective settings    |

### Configure workspace detail

Rig-level setup — "how is this microscope set up?"

- Profile selection (switch between existing profiles) and profile editing
- Channel configuration: detection + illumination pairings, filter positions, emission wavelengths
- DAQ timing: sample rate, duration, rest time (editable with live waveform preview)
- Waveform composition: per-device waveform type selection and parameter editing, visual editor
- Port assignment overview: which device maps to which DAQ port (ao0, ao1, etc.)
- Stack-only waveform designation: mark waveforms as active only during z-stacks
- Device health/connection overview: all devices with status indicators

### Scout workspace detail

Sample-level exploration — "where is my sample and how does it look?"

- ~~Profile settings form (exposure, laser power, channel config) with "save to profile" action~~ (moved to Configure)
- Live device parameter tuning via bottom panel with "save to profile" action
- Grid offset (X, Y) spinboxes
- Overlap spinbox
- Stage position display + quick navigation (step buttons or click-to-move)
- Position bookmarks list (saved XY + Z + optional thumbnail)
- Bookmark button to save current position

### Plan workspace detail

- Settings view toggle: contextual (default) ↔ table/matrix
- Contextual view: profile defaults form, tile overrides when tile selected
- Table view: settings × tiles matrix with override indicators
- Tile order selector
- Z-range controls: z_start, z_end, z_step spinboxes
- Frame count (computed)
- "Add Stacks" button for selected tiles
- Stack list (new design, not reusing GridTable):
  - Per-stack: position, z-range, status, frame count
  - Inline z-range editing for PLANNED stacks
  - Bulk select + bulk edit z-range
  - Remove button
- Stack summary: total stacks, total frames, estimated time

### Acquire workspace detail

- Start All / Stop button
- Overall progress: "3 of 10 stacks completed"
- Per-stack status list:
  - PLANNED → pending (grey)
  - ACQUIRING → in progress (blue, animated)
  - COMPLETED → done (green)
  - FAILED → error (red) with message
- Elapsed time / estimated remaining
- Post-acquisition summary: completed/failed counts, total duration, output path

### Viewer (right panel)

|                   | Configure                                           | Scout                                                                                 | Plan                                                                            | Acquire                                                                        |
| ----------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **GridCanvas**    | Inactive or minimal — no sample context yet         | Navigation mode — FOV follows stage, grid lines visible, click-to-move, bookmark pins | Selection mode — click/drag to select tiles, planned stacks as colored overlays | Progress mode — read-only, stacks colored by status, current stack highlighted |
| **PreviewCanvas** | Optional — may show live preview for testing config | Primary — full size, all controls, live preview is main focus                         | Reference — still live, secondary importance                                    | Minimal — preview paused during stack capture, shows last frame                |

## Backend Changes Required

### SessionWorkflow on Session model

Add `workflow: SessionWorkflow` field to `SessionConfig` and `Session`:

- Enum values: `configure`, `scout`, `plan`, `acquire`
- Default: `scout` for new sessions (auto-skip Configure on startup)
- Persisted in `.voxel.yaml`
- Included in `SessionStatus` broadcast
- Frontend receives via status updates

### Workflow transition API

WebSocket topic `session/set_workflow` with payload `{ "workflow": "scout" | "plan" | "acquire" }`.
Backend validates transition rules before accepting.

### Settings hierarchy support

Backend needs to support the profile → tile settings inheritance model:

- **Profile settings** — already exists as profile config (channels, device params)
- **Tile/stack overrides** — per-tile device parameter overrides (laser power, exposure, etc.)
- Could be a `settings: dict[str, Any]` or typed override model on `Stack`
- Backend resolves effective settings at acquisition time: tile override if present, otherwise profile default
- Applied before each stack acquisition in `rig.acquire_stack()`
- Frontend needs API to read/write tile overrides and query effective settings

## Missing Features (identified)

### No snapshot capability

Backend has no `capture_snapshot` method. Preview frames stream but aren't persisted. Scouting workflow needs position bookmarking with thumbnails — requires either backend support or client-side storage.

### Settings hierarchy gap

Backend `Stack` model only stores z-range and profile_id. No per-tile laser power, exposure, or device overrides. Plan mode needs this for the profile → tile settings inheritance model. Backend model needs extension.

## Bottom Panel — Device & Tab Inventory

### Current tab layout

The footer contains two tab groups:

**Left group (main):** Cameras | Lasers | Waveforms
**Right group (auxiliary):** Session | Logs

The Lasers tab has a live `LaserIndicators` component in its tab button (animated ping dots for enabled lasers). The Session tab shows `ClientStatus` (connection indicator).

Tab selection toggles collapse: clicking the active tab collapses/expands the bottom pane; clicking a different tab switches and expands.

### Tab completion status

| Tab           | Completeness | Summary                                                                                               |
| ------------- | ------------ | ----------------------------------------------------------------------------------------------------- |
| **Lasers**    | ~95%         | Gold standard. Dual-panel, power history sparklines, profile-aware grouping, quick presets, stop-all. |
| **Waveforms** | ~85%         | uPlot chart, timing sidebar, device toggle tree, cycle control. Viewer only.                          |
| **Cameras**   | ~80%         | Multi-select batch editing, property cards, stream stats. No detail panel.                            |
| **Session**   | ~60%         | Read-only metadata grid (config, stage, grid info).                                                   |
| **Logs**      | —            | LogViewer component, not assessed.                                                                    |

### Lasers tab — reference implementation

**Layout:** Left detail panel (384px fixed) + Right scrollable laser list.

**Left panel (selected laser):**

- Header: wavelength, laser color dot, device ID
- Power setpoint: SpinBox (0–max, 1mW steps, 1 decimal)
- Quick presets: 0% / 25% / 50% / 75% / 100% buttons
- Power history: SVG sparklines, multi-laser overlay with per-laser colors and opacity, selected laser emphasized (stroke-width 2, opacity 0.75)
- Footer: current temperature (°C), channel info popover button

**Right panel (laser list):**

- Organized into "Active Profile [name]" and "Other Lasers" sections
- "Stop All" button (danger, hidden when no lasers enabled)
- Per-laser row: wavelength dot + label | power Slider (shows both setpoint and actual) | power readout | Toggle switch
- 100ms throttled slider updates

**What makes it the gold standard:**

1. Dual-panel architecture — list for overview, detail panel for deep inspection
2. Rich visual feedback — color dots, sparklines, dual power display (target + actual)
3. Multiple control modalities — slider, spinbox, quick presets, toggle
4. Profile-aware organization — active profile lasers vs others
5. Emergency control — "Stop All" button
6. Smooth interactions — 100ms history loop, throttled updates, transitions

### Cameras tab — current state

**Layout:** Left edit panel (384px fixed, shown when cameras selected) + Right scrollable camera grid.

**Right panel (camera cards):**

- Grid layout (auto-fit, min 256px)
- "Select All" checkbox + count indicator
- Per-camera card:
  - Checkbox + device ID + mode dot (green=PREVIEW, yellow=ACQUISITION, gray=IDLE)
  - Properties: exposure (ms), binning (Nx), pixel format, frame size (px), sensor size (px), pixel size (µm)
  - Stream info (when streaming): FPS, data rate MB/s, dropped frames
  - Expandable channel info: label, emission wavelength, illumination device, filter positions

**Left panel (batch editor, shown when cameras selected):**

- Exposure: SpinBox with min/max from first selected camera
- Binning: Select, shows only common options across selection
- Pixel format: Select, shows only common options
- Frame region: X, Y, Width, Height spinboxes
- Apply button: disabled until form changes, shows camera count

### Waveforms tab — current state

**Layout:** Three-column — Left sidebar (timing + cycles) | Center (uPlot chart) | Right sidebar (device toggle tree).

**Left sidebar:**

- Static timing info from active profile: sample rate (formatted Hz/kHz/MHz), duration (µs/ms/s), rest time, frequency (calculated), sample count (calculated)
- Cycle control: SpinBox (1–4) to expand timeline visualization

**Center chart:**

- uPlot with time (ms) x-axis, voltage (V) y-axis
- Multiple series with 10-color palette (emerald, blue, amber, red, violet, pink, cyan, lime, orange, indigo)
- Dashed lines (5px dash, 10px gap)
- Draggable x-axis cursor
- Responsive via ResizeObserver
- Single cycle data repeated for selected cycle count

**Right sidebar:**

- `ProfileDevicesToggle` component
- Grouping modes: All | Type | Path | Channel
- Filters to only devices with waveforms (in DAQ's acq_ports)
- Three-state checkboxes (checked/unchecked/indeterminate)
- Color indicators matching waveform line colors

**Empty states:** "No waveform data available" / "Select devices to view waveforms"

### Session tab — current state

Read-only grid (2 columns) displaying:

- Config name, active profile, tile count, stack count, stage connection status
- Stage X/Y/Z position (mm, 3 decimals), moving status
- Grid overlap, tile order, locked status, field of view (W×H mm)

## Full Device Inventory (Backend)

### Device types (`src/vxl/device.py` DeviceType enum)

| DeviceType        | Description                  | VoxelRig field                                     |
| ----------------- | ---------------------------- | -------------------------------------------------- |
| `CAMERA`          | Image sensor                 | `cameras: dict[str, CameraHandle]`                 |
| `LASER`           | Light source                 | `lasers: dict[str, DeviceHandle]`                  |
| `AOTF`            | Acousto-optic tunable filter | `aotfs: dict[str, DeviceHandle]`                   |
| `DAQ`             | Data acquisition             | `daq: DaqHandle \| None`                           |
| `CONTINUOUS_AXIS` | Linear/rotational motor      | `continuous_axes: dict[str, ContinuousAxisHandle]` |
| `LINEAR_AXIS`     | Variant of CONTINUOUS_AXIS   | (categorized as continuous_axis)                   |
| `ROTATION_AXIS`   | Variant of CONTINUOUS_AXIS   | (categorized as continuous_axis)                   |
| `DISCRETE_AXIS`   | Filter wheel, turret, slider | `discrete_axes: dict[str, DeviceHandle]`           |

Additionally: `fws: dict[str, DeviceHandle]` is a subset of discrete_axes populated from config filter wheel IDs. `stage: VoxelStage` bundles x/y/z from continuous_axes.

### Web UI representation status

| Device Type             | Has Dedicated UI?      | Has Frontend Model?      | Notes                                                        |
| ----------------------- | ---------------------- | ------------------------ | ------------------------------------------------------------ |
| Camera                  | Yes — CamerasPanel     | Yes — `camera.svelte.ts` | Batch editing, property cards, stream stats                  |
| Laser                   | Yes — LasersPanel      | Yes — `laser.svelte.ts`  | Gold standard: dual-panel, sparklines, presets               |
| Continuous Axis (stage) | Partial — SessionPanel | Yes — `axis.svelte.ts`   | Position display, movement in grid canvas                    |
| DAQ                     | Yes — WaveformViewer   | No dedicated model       | Waveform visualization only, no direct DAQ control           |
| **Filter Wheel**        | **No**                 | **No**                   | Only shown indirectly in channel info popovers               |
| **AOTF**                | **No**                 | **No**                   | Fully functional backend, zero UI                            |
| **Rotation Axes**       | **No**                 | **No**                   | Stage config supports roll/pitch/yaw but UI shows only x/y/z |

### Camera properties and commands

**Read properties:** `sensor_size_px`, `pixel_size_um`, `pixel_format`, `binning`, `exposure_time_ms`, `frame_rate_hz`, `frame_region`, `frame_size_px`, `frame_size_mb`, `frame_area_mm`, `stream_info`, `mode`
**Write properties:** `pixel_format`, `binning`, `exposure_time_ms`, `frame_rate_hz`
**Commands:** `update_frame_region(x?, y?, width?, height?)`, `start_preview()`, `stop_preview()`, `update_preview_crop()`, `update_preview_levels()`, `update_preview_colormap()`, `capture_batch()`, `get_preview_config()`

StreamInfo includes: `frame_index`, `input_buffer_size`, `output_buffer_size`, `dropped_frames`, `frame_rate_fps`, `data_rate_mbs`, `payload_mbs`

### Laser properties and commands

**Read properties:** `wavelength` (nm), `is_enabled`, `power_mw` (actual), `temperature_c`
**Read/Write properties:** `power_setpoint_mw` (min/max/step constrained)
**Commands:** `enable()`, `disable()`

### DiscreteAxis (filter wheel) properties and commands

**Read properties:** `slot_count`, `labels` (slot→name mapping), `position` (0-indexed, streamed), `label` (current, streamed), `is_moving` (streamed)
**Commands:** `move(slot, wait?, timeout?)`, `select(label, wait?, timeout?)`, `home(wait?, timeout?)`, `halt()`, `await_movement(timeout?)`

### AOTF properties and commands

**Read properties:** `num_channels`, `blanking_mode` (internal/external), `min_power_dbm`, `max_power_dbm`, `power_step_dbm`
**Per-channel:** `enable_channel()`, `disable_channel()`, `set_frequency()`, `set_power_dbm()`, `get_channel_state()`
**Registration:** `register_channel(device_id, channel, input_mode)` — used by laser drivers to claim channels

### ContinuousAxis properties and commands

**Read properties:** `position` (streamed), `lower_limit`, `upper_limit`, `speed`, `acceleration`, `backlash`, `home`, `is_moving` (streamed), `units`
**Write properties:** `speed`, `acceleration`
**Commands:** `move_abs()`, `move_rel()`, `go_home()`, `halt()`, `await_movement()`, `set_zero_here()`, `set_logical_position()`
**Optional TTL stepping:** `configure_ttl_stepper()`, `queue_absolute_move()`, `queue_relative_move()`, `reset_ttl_stepper()`

### DAQ properties and waveform types

**Properties:** `device_name`, `ao_voltage_range`, `available_pins`, `assigned_pins`
**Task management:** `create_ao_task()`, `create_co_task()`, `close_task()`, `start_task()`, `stop_task()`, `write_ao_task()`, `stop_all_tasks()`, `close_all_tasks()`

**Waveform types** (defined in `src/vxl/daq/wave.py`):

- `PulseWaveform` — on/off within timing window
- `SquareWave` — square wave with duty cycle
- `SineWave` — sinusoidal
- `TriangleWave` — triangular ramp
- `SawtoothWave` — sawtooth ramp
- `MultiPointWaveform` — custom [time, voltage] points
- `CSVWaveform` — loaded from CSV file

All waveforms define voltage range and a normalized time window.

## Rig Configuration Structure

### Optical paths (connect hardware to channels)

**Detection paths** (keyed by camera device ID):

- `filter_wheels: list[str]` — filter wheel device IDs in this path
- `magnification: float` — optical magnification
- `aux_devices: list[str]` — other devices (AOTFs for blanking, shutters, etc.)

**Illumination paths** (keyed by laser device ID):

- `aux_devices: list[str]` — other devices (AOTF blanking, shutter control, etc.)

### Channels (pair detection + illumination)

- `detection: str` — camera device ID
- `illumination: str` — laser device ID
- `filters: dict[str, str]` — maps filter_wheel_id → position_label
- `emission: float | None` — peak emission wavelength (nm) for color mapping
- `desc: str`, `label: str | None`

### Profiles (acquisition configurations)

- `channels: list[str]` — active channel IDs
- `daq.timing: FrameTiming` — sample_rate, duration, rest_time
- `daq.waveforms: dict[str, Waveform]` — per-device waveform definitions
- `daq.stack_only: list[str]` — waveforms active only during z-stacks

### Stage

- `x`, `y`, `z` — continuous axis device IDs (required)
- `roll`, `pitch`, `yaw` — rotation axis device IDs (optional)

### DAQ

- `device: str` — DAQ hardware device ID
- `acq_ports: dict[str, str]` — maps device_id → DAQ port (ao0, ao1, etc.)

## WebSocket API Topics (Device-Related)

### Device control

| Topic                        | Direction     | Payload                                     |
| ---------------------------- | ------------- | ------------------------------------------- |
| `device/set_property`        | Client→Server | `{device, properties: {...}}`               |
| `device/execute_command`     | Client→Server | `{device, command, args, kwargs}`           |
| `device/{id}/properties`     | Server→Client | Property stream updates                     |
| `device/{id}/command_result` | Server→Client | `{device, command, success, result, error}` |

### DAQ / Waveforms

| Topic                   | Direction     | Payload                         |
| ----------------------- | ------------- | ------------------------------- |
| `daq/request_waveforms` | Client→Server | (empty)                         |
| `daq/waveforms`         | Server→Client | `{device_id: [voltage_values]}` |

### Profile

| Topic             | Direction     | Payload        |
| ----------------- | ------------- | -------------- |
| `profile/update`  | Client→Server | `{profile_id}` |
| `profile/changed` | Server→Client | `{profile_id}` |

### Preview

| Topic           | Direction     | Payload                                     |
| --------------- | ------------- | ------------------------------------------- |
| `preview/start` | Client→Server | (empty)                                     |
| `preview/stop`  | Client→Server | (empty)                                     |
| `preview/frame` | Server→Client | Binary hybrid: JSON envelope + msgpack data |

Preview frames include optional histogram data in `PreviewFrameInfo`.

## Design Decisions — Bottom Panel & Workflow

### Resolved: Missing device coverage (filter wheels, AOTFs)

**Decision:** `ChannelPanel.svelte` will be deprecated. A future **Auxiliary Devices tab** in the bottom panel (with sub-tabs for discrete axes, continuous axes, AOTFs) will provide manual control and status monitoring. Tabled for now. Note: AOTF channel assignments are static (set at device init by laser drivers), and filter wheel positions are derived from channel config (set automatically on profile change) — neither requires explicit user configuration.

### Resolved: Waveform editing vs viewing

**Decision:** Waveform _editing_ (composition, timing parameters, waveform type selection) belongs in the **Configure workspace**. The bottom panel Waveforms tab remains a _viewer only_ — but enhanced with better data visualization. This keeps the bottom panel as a monitoring/inspection tool and the workspace as the action area.

### Resolved: Cameras tab direction

**Decision:** Focus on **configuration UX improvements**, not monitoring. Live histogram is already in PreviewCanvas. Priority additions:

- ROI visualizer — graphical frame region editor overlaid on sensor dimensions
- Trigger configuration — trigger mode and polarity
- Better detail panel (matching Lasers tab dual-panel pattern)

### Waveforms viewer enhancements (all roughly equal priority)

- **Hover data + measurements** — exact voltage/time on hover, amplitude readouts, zoom presets
- **Composite timeline** — show how waveforms relate to camera triggers, laser blanking, and stage motion in a unified view
- **Stack-only + port mapping** — visualize which waveforms are stack-only vs per-frame, and which DAQ port each device maps to

### Session tab enrichment (lower priority)

Currently minimal read-only grid. Could expand to include:

- Active profile details and channel summary cards
- Full acquisition parameters and estimated timing
- Disk usage projections
- Stage limits and range visualization
