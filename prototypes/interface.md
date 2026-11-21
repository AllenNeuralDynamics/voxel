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
- **The HTTP layer is a try-out** in `prototypes/interface/` (`web.py`, `demo.py`), on the real code. The real one is
  `vxl.station.api` (`station.md`); the try-out goes when it is built.

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

## HTTP rules for `vxl.station.api`

Built in the try-out; the real API keeps them.

- **Errors** are `application/problem+json` (RFC 9457) with `type`, `title`, `status`, `detail`, `instance`, and an
  `errors` member listing refused arguments. `400` not JSON, `404` unknown item, device or operation, `409` busy,
  `422` refused, `500` other. Unknown routes answer the same way.
- **`ETag` on every read and every answer with an item**: a hash of that item. `If-Match` on update and delete
  answers `412` when stale; `If-None-Match` on a read answers `304`. `If-Match` is optional for now; the UI always
  sends it. Require it (`428`, RFC 6585) when many users share a station.
- **PATCH is `application/merge-patch+json`** (RFC 7396): the API merges the patch into the current item and calls
  the method with whole field values.
- **A write answers the item and its `ETag`, plus `Vxl-Feed-Cursor`**, an opaque Structured Field String
  (RFC 9651), so the UI can wait until its feed caught up. No `X-` prefix (RFC 6648). Browsers need
  `Access-Control-Expose-Headers` to read it.
- **An action that starts an activity answers `202` with a `Location`** to the activity or the run (AIP-151, Azure
  `operation-location`), seen from the method's return type. Short actions answer `200` or `204`.
- **Device routes go through the instrument:** `PATCH /devices/{id}` calls `set_device_properties`,
  `POST /devices/{id}:{operation}` calls `execute_device_command`, both through the scheduler, checked against
  `view.devices[id].interface` and refused with `422` before reaching the device.
- Under a gateway, every route sits under `/stations/<id>/` (`gateway.md`).

## SPIM routes, as an example

| Route | Method |
| --- | --- |
| `GET /plan`, `GET /plan/{task_id}` | from the view |
| `POST /plan`, `PATCH /plan/{task_id}`, `DELETE /plan/{task_id}` | `add_task`, `update_task`, `remove_task` |
| `POST /plan:reorder` | `reorder` |
| `PATCH /profiles/{profile_id}`, `PATCH /writer`, `PATCH /preview` | `update_profile`, `update_writer`, `update_preview` |
| `POST /preview:start`, `POST /preview:stop` | `start_preview`, `stop_preview` |
| `GET /openapi.json` | made by FastAPI from all of the above |

## Open

- Status codes for create and no content: `201` and `204`, or `200` everywhere.
- `Vec3D` (`vxlib`) has no JSON Schema, so the view schema cannot be made as is.
- A `NotFoundError` next to `RejectedError`, so methods can say "no such item" themselves.
- Versioning: the guides disagree (AIP `/v1/`, Azure `api-version`, Zalando media type); nothing to cite as the
  standard.
- `Idempotency-Key` for retries is still an Internet-Draft.

## References

Google AIP-131 to 136, 151, 154, 156, 193, 235; RFC 9110, 9457, 7396, 6585, 6648, 8259, 9651; OpenAPI 3.1; Zalando
RESTful API guidelines; Azure REST API guidelines; FastAPI; Django REST Framework; gRPC transcoding.
