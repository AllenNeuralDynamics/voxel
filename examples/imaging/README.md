# Imaging Rig Example

Example implementation for imaging/microscopy systems with cameras and lasers.

## Components

- `ImagingRig` - Rig with typed `lasers` and `cameras` collections
- `ImagingNodeService` - Creates `CameraService` for camera devices
- Device drivers in `drivers/`

## Usage

**Local demo:**
```bash
cd examples
uv run python -m imaging.demo
```

**Distributed:**
```bash
cd examples

# Controller
uv run python -m imaging.demo

# Remote nodes
uv run python -m imaging.node node_1 tcp://192.168.1.100:9000
```

## Configuration

```yaml
metadata:
  name: "MyImagingRig"
  control_port: 9000

nodes:
  primary:
    devices:
      laser_488:
        target: imaging.drivers.laser.Laser
        kwargs: { wavelength: 488 }
  
  camera_node:
    hostname: 192.168.1.50
    devices:
      camera_1:
        target: imaging.drivers.camera.Camera
        kwargs: { pixel_size_um: "0.5, 0.5" }
```
