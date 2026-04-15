# rigur vs rigup — divergence log

Short notes on every intentional departure from rigup. Newest on top; each entry
should be a few lines — what changed, where, and why. Deeper discussion lives in
the conversation/PR that introduced the change, not here.

## Rig (Stage 2)

### New `rigur/rig.py` — Rig class (no ClusterManager)
- **Where:** `src/rigur/rig.py`.
- **What:** `Rig` takes a `RigConfig`, creates `Node` instances (one
  `LocalNode` for `config.devices`, plus `SubprocessNode`/`RemoteNode` for
  each entry in `config.nodes`), and exposes a unified `devices` property.
- **API:** `open()` (create + open nodes + build all devices) and `close()`
  (close everything). No `build()` method — device construction is fully
  implicit in `open`. Build errors accumulate in `rig.build_errors`.
- **Key divergence from rigup:**
    - **No `ClusterManager`.** rigup has `Rig` → `ClusterManager` → nodes.
      rigur's `Rig` directly owns `Node` instances. The coordinator class
      was removed because it had no independent responsibility — everything
      it did is now either in the `Node` layer or in `Rig` itself.
    - **No `node_cls()` classmethod.** rigup's extension model was
      `Rig.node_cls()` → `VoxelNode` → custom controllers/handles. rigur
      returns generic `DeviceHandle` instances; typed wrappers live in the
      application layer (`VoxelRig` composes `Rig`, doesn't subclass it).
    - **`devices` is computed.** Merges all nodes' device dicts on access —
      always reflects current state, no stale cache.
    - **Close in reverse order.** Transport nodes close before local,
      matching dependency order (remote devices may depend on local ones).

### `rigur-node` console script
- **Where:** `pyproject.toml` → `rigur.node._runner:standalone_main`.
- **What:** Entry point for manually-run remote node daemons. Currently
  raises `NotImplementedError`; will gain proper argparse (--port, --host)
  when the standalone remote daemon workflow is fully wired.

## Node layer (Stage 2)

### New `rigur/node/` subpackage — full node layer
- **Where:** `src/rigur/node/{__init__.py,_base.py,_local.py,_transport.py,
  _remote.py,_subprocess.py,_daemon.py,_runner.py}`.
- **What:**
    - `Node` ABC with `open`, `close`, `build_devices`, `close_device`,
      `close_all_devices`, `devices` (property). `build_devices` returns a
      `(handles, errors)` tuple matching `build_objects_async`'s accumulation
      pattern. **Declarative:** always closes existing devices before building.
    - `LocalNode` + `LocalAdapter[D]` — in-process, no transport.
    - `TransportNode` — shared base for subprocess/remote. Implements device
      build/close via `protocol.call()` over a `TransportClient`.
    - `TransportAdapter[D]` — routes device RPC through a shared per-node
      `TransportClient`. One adapter per device, all sharing one transport.
    - `SubprocessNode(TransportNode)` — spawns a child process via
      `asyncio.create_subprocess_exec`. Defaults to IPC transport (faster
      than TCP, no port allocation). Falls back to TCP when config specifies
      an address. Terminates subprocess on close (graceful → SIGTERM → SIGKILL).
    - `RemoteNode(TransportNode)` — connects to an externally supervised
      process. Claims authority on open, releases on close. Does NOT
      terminate the process.
    - `NodeDaemon` — server-side runtime. Blank executor: no config of its
      own, builds whatever the orchestrator sends. Registers protocol handlers
      for all actions (claim/release, build/close, device RPC, ping, shutdown).
      Identical code for subprocess and remote deployments.
    - `_runner.py` — subprocess entry point (`subprocess_main`) and future
      standalone CLI (`standalone_main`).
- **Naming decisions:**
    - Client-side: `Node` (ABC), `LocalNode`, `SubprocessNode`, `RemoteNode`.
    - Server-side: `NodeDaemon` — "Daemon" chosen over "Service" (overloaded),
      "Host", "Agent", or "Controller."
- **Key divergence from rigup:**
    - rigup's `ClusterManager` + `RigNode` + `LocalNodeProcess` are replaced
      by the `Node` ABC + three concrete implementations. Cleaner separation:
      each node kind owns its own lifecycle (spawn vs connect vs in-process).
    - rigup's `RigNode` was monolithic (server-side service); rigur splits
      into `NodeDaemon` (server) and `TransportNode` (client).
    - `build_devices` is declarative: always closes existing devices first.
    - `NodeDaemon` is a blank executor — no config pushed at construction,
      no `GET_CONFIG` validation. Build failures are the validation.
    - `SubprocessNode` defaults to IPC (Unix domain sockets) for same-host
      communication — no port allocation, no TOCTOU race, lower latency.
    - `LocalAdapter` co-located with `LocalNode`; `TransportAdapter`
      co-located with `TransportNode`. Each adapter is only used by its node.

## Protocol (Stage 2 groundwork)

### Rewrote `rigur/protocol.py` as the typed action vocabulary + dispatch layer
- **Where:** `src/rigur/protocol.py` (replaces the old lift from rigup that
  defined `NodeMessage`/`RigMessage` dataclasses).
- **What:**
    - `Action` and `Notify` enums — the full vocabulary spoken on the
      reliable channel (claim/release, list/build/close devices, device RPC,
      ping, heartbeat/shutdown notifies).
    - Pydantic payload models for every action (`ClaimRequest`,
      `BuildDevicesRequest`/`Response`, `HeartbeatPayload`, etc.). Device
      RPC responses are re-exported from `rigur.device` (`Results`,
      `PropResults`, `DeviceInterface`) — no duplicate shapes.
    - `Dispatcher` class that maps `action → (req_model, resp_model, handler)`
      and exposes `handle_request(action, bytes) → bytes` /
      `handle_notify(action, bytes) → None` for transport consumption.
      Serialization is owned here; higher layers only see typed models.
    - `call(transport, action, request, response_model, timeout)` —
      typed client-side helper. Dispatches to `transport.request` or
      `transport.push_request` depending on which side (Client vs Server) is
      calling, so either side of DEALER/ROUTER can initiate.
    - `send_notify(transport, action, payload)` — typed notify helper.
    - `bind(dispatcher, peer)` — wires a dispatcher into either a
      `TransportClient` or `TransportServer` via a one-liner.
- **Why this shape:**
    - Protocol knows nothing about ZMQ. Transport moves bytes; protocol
      converts between pydantic and bytes. Clean separation means a future
      non-ZMQ transport can reuse this module unchanged.
    - Symmetric `call` / `send_notify` over `TransportClient | TransportServer`
      matches the bidirectional DEALER/ROUTER reality — rig can request node,
      node can push-request rig, both use the same helpers.
    - `Action` / `Notify` as `StrEnum` gives us type-checked action strings at
      use sites while staying interoperable with any string.
- **Dropped from rigup's version:**
    - `NodeMessage`/`RigMessage` dataclasses — their framing concerns (empty
      delimiter frame, identity handling) are now transport-layer concerns,
      not protocol. Protocol doesn't know multipart frames exist.
    - Manual `to_parts`/`from_parts` multipart assembly — superseded by
      pydantic `model_dump_json` / `model_validate_json`.
    - Asymmetric `NodeAction` / `RigAction` enums — unified into one
      `Action` enum since either side can send any action over DEALER/ROUTER.

## Transport (Stage 2 groundwork)

### New `rigur/transport/` package — per-node, bidirectional, wire-agnostic
- **Where:** `src/rigur/transport/{_base.py,_zmq.py,__init__.py}`.
  The implementation file is `_zmq.py` (underscored) to avoid shadowing the
  `pyzmq` package — a top-level `import zmq` inside a module named `zmq.py`
  is ambiguous and breaks attribute lookups. Classes are re-exported from
  `transport/__init__.py` so callers write `from rigur.transport import
  ZMQTransportClient` and never see the underscore.
  Old per-device code lives in `src/rigur/transport_old/` for reference only.
- **What:** Two ABCs — `TransportClient` and `TransportServer` — plus a
  `NodeAddress` hierarchy (`TCPAddress`, `IPCAddress`, `INPROCAddress`) and
  the ZMQ implementations `ZMQTransportClient` / `ZMQTransportServer`.
- **Key design decisions (diverging from rigup's `transport_old/` shape):**
    - **Per-node, not per-device.** One socket pair per rig↔node connection
      instead of per-device. Authority, cluster close, and heartbeat all land
      on the single node connection. Devices multiplex via the protocol layer
      on top.
    - **Bidirectional DEALER/ROUTER** replaces per-device REQ/REP. Either
      side can send `request` (await response), `notify` (fire-and-forget),
      or respond to the other's `request`. Concurrent in-flight requests are
      correlated by 32-bit request IDs.
    - **Three message kinds** on the reliable channel — `REQUEST`,
      `RESPONSE`, `NOTIFY` — encoded as the leading byte of the multipart
      frames. Request-ID correlation is transport-owned; higher layers just
      await `request` and get bytes back (or a `TransportError`).
    - **Pub/Sub for streams, unchanged in spirit.** Node publishes to topics,
      rig subscribes. Lossy by design so high-volume data (frames, property
      changes) does not back-pressure the reliable channel.
    - **Symmetric API shape.** Both `TransportClient` and `TransportServer`
      expose `request` / `notify` outgoing methods and `on_request` /
      `on_notify` handler registration — because DEALER/ROUTER genuinely
      allows either side to initiate. Server's outgoing methods are named
      `push_request` / `push_notify` for clarity; they target the single
      tracked peer identity.
    - **Actions are just strings** at the transport boundary. The vocabulary
      (`build_device`, `run_command`, etc.) is defined by the protocol layer
      above, not transport.
    - **Transport addresses are typed**, not bare strings. `TCPAddress`
      defaults `pub_port` to `rpc_port + 1` when omitted; `as_bind()`
      produces a server-side variant with `host=0.0.0.0`.
    - **Error responses are explicit.** A handler raising produces a
      `[status=b"err", error_message_bytes]` response frame pair, which the
      caller's `request` raises as `TransportError`. No silent-drop or
      timeout-to-detect.
    - **Single-peer server model.** `ZMQTransportServer` tracks one peer's
      identity; `push_*` raises if no peer has been seen yet. Matches the
      "one orchestrator per rig" authority model.
- **Dependency note:** transport only depends on `pydantic`, `pyzmq`,
  `vxlib` (for `Unsub`). Knows nothing about devices, commands, or configs
  — the protocol layer (next) bridges those to this transport's raw-bytes
  API.

## Config schema (Stage 1)

### `build.py` moved from `device/` to package root
- **Where:** `src/rigur/build.py` (was `src/rigur/device/build.py`).
- **What:** `BuildConfig`, `BuildError`, `build_objects`, `build_objects_async`
  are no longer under the `device` module. Their exports were removed from
  `device/__init__.py`.
- **Why:** Building objects from target+init+defaults specs is a
  framework-level concern, not tied to the `Device` abstraction specifically.
  Keeping it at package root makes it reusable for any object graph (nodes,
  controllers, devices) and keeps the device layer focused on device APIs.

### New `rigur/config.py` with `RigConfig` / `NodeConfig`
- **Where:** `src/rigur/config.py`.
- **What:** Defines `RigConfig` (`name` + top-level `devices` + `nodes`),
  `NodeConfig` (with `kind`, `address`, `allow_extras`, `devices`), and a
  `NodeKind = Literal["subprocess", "remote"]` alias. `DeviceConfig` is an
  alias of `BuildConfig` re-declared in this module.
- **Key schema decisions (diverging from rigup — see comparison at bottom):**
    - In-process devices live at the rig level (`RigConfig.devices`); nodes
      are always separate processes. *No `local` node kind* — the local case
      is the absence of a node, not a kind of one.
    - `NodeKind` has two values: `subprocess` (cluster-manager-spawned) and
      `remote` (externally supervised). Both may live on localhost; the
      difference is who owns the process lifetime.
    - `kind` is autofilled from `address` by a `before` validator when not
      specified: missing or localhost-shaped address → `subprocess`, other
      address → `remote`. Explicit `kind` always wins.
    - `address` is a full ZMQ endpoint (e.g. `tcp://10.0.0.2:5555`,
      `ipc:///tmp/foo`), not a bare hostname.
    - No `from_yaml` helper — loading is the caller's responsibility.
    - No derived properties (`local_nodes`, `remote_nodes`, `device_uids`) —
      the typed schema is the API; add grouping helpers only if needed.
- **Runtime counterpart:** `Rig` creates a `LocalNode` for
  `RigConfig.devices` and `SubprocessNode`/`RemoteNode` for each
  `RigConfig.nodes` entry — uniform `Node` iteration at the Rig layer.

## Device layer cleanups (Stage 0)

### `DeviceController.stop_streaming` / `close` are now async; cancellation is awaited
- **Where:** `device/controller.py`.
- **What:** `stop_streaming` was sync, cancelling the stream task and
  immediately dropping the reference. It is now `async`, awaits the cancelled
  task (with `CancelledError` suppressed), then nils the reference.
  Consequently `close` is also `async`. `start_streaming` stays sync because
  it only creates a task (no await needed).
- **Why:** Without awaiting after cancel, the runtime can drop the task
  reference while the coroutine is mid-flight — producing "Task was destroyed
  but it is pending!" log noise and leaving any in-flight `publish` calls
  racing teardown. Awaiting also lets the loop's own `CancelledError` handler
  run, so the task exits cleanly instead of being garbage-collected.
- **Note:** `Device.close()` (called from `DeviceController.close`) remains
  sync — making it async is a separate item (6 in the review).

### Failed `defaults` abort the device's build
- **Where:** `device/build.py` — sync `_build_one` and async `_build_group_sync`.
- **What:** A `setattr` exception while applying `BuildConfig.defaults` used to
  be downgraded to a `logger.warning`. It now produces a
  `BuildError(error_type="defaults", ...)` and removes the device from the
  built map. Added `"defaults"` to `BuildError.error_type`'s Literal.
- **Why:** A swallowed default means the device's initial state diverges from
  the config with no signal to the caller. Per-device classification matches
  the existing pattern for instantiation failures — batch continues, errors
  accumulate and surface at the end.
- **Note:** This fixes only the "setattr raised" path. If a descriptor
  *silently clamps* an invalid value (e.g., `@deliminated_float` logging a
  warning and snapping to bounds), build still returns success. That's a
  descriptor-semantics question (clamp vs raise) left for later.
- **Provisional — may relax later.** Strict "fail the device on a raising
  default" may prove too sharp in practice. If noise from legitimate edge
  cases accumulates, the fallback is to change this from a `BuildError` back
  to a structured warning recorded alongside the built device (e.g., a
  `warnings: dict[str, BuildError]` in the result tuple) — keeping the
  diagnostic information but allowing the device to be used.

### Dropped `Device.__COMMANDS__`
- **Where:** `device/base.py` (`Device` class).
- **What:** Removed the `__COMMANDS__: ClassVar[set[str]]` class variable.
- **Why:** Command discovery is now solely via `@describe`. Two discovery paths
  (a magic class attribute plus a decorator) was ambiguous; one is simpler and
  makes the exposed surface visible at each method definition.

### `collect_commands` / `collect_properties` → `@describe` only
- **Where:** `device/base.py`.
- **What:** Both collectors lost their `strict` parameter. They now only return
  members carrying `@describe`. The old TODO about the decorator's double-duty
  is resolved: `@describe` is *both* the "remotely callable" marker *and* the UI
  metadata source. Public methods without it are treated as internal.
- **Why:** Predictable, allowlist-based command surface. No accidental exposure.

### Removed `PropsCallback`; adapter exposes a `Signal`
- **Where:** `device/base.py`, `device/handle.py`, `device/__init__.py`.
- **What:** Deleted the `PropsCallback = Callable[[PropResults], Awaitable[None]]`
  alias. `Adapter.on_props_changed(callback)` is now a `props_changed:
  Signal[PropResults]` abstract property; `DeviceHandle` forwards it.
- **Why:** The old API was single-callback last-wins. `Signal[T]` supports
  multiple subscribers with uniform (un)subscribe semantics and matches the
  reactive primitives already in vxlib.

### Dropped `DeviceHandle.device_type()`
- **Where:** `device/handle.py`.
- **What:** Method removed; callers should use `(await handle.interface()).type`.
- **Why:** Redundant with `interface()`; both paths cached the same lazy fetch.

### `runcmd` accepts a logger parameter
- **Where:** `device/base.py`.
- **What:** `runcmd` gained `log: logging.Logger = logger` parameter,
  defaulting to the module-level logger. `get_command_help` and
  `list_commands` still use the module logger directly.
- **Why:** Decouples the most commonly called dev utility from the hardcoded
  logger so callers can route output to their own loggers.

### Documented per-device 1-worker `ThreadPoolExecutor`
- **Where:** `device/controller.py` (`DeviceController.__init__`).
- **What:** Added a comment explaining the choice — one worker per device
  serializes sync calls into a single SDK (most hardware libs are not
  thread-safe), while separate pools per device isolate them from each other.
- **Why:** The choice was load-bearing but undocumented; future readers would
  otherwise be tempted to share a pool and break SDK thread assumptions.

### Renamed `Device.log` → `Device.logger`
- **Where:** `device/base.py`.
- **What:** Instance attribute renamed.
- **Why:** Consistency (`logger` matches the module-level convention elsewhere).

## Dependencies

### Added `vxlib`
- **Where:** `pyproject.toml`.
- **Why:** Needed for `Signal` on `Adapter.props_changed`. Accepted as a direct
  runtime dependency for now; revisit if rigur ever needs to stand fully alone.

## Tests

### Test suite — 67 tests across 7 files
- **Where:** `tests/`.
- **What:** Unit + integration tests covering the full stack:
    - `test_config.py` (14) — NodeConfig autofill, validation, RigConfig shape
    - `test_build.py` (6) — defaults-as-BuildError, sync + async build
    - `test_protocol.py` (8) — Dispatcher dispatch, enum support, error propagation
    - `test_local_node.py` (11) — LocalNode + LocalAdapter full device path
    - `test_rig.py` (6) — Rig end-to-end with local-only config
    - `test_transport.py` (10) — ZMQ DEALER/ROUTER, concurrency, PUB/SUB, errors
    - `test_daemon.py` (12) — NodeDaemon authority, device lifecycle, RPC over wire
- **Shared fixture:** `tests/_mock.py` defines `MockDevice` (a `Device`
  subclass with @describe-decorated commands and properties).
- **Not tested yet:** SubprocessNode spawning (requires process management),
  RemoteNode integration (structurally identical to daemon tests).

## Deferred decisions

### `Adapter.device` leak left as-is
- **Where:** `device/handle.py` (`Adapter.device` returns `D | None`).
- **What:** Kept the property exposing the raw device for local adapters.
- **Why:** Deferred — transport-concern leak is real, but small enough to
  revisit when it causes a concrete problem.

### `Command` `*args`/`**kwargs` validation gap left as-is
- **Where:** `device/base.py` (`Command._create_param_model`).
- **What:** Kept the current behaviour of silently skipping `*args`/`**kwargs`
  from pydantic validation.
- **Why:** Deferred; no concrete failure yet.

### `Device.close()` remains sync
- **Where:** `device/base.py`.
- **What:** Device's `close` is still sync (`def close`), even though
  `DeviceController.close` is now async. A device needing async teardown
  (e.g., `await stop_acquisition()`) can't express it cleanly.
- **Why:** Deferred — would require `DeviceController.close` to detect and
  await an async `Device.close`. Small change when needed.
