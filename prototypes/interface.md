# Instrument interface

**Status, 2026-11-18:** built. Decorators that declare an operation live in `rigup/src/rigup/interface.py` (named
"marks" until the same day); vxl checks each kind against its state and gives routes and `InstrumentInterface` in
`src/vxl/instrument/interface.py`; `Instrument.execute(name, args)` runs an operation by name. The HTTP layer
is still a try-out in `prototypes/interface/` (`web.py`, `demo.py`), now on the real code; the real one comes with the
web layer step. Terms: a decorator records a **declaration**; the description clients read is an
**`OperationInfo`**; "operation" replaces "command" everywhere.

The sections below record how the design was reached, in order; later sections replace earlier ones where they
disagree.

## Sources

| Source | What we take |
| --- | --- |
| Google AIP-131 to 135 (standard methods) | Get and List are `GET`; Create is `POST` on the collection; Update "should be `PATCH`", with the fields sent as the mask; Delete is `DELETE` with no body. `PUT` is "strongly discouraged". |
| AIP-136 (custom methods) | For what standard methods cannot express: `GET` when it only reads, `POST` when it has side effects. Prefer standard methods. |
| AIP-156 (singletons) | One per parent, no ID, Get and Update only, never Create or Delete. |
| RFC 9110, 9.2 and 9.3.5 | `GET` is safe. `PUT`, `DELETE` and safe methods are idempotent. Content in a `DELETE` has no defined meaning. |
| Django REST Framework (ViewSet, `@action`, routers) | Standard actions plus custom `@action`s; a router makes every route from them. |
| gRPC transcoding (`google.api.http`) | Methods are declared once; the HTTP mapping is derived. Unbound fields go into the body. |
| FastAPI | Signatures become schemas and OpenAPI. Its path parameters are matched by name; ours are named in the declaration. |

## Rules

1. **The instrument knows no HTTP.** Declarations say what a method does to the instrument. The web server maps that to
   HTTP; Qt, scripts and tests call the methods directly.
2. **Reads need no declarations.** Every `GET` of a resource is served from the view.
3. **3 standard declarations, 3 custom declarations.** Nothing else.
4. **Nothing is inferred from names.** A declaration names its resource and its key. The checks below run when the class is
   defined.

## The declarations

| Declaration | Does | HTTP | Body |
| --- | --- | --- | --- |
| `@create("plan")` | adds an item to a collection | `POST /plan` | every argument |
| `@update("plan", key="task_id")` | changes some fields of 1 item | `PATCH /plan/{task_id}` | the other arguments |
| `@update("writer")` | changes some fields of a singleton | `PATCH /writer` | every argument |
| `@delete("plan", key="task_id")` | removes 1 item | `DELETE /plan/{task_id}` | none |
| `@query` | reads, with arguments, without changes | `GET /:name` | none; arguments in the query |
| `@action` | anything else that changes the instrument | `POST /:name` | every argument |
| `@failsafe` | makes the instrument safe; takes no arguments | `POST /:name` | none |

`@query`, `@action` and `@failsafe` take `on="plan"` to belong to a resource: `POST /plan:reorder`.

- **No `PUT`.** AIP-134 discourages it, and `PATCH` with every field covers replacement.
- **A camera region is an update**, though it moves hardware. The method is about what the client may assume:
  setting the same region twice leaves the same state.
- **Batch delete is a custom method**, as AIP-235 does it (`POST /plan:batchDelete`), because a `DELETE` has no
  body. Several single deletes would be several undo steps.

## Checks when the class is defined

1. The resource is a path in the kind's view model (`SPIMView`), such as `state.plan` written as `plan`.
2. `@create`, `@delete` and `@update` with a `key` target a **collection**: a `Mapping[Id, Model]` in the view.
   `@update` without a `key` targets a **singleton**: a model.
3. `key` is an argument of the method, of the collection's key type.
4. `@update` takes only fields of the item: its arguments are a subset of the model's fields, all optional, as a
   `**fields: Unpack[SomeFields]` with `total=False`.
5. `@failsafe` takes no required arguments.
6. No 2 declarations make the same route.

One test builds the route table of every kind we ship.

## One rule for the state: collections are maps

`plan` is a `list[Task]` today, found by each task's `id`. Rule 2 asks for `Mapping[TaskId, Task]` instead: a dict
keeps its order, and the key is the type itself, so no "key field" rule is needed. Reorder stays a custom method.

## SPIM, declared

```python
class Microscope(Instrument[SPIMConfig, SPIMState, SPIMView]):
    @create("plan")
    async def add_task(self, task: Task) -> None: ...

    @update("plan", key="task_id")
    async def update_task(self, task_id: TaskId, **fields: Unpack[TaskFields]) -> None: ...

    @delete("plan", key="task_id")
    async def remove_task(self, task_id: TaskId) -> None: ...

    @action(on="plan")
    async def reorder(self, task_ids: Sequence[TaskId]) -> None: ...

    @update("profiles", key="profile_id")
    async def update_profile(self, profile_id: ProfileId, **fields: Unpack[SPIMProfileFields]) -> None: ...

    @update("writer")
    async def update_writer(self, **fields: Unpack[WriterFields]) -> None: ...

    @update("preview")
    async def update_preview(self, *, channels: Collection[DeviceId]) -> None: ...

    @action
    async def start_preview(self) -> None: ...

    @failsafe
    async def stop_preview(self) -> None: ...
```

| Route | Method |
| --- | --- |
| `GET /plan`, `GET /plan/{task_id}` | from the view |
| `POST /plan` | `add_task` |
| `PATCH /plan/{task_id}` | `update_task` |
| `DELETE /plan/{task_id}` | `remove_task` |
| `POST /plan:reorder` | `reorder` |
| `PATCH /profiles/{profile_id}` | `update_profile` (replaces `set_spacing`) |
| `PATCH /writer` | `update_writer` |
| `PATCH /preview` | `update_preview` |
| `POST /:start_preview`, `POST /:stop_preview` | `start_preview`, `stop_preview` |
| `GET /openapi.json` | made by FastAPI from all of the above |

## Where the code goes

- `rigup`: the command declarations and the argument model builder move from `rigup.device` to a shared module
  (`rigup.interface`); devices keep `@query`, `@action`, `@failsafe`. The builder learns `**fields: Unpack[TypedDict]`:
  today `params_model` refuses `**kwargs`.
- `vxl.instrument.interface`: `create`, `update`, `delete`, and the checks against the view model. Kind authors
  import every declaration from here.
- `vxl.station.web`: reads the declarations of the open instrument and registers 1 FastAPI route per declaration.

## Open

- Conflicts: send the store revision as an `ETag` and accept `If-Match`, as AIP-154 suggests.
- Status codes: `201` for create, `204` for no content, or `200` everywhere.
- Device commands over the same server: `/devices/{id}/:name` from each device's interface.

## Prototype and review, 2026-11-18

Built in `prototypes/interface/`: `declarations.py`, `operations.py`, `instrument.py` (vxl checks, `InstrumentInterface`),
`web.py` (routes), `spim.py` (a declared SPIM subclass), `demo.py` (real HTTP run), `test_marks.py` (28 cases).
Run: `uv run python -m prototypes.interface.demo` and `uv run pytest -q prototypes/interface/test_marks.py`.

Changes to the design above, from building it:

- **Collections are lists with a `Key` field, or maps.** Lists keep order in JSON (RFC 8259: objects are unordered).
- **`@create` takes `key=` for a map**: the client chooses the new key (AIP-133).
- **`InstrumentInterface` has no `devices`**: `view.devices` already holds each device's interface.
- **Errors**: `400` not JSON, `404` unknown item, device or command, `409` busy, `422` refused, `500` other.
- **Keys contain no `/` or `:`**, so an item path never matches a custom method.
- **More checks**: positional-only arguments, a missing `self`, a key with a default, declarations under `@property`, and an
  override that changes what an operation does are refused.

Found while building:

- `Vec3D` (`vxlib`) has no JSON Schema, so the view schema cannot be made as is.
- `RejectedError` covers every refusal; a `NotFoundError` would let methods say "no such item" themselves.

Decisions for the real build:

1. **1 request = 1 undo step.** A declared method must be 1 state edit; `StateEdit` needs to record several paths at
   once (today `edit_profile` makes 2 undo steps).
2. **Declaration the real methods**, no wrappers: 1 Python name per operation.
3. **Run the checks in `Instrument.__init_subclass__`**, so a bad declaration fails on import.
4. **Unify with rigup**: 1 `Declaration`, 1 argument builder with `Unpack` support, `CommandInfo` and `OperationInfo` as 1
   model (`operation` or `command` as the word).
5. **What a write answers**: the item, or `204` plus the feed cursor so the feed stays the 1 source of state.
6. **Device routes** built from `DeviceInterface` with the same runner, so arguments are checked.

Standards gaps, checked on the web on 2026-11-18:

| Gap | Source | What it says |
| --- | --- | --- |
| Error bodies | RFC 9457 §1, §3 (obsoletes RFC 7807); Zalando #176 MUST | `application/problem+json` with `type`, `title`, `status`, `detail`, `instance`; extension members allowed (for validation errors). Google (AIP-193) and Azure use their own `{"error": {...}}` instead |
| Conflicts | RFC 9110 §8.8.3, §13.1.1, §15.5.13; RFC 6585 §3 | `ETag` + `If-Match`; on a stale tag the server MUST NOT perform the method, `412` is the usual answer (a MAY). `428` when a tag is required but missing |
| | AIP-154 | Google puts the etag in the request body and answers `ABORTED` = `409` (changed from `400` in 2021). It differs from RFC 9110: pick 1 |
| PATCH format | RFC 7396 §1–4; Zalando #148 (first choice) | `application/merge-patch+json`: `null` removes a member, arrays are replaced whole |
| Custom methods at the root | AIP-136 | Methods may attach to resources, collections or services, but every example sits under a resource path; a root `/:verb` has no example. Give root commands a noun: `/preview:start` |
| Long actions | AIP-151; Azure guidelines | Google returns an Operation the client polls by name; Azure answers `202` with an `operation-location` header |
| Retries | draft-ietf-httpapi-idempotency-key-header-08 | Still an Internet-Draft, not an RFC: `Idempotency-Key` on POST and PATCH |
| Versioning | AIP (`/v1/` in the path); Azure (`api-version` query, required); Zalando #113–115 (avoid; media type; never in the URL) | The guides disagree; nothing to cite as the standard |
| OpenAPI | OpenAPI 3.1 §3.2, §4.4, §4.8.12.2, §4.9 | Every path template variable declared `in: path, required: true` (now done); `x-` extensions allowed; schemas are JSON Schema 2020-12 |
| JSON order | RFC 8259 §1 | "An object is an unordered collection": the reason ordered collections are lists |

## Decided 2026-11-18: RFC 9110 and RFC 9457

Built in the prototype:

- **Errors** are `application/problem+json` (RFC 9457) with `type`, `title`, `status`, `detail`, `instance`, and an
  `errors` member listing refused arguments. Unknown routes answer the same way.
- **Every read and every answer with an item carries an `ETag`**: a hash of that item, so an edit to 1 item leaves
  the others' tags valid. `If-Match` on update and delete answers `412` when stale; `If-None-Match` on a read answers
  `304`. `If-Match` is optional for now; requiring it would add `428` (RFC 6585).

## Decided 2026-11-18: updates, undo and inheritance

- **1 request = 1 undo step holds already**: `StateEdit.record` writes many paths at once, all or nothing (the store
  validates the whole state on commit), and refuses a second record. The 2 undo steps seen earlier came from the
  prototype's `edit_profile` calling 2 methods (`set_spacing` and `update_profile_details`), split because spacing is
  a SPIM field and label and notes are base fields. Fixed in the prototype: 1 edit, and 1 undo restores both.
- **Updates keep `**fields: Unpack[SomeFields]`** (`TypedDict`, `total=False`). Patch models were considered; they only
  help with a type parameter, which adds a 4th type argument to `Instrument`.
- **A resource that kinds extend is declared by the kind, not the base.** Each kind declarations its own `update_profile` with
  its own fields; the base gives an undeclared helper that records them as 1 edit. The base never runs alone (a target
  needs config and state classes), so no instrument is left without it. An override cannot add `Unpack` fields: the
  type checker refuses it, because a `TypedDict` is open.
- **The base declarations only operations every kind has in full**: undo, redo, apply profile, device operations.
- **An override of a declared method repeats the declaration and keeps its signature and what it does** (checked at load).
- **Never call `super()` for an edit inside a declared edit**: that is 2 state edits. Share work with helpers that
  return values, or record once in a base helper.
- **Guard, to build**: the operation runner checks that a `create`, `update` or `delete` made at most 1 history entry,
  and 1 test runs it over every shipped kind.
- **`BasicInstrument`** (decided 2026-11-18): a ready-made kind in `vxl.instrument.basic` (moved from `vxl.instruments.basic` on 2026-11-19), `Instrument[InstrumentConfig,
  InstrumentState, InstrumentView]`, that declarations `update_profile` with the base `ProfileFields`. A `rig.yaml` can name it
  and run with no code. Kinds still subclass `Instrument` and declaration their own `update_profile`. The base keeps the name
  `Instrument`, because type hints use it for "any instrument". The base helper `_update_profile` does the edit;
  `update_profile_details` and SPIM's `set_spacing` go away.
- **Declarations live in `rigup.interface`, and the word is "operation"** (decided 2026-11-18). 1 `Declaration`, 1 argument builder (with
  `Unpack` support), 1 `OperationInfo` for devices and instruments: rigup's `CommandInfo` becomes `OperationInfo`,
  `DeviceInterface.commands` becomes `operations`, `execute_command` becomes `execute`. The checks against a state
  model stay in vxl.
- **Nested-edit guard, tried 2026-11-18 and reverted**: a `ContextVar` in `_state_edit` that raises when a state edit
  opens inside another. With it, all 1021 tests, the 28 prototype tests and the demo pass, so nothing nests today; a
  nested edit is refused with "'Update profile details' opens a state edit inside 'Spacing and label'". Found: the
  refusal comes after the outer edit already recorded, so its change stays saved. `_state_edit` should undo its own
  recorded change when its block raises, so an edit block is all or nothing.
- **Joined edits, built 2026-11-18 in `src/vxl/instrument/base.py`** (replaces the refusing guard). An edit opened inside another joins it
  (a `ContextVar` holds the open edit). Each record saves at once, so the block reads the latest state; the edit keeps
  each path's value before its first record and after its last; the outermost block makes 1 history entry; if the
  block raises, every path goes back to its value before the edit. `StateEdit` may record more than once. Results:
  all 1021 tests and the 28 prototype tests pass; a nested edit (spacing + `update_profile_details`) is 1 undo step and
  1 redo; a refused nested edit and a failure after a record both roll the edit back. Remaining: screens may see the
  first half for a moment, and each record must be valid on its own. This removes the "never call `super()`" rule.

## Decided 2026-11-18: answers, devices, versions, PATCH, nouns, long actions

1. **A write answers the item and its `ETag`, plus a feed cursor header**, so the UI can wait until its feed has caught
   up. Checked on the web: no standard header exists for this (vendors each use their own); RFC 6648 (BCP 178, current)
   and RFC 9110 §16.3.2.1 say no `X-` prefix, and §16.3.2.1 suggests an app prefix for an app-only header; Azure also
   says no `x-`. The value is an opaque Structured Field String (RFC 9651, which obsoletes RFC 8941), since the feed
   cursor is `{stream_id, seq}`. Do not reuse `Last-Event-ID`: the SSE spec defines it as a request header only. A
   browser client needs `Access-Control-Expose-Headers` to read it. The header is `Vxl-Feed-Cursor`.
2. **Device routes stay, and always go through the instrument**: `PATCH /devices/{id}` calls
   `set_device_properties`, `POST /devices/{id}:{operation}` calls `execute_device_command`, both through the
   scheduler. Each request is checked against that device's interface (`view.devices[id].interface`) and refused with
   `422` before it reaches the device. They exist for device control during a session; `vxl devices shell` covers
   devices outside an instrument.
3. **`If-Match` is optional** for now (AIP-154 makes the etag optional too); the UI always sends it. Require it (`428`,
   RFC 6585) when many users share a station.
4. **PATCH is `application/merge-patch+json`** (RFC 7396): the HTTP adapter merges the patch into the current item
   (deep merge for objects, arrays replaced, `null` removes) and calls the method with whole field values, so Python
   methods keep "replace these fields".
5. **Instrument operations at the root get a noun**: `@action(on="preview", verb="start")` gives
   `POST /preview:start`. `on` is checked against the state only when it names a state path. Devices are unaffected:
   their noun is the device (`/devices/{id}:{operation}`), and the options default to nothing.
6. **An action that starts an activity answers `202` with a `Location`** to the activity or the run (AIP-151,
   Azure `operation-location`); the adapter sees it from the method's return type, no flag. Short actions answer
   `200` or `204`.
