<h1>
    <div>
        <img src="voxel-logo.png" alt="Voxel Logo" width="50" height="50">
    </div>
    Voxel
</h1>

Core library for light sheet microscopy using PyRig.

> [!Warning]
> 🚧 Under Construction: APIs, configuration schemas, device drivers, and documentation are actively evolving. 🚧

## What is Voxel?

A light sheet microscope illuminates samples with a thin sheet of light while imaging perpendicular to the illumination plane. This package provides:

- **VoxelRigConfig** - YAML-based configuration schema with validation for microscope hardware topology
- **VoxelRig** - Orchestration class that manages device lifecycle, profile switching, and coordinated preview/acquisition
- **Device abstractions** - Base classes for cameras, lasers, DAQs, stages, AOTFs, and filter wheels
- **Frame acquisition** - DAQ-synchronized waveform generation and hardware triggering

Concrete hardware drivers are in [voxel-drivers](voxel-drivers/).

The configuration models the physical structure of the microscope:

- **Detection paths** - Camera + filter wheels + aux devices
- **Illumination paths** - Laser + aux devices (e.g., AOTF)
- **Channels** - Pair a detection path with an illumination path and specify filter positions
- **Profiles** - Group channels that can be acquired simultaneously, with DAQ waveform timing
- **Stage** - XYZ linear axes (+ optional rotation axes)
- **DAQ** - Synchronizes acquisition via hardware triggers

## Configuration

```yaml
metadata:
  name: my-voxel-rig

nodes:
  main:
    devices:
      camera_1: { target: voxel_drivers.cameras.Vieworks }
      laser_488: { target: voxel_drivers.lasers.AAOpto }
      daq: { target: voxel_drivers.daqs.NI }
      # ...

daq:
  device: daq
  acq_ports: { camera_1: ao0, laser_488: ao1 }

detection:
  camera_1: { filter_wheels: [fw1] }

illumination:
  laser_488: {}

channels:
  gfp: { detection: camera_1, illumination: laser_488, filters: { fw1: GFP } }

profiles:
  default:
    channels: [gfp]
    daq: { timing: { ... }, waveforms: { ... } }
```

## Usage

For a complete application with web UI and CLI, see [voxel-studio](voxel-studio/).

```python
from voxel.config import VoxelRigConfig
from voxel.rig import VoxelRig

config = VoxelRigConfig.from_yaml("system.yaml")
rig = VoxelRig(config)
await rig.start()
await rig.set_active_profile("default")
await rig.start_preview(frame_callback)
```
