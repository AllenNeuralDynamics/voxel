# SPIM Rig

Core library for selective plane illumination microscopy (SPIM) using PyRig.

## What is a SPIM Rig?

A SPIM microscope illuminates samples with a thin sheet of light while imaging perpendicular to the illumination plane. This package provides:

- **SpimRigConfig** - YAML-based configuration schema with validation for SPIM hardware topology
- **SpimRig** - Orchestration class that manages device lifecycle, profile switching, and coordinated preview/acquisition
- **Device abstractions** - Base classes for cameras, lasers, DAQs, stages, AOTFs, and filter wheels
- **Frame acquisition** - DAQ-synchronized waveform generation and hardware triggering

Concrete hardware drivers are in [spim-drivers](../spim-drivers/).

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
  name: my-spim

nodes:
  main:
    devices:
      camera_1: { target: spim_drivers.cameras.Vieworks }
      laser_488: { target: spim_drivers.lasers.AAOpto }
      daq: { target: spim_drivers.daqs.NI }
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

For a complete application with web UI and CLI, see [spim-studio](../spim-studio/).

```python
from spim_rig.config import SpimRigConfig
from spim_rig.rig import SpimRig

config = SpimRigConfig.from_yaml("system.yaml")
rig = SpimRig(config)
await rig.start()
await rig.set_active_profile("default")
await rig.start_preview(frame_callback)
```
