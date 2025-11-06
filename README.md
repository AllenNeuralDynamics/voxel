# PyRig

Distributed device control framework for experimental rigs.

Type-safe remote control of hardware devices across networked nodes with ZeroMQ.

## Quick Start

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

Each device service exposes:
- `REQ` - Execute command
- `GET` - Read properties
- `SET` - Write properties  
- `INT` - Introspection

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

## Examples

**Simple:** Base classes, generic access  
**Imaging:** Custom rig with typed clients (cameras, lasers)

```bash
cd examples
uv run python -m simple.demo
uv run python -m imaging.demo
```

## License

MIT
