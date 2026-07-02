# rigup

A framework for controlling hardware devices — locally, in a child process, or across networked machines — with a single async API and a single YAML config. Devices are declared in configuration, driven through typed async handles, and behave identically no matter where they run.

## Mental model

Every device passes through four layers:

```
Device            hardware abstraction — one subclass per device (rigup.device.driver)
  └─ DeviceController   introspects @describe'd members, runs commands, streams properties
       └─ Adapter       Local (in-process) or Transport (over the wire)
            └─ DeviceHandle   the public async API
```

A **`Rig`** groups devices into **`Node`s**. A node is one of three kinds:

- **local** — devices built in-process, no serialization
- **subprocess** — devices built in a child process rigup spawns
- **remote** — devices built in a process on another machine

The same handle calls work across all three; only the `Adapter` beneath differs.

## Defining a device

A device is a subclass of `Device` whose exposed members are marked with decorators. Read-only telemetry uses `@property` + `@describe`; a constrained read/write value uses a descriptor (`@numeric`, `@numeric_int`, `@enumerated`, `@enumerated_int`); a command is any `@describe`'d method.

```python
from enum import StrEnum
from rigup.device import Device, describe, numeric

class LaserState(StrEnum):
    OFF = "off"
    ON = "on"

class MyLaser(Device[LaserState]):
    __DEVICE_TYPE__ = "laser"

    def __init__(self, uid: str):
        super().__init__(uid)
        self._power = 0.0

    @numeric(minimum=0.0, maximum=100.0, step=0.1)
    @describe(label="Power", units="mW", stream=True)
    def power(self) -> float:
        return self._power

    @power.setter
    def power(self, value: float) -> None:
        self._power = value  # clamped and step-snapped before it reaches here

    @describe(label="Enable")
    def enable(self) -> None:
        ...
```

`@describe` is what makes a member visible over the wire — undecorated methods and properties stay private. `stream=True` publishes the value on a timer so subscribers get live updates. The bounds on `@numeric` are serialized alongside the value, so a UI can render the right control without hard-coding limits.

## Configuring a rig

A rig is declared in YAML. Top-level `devices:` run in-process; `nodes:` run in a subprocess or on a remote host. Each device gives a `target` class, `init` constructor arguments, and optional `defaults` applied after construction.

```yaml
devices:
  laser:
    target: mypackage.MyLaser
    init: { uid: "laser" }
    defaults: { power: 5.0 }

nodes:
  stage_node:
    kind: subprocess          # inferred from `address` if omitted
    devices:
      stage:
        target: mypackage.MyStage
        init: { uid: "stage", port: "/dev/ttyUSB0" }

  remote_scope:
    kind: remote
    address: "tcp://192.168.1.100:5555"
    devices:
      daq:
        target: mypackage.MyDaq
        init: { uid: "daq" }
```

## Local vs. distributed

Configuration is the only thing that changes between running every device in one process and spreading devices across machines — the code that drives the rig is identical:

```python
from rigup import Rig, RigConfig

rig = Rig(RigConfig.model_validate(config))
await rig.open()

laser = rig.devices["laser"]
await laser.call("enable")
props = await laser.props.get("power")

await rig.close()
```

For subprocess and remote nodes, rigup communicates over ZeroMQ through a transport abstraction (`transport/`) — RPC on a request/reply channel and property streams on a publish/subscribe channel. A node accepts one orchestrator at a time (a `CLAIM`/`RELEASE` handshake), so two rigs cannot contend for the same hardware. None of this is visible from the handle API.

## Layout

| Path | Responsibility |
|------|----------------|
| [`device/`](src/rigup/device/) | `Device`, `DeviceController`, `DeviceHandle`, property descriptors, command/property schemas |
| [`node/`](src/rigup/node/) | `LocalNode`, `SubprocessNode`, `RemoteNode`, and the daemon that hosts devices in a node process |
| [`transport/`](src/rigup/transport/) | Wire-agnostic RPC + pub/sub contracts, with a ZeroMQ implementation |
| [`rig.py`](src/rigup/rig.py) | `Rig` — builds nodes from config and aggregates their devices |
| [`config.py`](src/rigup/config.py) | `RigConfig` / `NodeConfig` schemas |
| [`build.py`](src/rigup/build.py) | Configuration-driven instantiation with error accumulation |

## Tests

Tests live in [`tests/`](tests/) and run under pytest (`asyncio_mode = "auto"`). They cover the rig lifecycle, each node kind, the transport layer, the protocol, and the property descriptors. Networked tests are marked `slow`:

```bash
uv run pytest rigup/tests
uv run pytest rigup/tests -m "not slow"
```
