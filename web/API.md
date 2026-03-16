# Web API — REST + WebSocket

## Design Principles

- **REST for mutations** — one-shot commands use HTTP (proper status codes, typed responses, no fire-and-forget ambiguity)
- **WebSocket for streams** — server→client events (status pushes, preview frames, acquisition progress, device property updates)
- **Broadcast on mutation** — every REST mutation calls `service.broadcast({}, with_status=True)` so all WS clients stay in sync
- **Paths mirror data model** — URL hierarchy reflects `SessionConfig` structure

## REST Endpoints

### `plan/` — Acquisition plan (maps to `SessionConfig.plan: AcquisitionPlan`)

| Method | Path | Body | Description |
|--------|------|------|-------------|
| PUT | `plan/tile-order` | `{ tile_order }` | Set tile ordering |
| PUT | `plan/interleaving` | `{ interleaving }` | Set interleaving mode |
| POST | `plan/profiles` | `{ profile_id }` | Add profile to plan |
| DELETE | `plan/profiles` | `{ profile_id }` | Remove profile from plan |
| PUT | `plan/profiles/reorder` | `{ profile_ids[] }` | Reorder profiles |
| PATCH | `plan/grid` | `{ x_offset_um?, y_offset_um?, overlap_x?, overlap_y? }` | Update active profile's grid |
| GET | `plan/grid` | — | Get active profile's grid config |
| POST | `plan/stacks` | `{ stacks[] }` | Add stacks |
| PATCH | `plan/stacks` | `{ edits[] }` | Edit stacks |
| DELETE | `plan/stacks` | `{ positions[] }` | Remove stacks |
| GET | `plan/stacks` | — | List all stacks |

### `rig/` — Hardware and profile config (maps to `SessionConfig.rig`)

| Method | Path | Body | Description |
|--------|------|------|-------------|
| GET | `rig/config` | — | Full rig config |
| POST | `rig/profile/active` | `{ profile_id }` | Activate profile |
| POST | `rig/profile/save-props` | `{ device_id }` or `{ all: true }` | Save device props to profile |
| POST | `rig/profile/apply-props` | — | Apply saved props to hardware |
| PATCH | `rig/profile/waveforms` | `{ waveforms?, timing? }` | Update waveforms |
| GET | `rig/daq/waveforms` | — | Get waveform traces |
| GET | `rig/colormaps` | — | Available colormaps |
| GET | `rig/devices` | — | List devices |
| GET | `rig/devices/{id}/properties` | — | Get device properties |
| PATCH | `rig/devices/{id}/properties` | `{ properties }` | Set device properties |
| POST | `rig/devices/{id}/commands/{cmd}` | `{ args?, kwargs? }` | Execute command |

### `workflow/` — Workflow state

| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `workflow/next` | — | Advance to next step |
| POST | `workflow/reopen` | `{ step_id }` | Reopen a step |

### Other

| Method | Path | Body | Description |
|--------|------|------|-------------|
| GET | `info` | — | Static session info |
| GET | `status` | — | Current session status |
| PATCH | `metadata` | `{ metadata }` | Update experiment metadata |

### All REST paths are prefixed with `/api/` by the FastAPI router.

## WebSocket (read-only for state, bidirectional for streaming)

Connected at `/api/ws`. After migration, WS is used only for:

### Client → Server (kept on WS — high-frequency or streaming)

| Topic | Payload | Reason |
|-------|---------|--------|
| `request_status` | — | Ask server to push status |
| `preview/start` | — | Start frame streaming |
| `preview/stop` | — | Stop frame streaming |
| `preview/crop` | `{ x, y, k }` | High-frequency (drag panning) |
| `preview/levels` | `{ channel, min, max }` | High-frequency (slider) |
| `preview/colormap` | `{ channel, colormap }` | Grouped with preview |

### Server → Client (events pushed to all connected clients)

| Topic | Payload | Trigger |
|-------|---------|---------|
| `status` | `AppStatus` | Any mutation (via `broadcast(with_status=True)`) |
| `preview/frame` | binary (msgpack) | During preview streaming |
| `preview/crop` | `{ x, y, k }` | Crop change echo |
| `preview/levels` | `{ channel, min, max }` | Levels change echo |
| `preview/colormap` | `{ channel, colormap }` | Colormap change echo |
| `acq/progress` | `{ status, tile_id?, ... }` | During acquisition |
| `daq/waveforms` | `{ profile_id, traces, ... }` | After waveform update |
| `device/{id}/properties` | property payload | After device prop change |
| `device/{id}/command_result` | result payload | After command execution |
| `profile/changed` | `{ profile_id }` | After profile switch |
| `profile/props_saved` | `{ device_id? }` or `{ devices[] }` | After props saved |
| `profile/props_applied` | `{ devices[] }` | After props applied |
| `error` | `{ error, topic? }` | On error |
| `log/message` | `{ level, message, ... }` | Log stream |

## Migration Status

### Phase 1: Restructure REST endpoints under new paths
- [ ] Move existing `/session/*` endpoints to `plan/*` paths
- [ ] Move existing `/profiles/active` to `rig/profile/active`
- [ ] Add missing REST endpoints (plan/profiles, plan/interleaving, workflow/*, rig/profile/save-props, etc.)
- [ ] Update frontend to use `fetch()` for all mutations

### Phase 2: Remove WS RPC for migrated topics
- [ ] Remove WS message handlers for topics that now have REST endpoints
- [ ] Remove corresponding `ClientMessage` types from client.svelte.ts
- [ ] Remove `client.send()` calls, replace with fetch-based methods on Session class

### Phase 3: Acquisition page UI
- [ ] Stack list reflecting actual execution order (grouping follows interleaving mode)
- [ ] Tile order dropdown
- [ ] Interleaving dropdown
- [ ] Profile reorder (drag or up/down)
- [ ] Acquisition start/stop controls
