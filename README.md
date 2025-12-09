# PyRig

Distributed device control framework for experimental rigs: Provides control of hardware devices across networked nodes with ZeroMQ.

> 🚧 **Heads up:** PyRig is under active development. Expect rapid changes and occasional breaking updates while the core APIs settle.  🚧

## Quick Start

```bash
# Install dependencies
uv sync --all-packages --all-extras

# Run basic examples
uv run python -m examples.simple.demo
uv run python -m examples.imaging.demo
```

**[SPIM-Rig:](spim-rig/README.md)** A complete microscope rig implementation using PyRig with web UI and hardware drivers.

### Example code

```python
from pyrig import Rig, RigConfig

config = RigConfig.from_yaml("system.yaml")
rig = Rig(zctx, config)
await rig.start()

# Generic access
temp = rig.agents["temp_controller"]
await temp.call("start_regulation")

# Or with typed clients (ImagingRig example)
laser = rig.lasers["laser_488"]
await laser.turn_on()  # IDE autocomplete!
```

## Architecture

Three layers:

**Device** - Hardware abstraction (talks to SDK/driver)
**Service** - Network wrapper (ZeroMQ server)
**Client** - Remote proxy (ZeroMQ client)

```python
from pyrig import Device, DeviceService, DeviceClient, describe

# Device (server-side)
class Camera(Device):
    def capture(self) -> np.ndarray:
        return self._sdk.acquire()

# Service (server-side, optional)
class CameraService(DeviceService[Camera]):
    @describe(label="Start Stream", desc="Stream frames to file")
    def start_stream(self, n_frames: int):
        for i in range(n_frames):
            self._writer.write(self.device.capture())

# Client (controller-side, optional)
class CameraClient(DeviceClient):
    async def capture(self) -> np.ndarray:
        return await self.call("capture")

    async def start_stream(self, n_frames: int):
        return await self.call("start_stream", n_frames)
```

Devices can run on separate machines. Configuration in YAML:

```yaml
metadata:
  name: MyRig
  control_port: 9000

nodes:
  primary:
    devices:
      camera_1:
        target: myrig.devices.Camera
        kwargs: { serial: "12345" }

  remote_node:
    hostname: 192.168.1.50
    devices:
      stage_x:
        target: myrig.devices.MotorStage
        kwargs: { axis: "X" }
```

## Communication

**Commands/Properties:** REQ/REP sockets
**State streaming:** PUB/SUB sockets
**Connection monitoring:** Heartbeats
**Logging:** PUB/SUB aggregation

Each device service exposes:

- `REQ` - Execute command
- `GET` - Read properties
- `SET` - Write properties
- `INT` - Introspection

## Logging

PyRig uses Python's stdlib logging with ZeroMQ log aggregation.

**Enable logging:**

```python
import logging
logging.basicConfig(level=logging.INFO)  # See all pyrig and node logs

from pyrig import Rig, RigConfig
rig = Rig(zctx, config)
await rig.start()
```

The Rig automatically receives logs from all nodes and forwards them to Python's logging system under the `node.<node_id>` logger. You'll see logs like:

```txt
2025-11-05 20:58:00 - pyrig.rig - INFO - Starting MyRig...
2025-11-05 20:58:00 - pyrig.nodes - INFO - [node.primary.INFO] Node primary started
2025-11-05 20:58:02 - pyrig.rig - INFO - MyRig ready with 4 devices
```

Users opt-in by configuring Python logging. No logs appear by default (library best practice).

## Customization

**Base Rig:** Generic device access via `rig.agents["id"]`

**Custom Rig:** Typed collections with autocomplete

```python
class ImagingRig(Rig):
    NODE_SERVICE_CLASS = ImagingNodeService  # Custom services

    def __init__(self, zctx, config):
        super().__init__(zctx, config)
        self.lasers: dict[str, LaserClient] = {}
        self.cameras: dict[str, CameraClient] = {}

    def _create_client(self, device_id, prov):
        if prov.device_type == DeviceType.LASER:
            client = LaserClient(...)
            self.lasers[device_id] = client
            return client
        # ...
```

## Property Helpers

Many hardware knobs expose constrained values (bounded ranges, enumerated modes). PyRig ships specialized property descriptors under `pyrig.props` so those constraints stay declarative and travel with the data:

- `@deliminated_float` / `@deliminated_int`: clamp values to `min/max/step` and report those bounds to clients.
- `@enumerated_string` / `@enumerated_int`: restrict values to a predefined list and expose the options in RPC responses.

Descriptors return `PropertyModel` objects, so `DeviceService` and `DeviceClient` automatically serialize both the value and its metadata. UI layers can render sliders or dropdowns without guessing constraints.

```python
from pyrig.props import deliminated_float, enumerated_string

class Laser(Device):
    @deliminated_float(min_value=0.0, max_value=100.0, step=0.5)
    def power_setpoint(self) -> float:
        return self._power

    @power_setpoint.setter
    def power_setpoint(self, value: float) -> None:
        self._power = value

    @enumerated_string(options=["cw", "pulsed", "burst"])
    def mode(self) -> str:
        return self._mode
```

On the client side, call `await client.get_prop("power_setpoint")` to receive the full `PropertyModel` (value + bounds), or `await client.get_prop_value("mode")` for just the primitive.

## Examples

**Simple:** Base classes, generic access
**Imaging:** Custom rig with typed clients (cameras, lasers)

```bash
cd examples
uv run python -m simple.demo
uv run python -m imaging.demo
```

## License

[MIT](LICENSE)
