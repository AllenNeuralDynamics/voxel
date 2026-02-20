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

## Layout (Route 3)

### Three-column layout

- **Left sidebar** — Channel controls, profile selector, device settings
- **Middle column** — Workflow-specific content (top) + collapsible bottom panel (Session/Waveforms/Lasers/Logs)
- **Right column** — GridCanvas (top) + PreviewCanvas (bottom)

### Entire UI is mode-aware

Not just the middle column — all three columns adapt based on `session.workflow`:

- **GridCanvas** behavior changes: navigation (scout) → tile selection (plan) → progress display (acquire)
- **PreviewCanvas** emphasis changes: primary (scout) → reference (plan) → minimal (acquire)
- **Left sidebar** adapts: channel tweaking (scout) → per-stack settings (plan) → monitoring (acquire)

### Grid parameters belong in Scout, not Plan

Offset, overlap, tile order are part of exploring and framing the sample. Plan mode is for selecting tiles and configuring stack-specific settings.

## Workflow UI per Pane

How each pane adapts across workflow steps.

### Left Sidebar

| | Scout | Plan | Acquire |
|---|---|---|---|
| Profile selector | Active — switch profiles to explore | Locked if stacks exist with different profile | Read-only during acquisition |
| Channel controls | Full — exposure, laser power, device settings | Per-stack overrides — settings for selected stacks | Read-only monitoring |
| Device filter | All modes available | Same | Same |

### Middle Column (main content area)

| | Scout | Plan | Acquire |
|---|---|---|---|
| **Primary content** | Grid config (offset, overlap, tile order), stage navigation, position bookmarks | Stack planning — tile selection summary, z-range config, stack list with bulk/individual editing | Acquisition controls + progress |
| **Key actions** | Adjust grid params, bookmark positions, navigate stage | Select tiles → set z-range → add stacks, edit/remove planned stacks | Start/stop acquisition, monitor per-stack status |
| **Bottom panel** | Session info, waveforms, lasers, logs (unchanged across modes) | Same | Same |

#### Scout middle column detail

- Grid offset (X, Y) spinboxes
- Overlap spinbox
- Tile order selector
- Stage position display + quick navigation (step buttons or click-to-move)
- Position bookmarks list (saved XY + Z + optional thumbnail)
- Bookmark button to save current position

#### Plan middle column detail

- Selection summary: "N tiles selected"
- Z-range controls: z_start, z_end, z_step spinboxes
- Frame count (computed)
- "Add Stacks" button for selected tiles
- Stack list (new design, not reusing GridTable):
  - Per-stack: position, z-range, status, frame count
  - Inline z-range editing for PLANNED stacks
  - Bulk select + bulk edit z-range
  - Remove button
- Stack summary: total stacks, total frames, estimated time
- Per-stack device overrides (laser power, exposure) — requires backend extension

#### Acquire middle column detail

- Start All / Stop button
- Overall progress: "3 of 10 stacks completed"
- Per-stack status list:
  - PLANNED → pending (grey)
  - ACQUIRING → in progress (blue, animated)
  - COMPLETED → done (green)
  - FAILED → error (red) with message
- Elapsed time / estimated remaining
- Post-acquisition summary: completed/failed counts, total duration, output path

### Right Column

| | Scout | Plan | Acquire |
|---|---|---|---|
| **GridCanvas** | Navigation mode — FOV follows stage, grid lines visible, click-to-move, bookmark pins | Selection mode — click/drag to select tiles, planned stacks as colored overlays | Progress mode — read-only, stacks colored by status, current stack highlighted |
| **PreviewCanvas** | Primary — full size, all controls, live preview is main focus | Reference — still live, secondary importance | Minimal — preview paused during stack capture, shows last frame |

### Laser Controls

Laser controls live in the bottom panel as a tab (alongside Session, Waveforms, Logs). The tab trigger shows colored dot indicators (filled + pinging when enabled, border-only when disabled) instead of a text label. The pane content shows per-laser toggle switches with wavelength, power readout, and a "Stop All" emergency button. Laser state is derived in the page script rather than importing the LaserIndicators tooltip component.

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

### Per-stack settings (future)

Backend `Stack` model needs extension for device overrides:
- Per-stack laser power, exposure, etc.
- Could be a `settings: dict[str, Any]` or typed override model
- Applied before each stack acquisition in `rig.acquire_stack()`

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

### Per-stack settings gap

Backend `Stack` model only stores z-range and profile_id. No per-stack laser power, exposure, or device overrides. Plan mode needs this for proper per-tile configuration. Backend model needs extension.

### Route cleanup

Route 3 promoted to root route (`/`). Routes 0, 1, 2 and old root deleted. `LeftPanel.svelte` deleted. Route 3's local `ChannelSection.svelte` and `DeviceFilterToggle.svelte` moved to routes root.

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
