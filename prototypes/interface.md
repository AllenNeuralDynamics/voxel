# Instrument interface

Discussed and built on 2026-11-18; trimmed on 2026-11-20 to the current design. The history of how it was reached
is in git.

## Built

- **Declarations** live in `rigup/src/rigup/interface.py`: 1 `Declaration`, 1 argument builder (with
  `**fields: Unpack[TypedDict]` support), 1 `OperationInfo` for devices and instruments. The word is "operation"
  everywhere (`DeviceInterface.operations`, `execute`).
- **vxl** checks each kind against its view model and gives routes and `InstrumentInterface` in
  `src/vxl/instrument/interface.py`. The checks run in `Instrument.__init_subclass__`, so a bad declaration fails on
  import. `Instrument.execute(name, args)` runs an operation by name.
- **Joined edits** (`src/vxl/instrument/base.py`): an edit opened inside another joins it. The outermost block makes 1
  history entry; if it raises, every path goes back. So 1 request is 1 undo step.
- **`BasicInstrument`** (`vxl.instrument.basic`): a ready-made kind a `rig.yaml` can name and run with no code.
- **The HTTP layer is in `vxl.web.station`** (built 2026-11-20 from the try-out in `prototypes/interface/`, deleted on
  2026-11-21 and kept in git; made leaner on 2026-11-21). `InstrumentRouter` (`instrument.py`) is the routes of 1 open instrument: a
  FastAPI router, not an app. `StationService` (`service.py`) owns the app: it passes each
  `/api/stations/<id>/instrument/...` request to the router of the open session, made at the first request of a session,
  and adds the station's own routes: `GET /api/stations/<id>/instruments`, `POST /api/stations/<id>/session:open` (body
  `{"instrument": "<name>"}`) and `POST /api/stations/<id>/session:close`, and the feed sockets under
  `/api/stations/<id>/feed/`. Each answer to a request that is not a read carries `Vxl-Feed-Cursor`. Every failure is
  answered in 1 place (`ProblemDetails` in `vxl.web.problems`); an instrument that does not start answers `422` with its
  problems. The router serves its own API page at `/instrument/openapi.json`.

## Rules

1. **The instrument knows no HTTP.** Declarations say what a method does to the instrument. The API maps that to
   HTTP; Qt, scripts and tests call the methods directly.
2. **Reads need no declarations.** Every `GET` of a resource is served from the view.
3. **Nothing is inferred from names.** A declaration names its resource and its key.
4. **1 request = 1 undo step**, through joined edits.

## The declarations

| Declaration | Does | HTTP | Body |
| --- | --- | --- | --- |
| `@create("plan")` | adds an item to a collection; `key=` for a map, so the client chooses the key | `POST /plan` | every argument |
| `@update("plan", key="task_id")` | changes some fields of 1 item | `PATCH /plan/{task_id}` | the other arguments |
| `@update("writer")` | changes some fields of a singleton | `PATCH /writer` | every argument |
| `@delete("plan", key="task_id")` | removes 1 item | `DELETE /plan/{task_id}` | none |
| `@query` | reads, with arguments, without changes | `GET /<noun>:<verb>` | none; arguments in the query |
| `@action` | anything else that changes the instrument | `POST /<noun>:<verb>` | every argument |
| `@failsafe` | makes the instrument safe; takes no arguments | `POST /<noun>:<verb>` | none |

- `@query`, `@action` and `@failsafe` take `on=` to belong to a resource (`POST /plan:reorder`). Operations at the
  root get a noun: `@action(on="preview", verb="start")` gives `POST /preview:start`.
- **No `PUT`** (AIP-134). `PATCH` with every field covers replacement.
- **A camera region is an update**, though it moves hardware: setting the same region twice leaves the same state.
- **Batch delete is a custom method** (AIP-235, `POST /plan:batchDelete`): a `DELETE` has no body, and several
  deletes would be several undo steps.
- **Updates take `**fields: Unpack[SomeFields]`** (`TypedDict`, `total=False`).

## Checks when the class is defined

1. The resource is a path in the kind's view model (`state.plan` written as `plan`).
2. `@create`, `@delete` and `@update` with a `key` target a collection: a list with a `Key` field, or a map. Lists
   keep order in JSON (RFC 8259: objects are unordered). `@update` without a `key` targets a singleton.
3. `key` is an argument of the method, of the collection's key type, with no default. Keys contain no `/` or `:`.
4. `@update` takes only fields of the item, all optional.
5. `@failsafe` takes no required arguments.
6. No 2 declarations make the same route. Positional-only arguments, a missing `self`, declarations under
   `@property`, and an override that changes what an operation does are refused.

One test builds the route table of every kind we ship.

## Inheritance

- **A resource that kinds extend is declared by the kind.** Each kind declares its own `update_profile` with its own
  fields; the base helper `_update_profile` records them as 1 edit. An override cannot add `Unpack` fields: a
  `TypedDict` is open, so the type checker refuses it.
- **The base declares only operations every kind has in full:** undo, redo, apply profile, device operations.
- **An override of a declared method repeats the declaration** and keeps its signature and what it does.

## HTTP rules for the station's operations

Built in `vxl.web.station`, except where a rule says "not built".

- **Errors** are `application/problem+json` (RFC 9457) with `type`, `title`, `status`, `detail`, `instance`, and an
  `errors` member listing refused arguments, or the problems that the instrument gave. `400` not JSON (`NaN` and
  `Infinity` are not JSON, RFC 8259 §6), `404` unknown item, device or operation, `405` with `Allow`, `409` busy, no
  open session, or a part that a running activity holds, `422` refused, `500` other. Unknown routes answer the same
  way. A path with a `/` at its end is unknown: no redirect.
- **Only a typed error gets its status.** The statuses are in `InstrumentRouter.statuses`. A method that raises a
  built-in error for bad input (`ValueError`, `RuntimeError`) answers `500`, so a method checks its input and
  raises `RejectedError`. A refusal that comes back from a device arrives as a `RuntimeError`: the instrument checks
  before it calls the device, as `move_stage` does with the limits of each axis.
- **`ETag` on every read and every answer with an item**: a hash of that item. `If-Match` on update and delete
  answers `412` when stale, also on `PATCH /devices/{id}`; `If-None-Match` on a read answers `304`. `If-Match` is
  optional for now; the UI always sends it. Require it (`428`, RFC 6585) when many users share a station.
- **PATCH is `application/merge-patch+json`** (RFC 7396): the API merges the patch into the current item and calls
  the method with whole field values. Not built: the HTTP layer passes the fields of the patch to the method as they
  are, and the method decides what a nested value replaces.
- **A write answers the item and its `ETag`, plus `Vxl-Feed-Cursor`**, an opaque Structured Field String
  (RFC 9651), so the UI can wait until its feed caught up. No `X-` prefix (RFC 6648). Built: the value is
  `"<stream_id>:<seq>"` of the state feed, on each answer to a request that is not a read. Browsers need
  `Access-Control-Expose-Headers` to read it from another origin; a window reads it from its own server. It covers
  what the operation itself changed. A value that a device reports later, such as after `PATCH /devices/{id}`,
  arrives in a later message.
- **An action that starts an activity answers `202` with a `Location`** to the activity or the run (AIP-151, Azure
  `operation-location`), seen from the method's return type. Not built: `POST /acquisition:start` answers `200`
  with the id of the acquisition. Short actions answer `200` or `204`.
- **Device routes go through the instrument:** `PATCH /devices/{id}` calls `set_device_properties`,
  `POST /devices/{id}:{operation}` calls `execute_device_command`, both through the scheduler, checked against
  `view.devices[id].interface` and refused with `422` before reaching the device.
- Every route sits under `/api/stations/<id>/`, at the station service and at its server (`server.md`); the routes
  of the open instrument sit under `/api/stations/<id>/instrument/`. The paths outside `/api` belong to the pages of
  the web app, such as `/stations/<id>/run` (decided 2026-11-21).

## SPIM routes, as an example

SPIM declares 33 operations (2026-11-21). A resource of the state sits under `/state`; another target is a noun of
its own. Some of them, each under `/api/stations/<id>/instrument`:

| Route | Method |
| --- | --- |
| `GET /state/plan`, `GET /state/plan/{task_id}` | from the view |
| `POST /state/plan`, `PATCH /state/plan/{task_id}` | `add_task`, `update_task` |
| `POST /state/plan:remove`, `POST /state/plan:reorder` | `remove_tasks`, `reorder_tasks` |
| `PATCH /state/profiles/{profile_id}`, `PATCH /state/writer` | `update_profile`, `update_writer_settings` |
| `POST /state/profiles:apply`, `POST /state/profiles/{profile_id}:select` | `apply_profile`, `select_profile` |
| `POST /preview:start`, `POST /preview:stop` | `start_preview`, `stop_preview` |
| `POST /acquisition:start`, `POST /acquisition:stop` | `start_acquisition`, `stop_acquisition` |
| `POST /history:undo`, `POST /history:redo` | `undo`, `redo` |
| `GET /stage:position`, `POST /stage:move` | `stage_position`, `move_stage` |
| `POST /devices/{device_id}:save_to_profile`, `:restore_from_profile` | `save_to_profile`, `restore_from_profile` |
| `GET /devices/{id}`, `PATCH /devices/{id}`, `POST /devices/{id}:{operation}` | the device routes |
| `GET /interface`, `GET /openapi.json` | the instrument's interface, and the API page of these routes |

## Open

- Status codes for create and no content: `201` and `204`, or `200` everywhere.
- Reads exist only for a state resource that has a create, an update or a delete. The other parts of the view are
  read from the feed. Decide whether every part of the view gets a `GET`.
- `Vec3D` (`vxlib`) has no JSON Schema, so the view schema cannot be made as is.
- A `NotFoundError` next to `RejectedError`, so methods can say "no such item" themselves.
- Versioning: the guides disagree (AIP `/v1/`, Azure `api-version`, Zalando media type); nothing to cite as the
  standard.
- `Idempotency-Key` for retries is still an Internet-Draft.

## References

Google AIP-131 to 136, 151, 154, 156, 193, 235; RFC 9110, 9457, 7396, 6585, 6648, 8259, 9651; OpenAPI 3.1; Zalando
RESTful API guidelines; Azure REST API guidelines; FastAPI; Django REST Framework; gRPC transcoding.
