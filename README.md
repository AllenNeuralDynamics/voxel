<h1>
    <div>
        <img src="voxel-logo.png" alt="Voxel Logo" width="50" height="50">
    </div>
    Voxel
</h1>

- [Overview](#overview)
  - [Instrument](#instrument)
  - [Acquisition](#acquisition)
  - [Utilities](#utilities)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Documentation](#documentation)
  - [Usage](#usage)
- [Appendix](#appendix)
  - [Devices](#devices)
  - [Writers](#writers)
  - [File Transfers](#file-transfers)
  - [Processes](#processes)
- [Support and Contribution](#support-and-contribution)
- [License](#license)

## Overview

Voxel is a Python package that provides core components and functionality for controlling Light Sheet Microscopy
systems. It is designed to simplify the process of developing software for novel microscope setups by focusing on
modular composable components. Voxel is built on the following principles:

1. **Modular**: Each component (device, writer, processor) implements a common interface and can be easily swapped out.
2. **Configurable**: Microscope setups are defined in a human readable YAML configuration file, allowing for easy setup and modification.
3. **Extensible**: New devices and components can be easily added by implementing the appropriate interface.
4. **Pythonic**: Written in Python and designed to be easily understood and modified.

Voxel provides two key Classes: `Instrument` and `Acquisition`.

### Instrument

The `Instrument` class focuses on the composition and structure of the microscope setup. At its core, an instrument is a collection of devices that implement the `VoxelDevice` interface. An `instrument.yaml` file defines the devices and their respective settings. Devices are defined by providing their python package, module, and class name as well as any initialization arguments and settings.

Checkout an example [instrument configuration yaml](#2-instrument-yaml-configuration) and the [Devices](#devices) section for a list of supported devices and their respective drivers.

### Acquisition

The `Acquisition` class focuses on the execution of an imaging experiment. It is responsible for coordinating the devices in the instrument to capture and process data. The `Acquisition` class is primarily set up as an abstract class that can be subclassed to implement specific acquisition protocols. It provides several methods that are useful in the implementation of an acquisition protocol. A run method is defined that should be overridden by the subclass in order to define a specific protocol for a given microscope design.
For an example of an acquisition protocol, check out the [ExaSpim Acquisiton Class](https://github.com/AllenNeuralDynamics/exaspim-control/blob/main/exaspim_control/exa_spim_acquisition.py)

### Utilities

Voxel also provides additional utilities useful for performing imaging experiments. This includes classes for writing data, performing online processing of imaging data, and concurrent transferring of data to external
storage.

Checkout the [Writers](#writers) and [File Transfers](#file-transfers) for a list of supported writers and file transfer methods and the [Processes](#processes) section for a list of supported processors.

## Getting Started

### Prerequisites

- **Python>=3.9** (tested) (Recommended to install via [Anaconda](https://www.anaconda.com/products/individual) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html))
- For control of some specific devices, you will need the appropriate SDK installed:
  - [Cameras](./voxel/devices/camera/README.md):
    - eGrabber (Windows and Linux)
    - DCAM (Windows only)
  - [Lasers]:
    - [Coherent HOPS](https://github.com/AllenNeuralDynamics/coherent_lasers) (Windows only)

### Installation

1. Create a virtual environment and activate it:
    On Windows:

    ```bash
    conda create -n voxel
    conda activate voxel
    ```

2. Clone the repository:

    ```bash
    git clone https://github.com/AllenNeuralDynamics/voxel.git && cd voxel
    ```

3. To use the software, in the root directory, run:

    ```bash
    pip install -e .
    ```

4. To develop the code, run:

    ```bash
    pip install -e .[dev]
    ```

5. To install specific device drivers that have SDK requirements, run:

    ```bash
    pip install -e .[egrabber, imaris]
    ```

Check out the [list of supported devices](#devices) for more information on device drivers.

### Documentation

- _(coming soon)_

### Usage

#### 1. Single device

Individual device can be instantiated by importing the appropriate driver
class with the expected arguments. For example a camera object for a Vieworks
VP-151MX can be invoked as:

```python
from voxel.devices.camera.vieworks_egrabber import VieworksCamera

camera = VieworksCamera(id='123456')
```

Camera properties can then be queried and set by accessing attributes of the
camera object:

```python
camera.exposure_time ms = 10.0
camera.pixel_type = 'mono16'
camera.bit_packing_mode = 'lsb'
camera.binning = 1
camera.width_px = 14192
camera.height_px = 10640
camera.trigger = {'mode': 'on', 'source': 'line0', 'polarity': 'risingedge'}
```

The camera can then be operated with:

```python
camera.prepare() # this function arms and creates the camera buffer
camera.start()
image = camera.grab_frame()
camera.stop()
camera.close()
```

#### 2. Instrument YAML configuration

```yaml
instrument:
    devices:
        vp-151mx camera:
        type: camera
        driver: voxel.devices.camera.simulated
        module: SimulatedCamera
        init:
            id: 123456
        settings:
            exposure_time_ms: 10.0
            pixel_type: mono16
            height_offest_px: 0
            height_px: 2048
            width_offset_px: 0
            width_px: 2048
            trigger:
            mode: off
            polarity: rising
            source: external
        488 nm laser:
        type: laser
        driver: voxel.devices.lasers.simulated
        module: SimulatedLaser
        init:
            id: COM1
        x axis stage:
        type: scanning_stage
        driver: voxel.devices.stage.simulated
        module: Stage
        init:
            hardware_axis: x
            instrument_axis: z
        settings:
            speed_mm_s: 1.0
```

An instrument can be invoked by loading the YAML file with and the loaded devices
can be accessed with. The above example uses all simulated device classes.

```python
from voxel.instruments.instrument import Instrument

instrument = Instrument(config_path='example.yaml')
instrument.cameras['vp-151mx camera']
instrument.lasers['488 nm laser']
instrument.scanning_stages['x axis stage']
```

#### 3. Experimental workflows may then be scripted by using the full instrument object and the contained device objects as needed

- _(example coming soon)_

## Appendix

### Devices

Currently supported device types and models are listed below.

#### DAQ

| Manufacturer         | Model     | Class        | Module                        | Tested |
| -------------------- | --------- | ------------ | ----------------------------- | ------ |
| National Instruments | PCIe-6738 | NIDaq        | `voxel.devices.daq.ni`        | ✅      |
| Simulated            | MockDAQ   | SimulatedDAQ | `voxel.devices.daq.simulated` | ✅      |

#### Cameras

| Manufacturer | Model            | Class           | Module                           | Tested |
| ------------ | ---------------- | --------------- | -------------------------------- | ------ |
| Simulated    | MockCamera       | SimulatedCamera | `voxel.devices.camera.simulated` | ✅      |
| Vieworks     | VP-151MX         | VieworksCamera  | `voxel.devices.camera.vieworks`  | ✅      |
| Vieworks     | VNP-604MX        |                 |                                  | ✅      |
| Hamamatsu    | ORCA-Flash4.0 V3 | HamamatsuCamera | `voxel.devices.camera.hamamatsu` | ✅      |
| Hamamatsu    | ORCA-Fusion BT   |                 |                                  | ✅      |
| PCO          |                  | PCOCamera       | `voxel.devices.camera.pco`       | ❌      |

#### Lasers

| Manufacturer | Model     | Class          | Module                                     | Tested |
| ------------ | --------- | -------------- | ------------------------------------------ | ------ |
| Simulated    | MockLaser | SimulatedLaser | `voxel.devices.laser.simulated`            | ✅      |
| Coherent     | OBISLX    | ObixLXLaser    | `voxel.devices.laser.coherent`             | ✅      |
| Coherent     | OBISLS    | ObixLSLaser    | `voxel.devices.laser.coherent`             | ✅      |
| Coherent     | GenesisMX | GenesisMXVoxel | `coherent_lasers.genesis_mx.voxel_adapter` | ✅      |
| Vortran      | Stradus   | StradusLaser   | `voxel.devices.laser.vortran`              | ❌      |
| Oxxius       | LBX       | OxxiusLBXLaser | `voxel.devices.laser.oxxius`               | ❌      |
| Oxxius       | LCX       | OxxiusLCXLaser | `voxel.devices.laser.oxxius`               | ❌      |
| Cobolt       |           | CoboltLaser    | `voxel.devices.laser.cobolt`               | ❌      |

#### Stages

| Manufacturer | Model     | Class          | Module                          | Tested |
| ------------ | --------- | -------------- | ------------------------------- | ------ |
| Simulated    | MockStage | SimulatedStage | `voxel.devices.stage.simulated` | ✅      |
| ASI          |           | ASIStage       | `voxel.devices.stage.asi`       | ✅      |

#### Rotation mounts

| Manufacturer | Model  | Class       | Module                                   | Tested |
| ------------ | ------ | ----------- | ---------------------------------------- | ------ |
| Simulated    | MockRM | SimulatedRM | `voxel.devices.rotation_mount.simulated` | ✅      |
| Thorlabs     | K10CR1 | ThorlabsRM  | `voxel.devices.rotation_mount.thorlabs`  | ✅      |

#### AOTF

| Manufacturer | Model    | Class         | Module                         | Tested |
| ------------ | -------- | ------------- | ------------------------------ | ------ |
| Simulated    | MockAOTF | SimulatedAOTF | `voxel.devices.aotf.simulated` | ✅      |
| AAOpto       |          | AAOptoAOTF    | `voxel.devices.aotf.aaopto`    | ❌      |

#### Filterwheel

| Manufacturer | Model   | Class          | Module                                | Tested |
| ------------ | ------- | -------------- | ------------------------------------- | ------ |
| Simulated    | MockFW  | SimulatedFW    | `voxel.devices.filterwheel.simulated` | ✅      |
| ASI          | FW-1000 | ASIFilterWheel | `voxel.devices.filterwheel.asi`       | ✅      |

#### Flip mount

| Manufacturer | Model  | Class       | Module                               | Tested |
| ------------ | ------ | ----------- | ------------------------------------ | ------ |
| Simulated    | MockFM | SimulatedFM | `voxel.devices.flip_mount.simulated` | ✅      |
| Thorlabs     | MFF101 | ThorlabsFM  | `voxel.devices.flip_mount.thorlabs`  | ✅      |

#### Power meter

| Manufacturer | Model  | Class       | Module                                | Tested |
| ------------ | ------ | ----------- | ------------------------------------- | ------ |
| Simulated    | MockPM | SimulatedPM | `voxel.devices.power_meter.simulated` | ✅      |
| Thorlabs     | PM100D | ThorlabsPM  | `voxel.devices.power_meter.thorlabs`  | ✅      |

#### Tunable lens

| Manufacturer | Model        | Class          | Module                                 | Tested |
| ------------ | ------------ | -------------- | -------------------------------------- | ------ |
| Simulated    | MockTL       | SimulatedTL    | `voxel.devices.tunable_lens.simulated` | ✅      |
| ASI          | TGTLC        | ASITunableLens | `voxel.devices.tunable_lens.asi`       | ✅      |
| Optotune     | ELE41, ICC4C | OptotuneTL     | `voxel.devices.tunable_lens.optotune`  | ✅ , ✅  |

### Writers

| Writer  | File Format   | Class         | Module                         | Tested |
| ------- | ------------- | ------------- | ------------------------------ | ------ |
| Imaris  | `.ims`        | ImarisWriter  | `voxel.writers.imaris_writer`  | ✅      |
| TIFF    | `.tiff`       | TIFFWriter    | `voxel.writers.tiff_writer`    | ✅      |
| BDV     | `.h5/.xml`    | BDVWriter     | `voxel.writers.bdv_writer`     | ✅      |
| ACQUIRE | `.zarr V2/V3` | ACQUIREWriter | `voxel.writers.acquire_writer` | ✅      |

### File Transfers

| Transfer Method | Class    | Module                         | Tested |
| --------------- | -------- | ------------------------------ | ------ |
| Robocopy        | Robocopy | `voxel.file_transfer.robocopy` | ✅      |
| Rsync           | Rsync    | `voxel.file_transfer.rsync`    | ✅      |

### Processes

```yaml
CPU processes:
    - Downsample 2D
    - Downsample 3D
    - Maximum projections (xy, xz, yz)
GPU processes:
    - Downsample 2D
    - Downsample 3D
    - Rank-ordered downsample 3D
```

## Support and Contribution

If you encounter any problems or would like to contribute to the project,
please submit an [Issue](https://github.com/AllenNeuralDynamics/voxel/issues)
on GitHub.

## License

Voxel is licensed under the MIT License. For more details, see
the [LICENSE](LICENSE) file.
