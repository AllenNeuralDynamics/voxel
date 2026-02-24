# Web UI Redesign Notes

Design decisions and context for the route 3 UI/UX redesign.

## Workflow System

### SessionWorkflow enum

The acquisition process follows three workflow steps: **Scout → Plan → Acquire**.

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

- `scout → plan` — Locks grid params (offset, overlap, tile order)
- `plan → acquire` — Requires at least one PLANNED stack
- `plan → scout` — Only if no non-PLANNED stacks exist (nothing acquired yet)
- `acquire → plan` — Only if rig is idle (no active stack), allows adding more stacks

Grid locking becomes mode-based rather than derived from stack statuses.

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

| | Scout | Plan | Acquire |
|---|---|---|---|
| **Primary content** | Profile settings form, grid config (offset, overlap) | Tile settings, tile order, stack config (z-range, step), stack list | Acquisition progress, controls |
| **Key actions** | Dial in profile defaults, configure grid, bookmark positions | Select tiles, set z-range, add stacks, per-tile overrides | Start/stop, pause/abort, monitor |
| **Settings focus** | Profile-level: establishing defaults | Tile-level: overrides and stack params | Read-only: effective settings |

### Scout workspace detail

- Profile settings form (exposure, laser power, channel config) with "save to profile" action
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

| | Scout | Plan | Acquire |
|---|---|---|---|
| **GridCanvas** | Navigation mode — FOV follows stage, grid lines visible, click-to-move, bookmark pins | Selection mode — click/drag to select tiles, planned stacks as colored overlays | Progress mode — read-only, stacks colored by status, current stack highlighted |
| **PreviewCanvas** | Primary — full size, all controls, live preview is main focus | Reference — still live, secondary importance | Minimal — preview paused during stack capture, shows last frame |

## Backend Changes Required

### SessionWorkflow on Session model

Add `workflow: SessionWorkflow` field to `SessionConfig` and `Session`:
- Enum values: `scout`, `plan`, `acquire`
- Default: `scout` for new sessions
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

## Component Decisions

### Button primitive sizes

- `xs` — h-6 (24px), used for compact controls (spinbox-adjacent buttons)
- `sm` — h-7 (28px) with min-w-14, used for action buttons (Start/Stop, Halt)
- `md` — h-7, default
- `lg` — h-8

### Button variant borders

Filled variants (default, secondary, danger, success) use matching border colors (e.g., `border-danger` for danger). Only outline/ghost get `focus:border-ring`. Prevents focus ring from overriding colored borders.

## Missing Features (identified)

### No snapshot capability

Backend has no `capture_snapshot` method. Preview frames stream but aren't persisted. Scouting workflow needs position bookmarking with thumbnails — requires either backend support or client-side storage.

### Settings hierarchy gap

Backend `Stack` model only stores z-range and profile_id. No per-tile laser power, exposure, or device overrides. Plan mode needs this for the profile → tile settings inheritance model. Backend model needs extension.

### Route cleanup

Route 3 promoted to root route (`/`). Routes 0, 1, 2 and old root deleted. `LeftPanel.svelte` deleted. `ChannelSection.svelte` and `DeviceFilterToggle.svelte` deleted (device controls inlined into `ChannelPanel.svelte`, filter toggle replaced by chip multiselect inline snippet). `ChannelPanel0.svelte` retains the old single-select filter approach for reference.

### Components not yet in route 3

- Tile order selector (needed in Scout middle column)
- Stack list/table (new design for Plan mode, not reusing GridTable/GridEditor)
- Acquisition progress tracking (`acq/progress` topic exists but no frontend listener)
- Position bookmarking (Scout mode — no backend support yet)

### Orphaned lib/ui components (candidates for deletion)

After route cleanup, these are no longer imported by any kept file:

- `lib/ui/DeviceFilterToggle.svelte` — route has its own local copy
- `lib/ui/Histogram.svelte` — was used by deleted ChannelSection (lib version)
- `lib/ui/devices/LaserIndicators.svelte` — laser controls inlined in page
- `lib/ui/grid/GridEditor.svelte` — Plan mode will have new design
- `lib/ui/grid/GridTable.svelte` — Plan mode will have new design
- `lib/ui/grid/GridCanvas.svelte` (v1) — barrel exports GridCanvas2 only
- `lib/ui/grid/index.ts` — exports only GridEditor + GridTable
- `lib/ui/devices/index.ts` — barrel file, no direct imports
- `lib/ui/preview/ChannelHistogram.svelte` — not imported anywhere
- `lib/ui/primitives/Checkbox.svelte` — only used by orphaned GridTable
