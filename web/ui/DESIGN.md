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

### Components not yet in route 3

- Tile order selector
- Stack list/table (GridTable/GridEditor need redesign, not reuse)
- Acquisition progress tracking (`acq/progress` topic exists but no listener)
