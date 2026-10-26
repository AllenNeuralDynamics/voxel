# vxl-drivers

**Connect Voxel's device interfaces to real microscope hardware.**

vxl-drivers contains the vendor-specific cameras, lasers, motion controllers, and related devices used by Voxel
instruments. The `vxl` package defines the device contracts, while [rigup](../rigup/) constructs the configured
devices and presents them through the same asynchronous handle API used for simulated hardware.

## Highlights

- **Configuration-selected hardware** — instrument configurations identify drivers by import path, without embedding
  vendor-specific construction in the instrument runtime.
- **Common device contracts** — physical cameras, lasers, power meters, and axes implement interfaces defined by `vxl`;
  specialized controllers such as AOTFs live in this package.
- **Shared-controller support** — hubs own serial buses or vendor connections and are injected into colocated device
  drivers by rigup.
- **Hardware-free application development** — core simulations live in `vxl`; legacy AOTF and laser simulations
  remain here alongside their driver interfaces.

## How the package fits

```mermaid
flowchart TD
    config["Instrument hal configuration"] --> rigup["rigup construction and handles"]
    contracts["vxl device interfaces"] --> drivers["vxl-drivers implementations"]
    rigup --> drivers
    drivers --> vendor["Vendor SDK or serial protocol"]
    vendor --> hardware["Physical hardware"]
```

Application code normally controls a configured driver through a rigup `DeviceHandle`; it does not instantiate the
driver directly. This keeps local, subprocess-hosted, and remote devices on the same control surface.

## Configure hardware

Each entry in an instrument's `hal.devices` mapping names a driver `target` and its constructor `init` arguments.
rigup supplies the device UID and resolves references to other configured devices on the same node. For example, a
Tiger hub can own one controller connection shared by several axes:

```yaml
hal:
  devices:
    tiger_controller:
      target: vxl_drivers.tigerhub.TigerHub
      init: {box: COM3}

    x_axis:
      target: vxl_drivers.axes.asi.TigerLinearAxis
      init: {hub: tiger_controller, axis_label: x, units: um}
```

A hub and the devices that depend on it must run in the same process. See the [rigup README](../rigup/) for local,
subprocess, and remote-node placement.

> [!CAUTION]
> Constructing a hardware driver may immediately open a physical device. Confirm ports, addresses, limits, and laser
> safety controls before loading a real instrument configuration.

## Included integrations

These are concrete integrations present in the package. Actual operation also depends on compatible hardware,
firmware, operating-system drivers, and vendor runtimes.

### Cameras

| Hardware | Target | Python support |
| --- | --- | --- |
| Vieworks through Euresys eGrabber | `vxl_drivers.cameras.egrabber.VieworksCamera` | `egrabber-camera` extra |
| Hamamatsu DCAM cameras | `vxl_drivers.cameras.dcam.hamamatsu.HamamatsuCamera` | Bundled Python wrapper; native DCAM runtime required |
| PCO sCMOS cameras | `vxl_drivers.cameras.pco.PCOCamera` | `pco` package installed separately |
| Ximea cameras | `vxl_drivers.cameras.ximea.XimeaCamera` | `ximea-camera` extra |

### Lasers and AOTFs

The [canonical laser contract](../src/vxl/devices/laser/README.md) separates source settings from output control.
The package cutover is complete; instrument, template, and UI integration is still in progress.

| Hardware | Target | Python support |
| --- | --- | --- |
| Coherent Genesis MX source | `vxl_drivers.lasers.genesis_mx.GenesisMXSource` | `coherent-laser` extra |
| Oxxius shared controller | `vxl_drivers.lasers.oxxius.controller.OxxiusController` | Serial support included |
| Oxxius LBX source | `vxl_drivers.lasers.oxxius.lbx.OxxiusLBXSource` | Serial support included |
| Oxxius LCX with linked AOM | `vxl_drivers.lasers.oxxius.lcx.OxxiusLCXLaser` | Serial support included |
| MPDS controller | `vxl_drivers.lasers.mpds.controller.MPDS` | Serial support included |
| Source with MPDS modulation | `vxl_drivers.lasers.mpds.laser.MPDSLaser` | Configured with a source and MPDS controller |

Wrap standalone sources with `vxl.devices.laser.source_only.SourceOnlyLaser` to expose the complete `Laser` API.
Driver module docstrings contain configuration examples and pending hardware checks. The MPDS calibration CLI is
`vxl-calibrate-mpds`; install the `mpds-calibration` extra for plotting.

Older laser implementations are retained under `vxl_drivers.lasers_legacy`. They report `laser_legacy`, remain
accessible through `hal.devices`, and cannot be assigned as canonical illumination lasers.

| Legacy hardware | Target | Python support |
| --- | --- | --- |
| Vortran Stradus | `vxl_drivers.lasers_legacy.vortran_stradus.VortranStradus` | `vortran-laser` extra |
| Cobolt Skyra | `vxl_drivers.lasers_legacy.cobolt_skyra.CoboltSkyra` | `pycobolt-laser` extra |
| Coherent Genesis MX | `vxl_drivers.lasers_legacy.coherent.genesis_mx.GenesisMX` | `coherent-laser` extra |
| Coherent OBIS LX and LS | `vxl_drivers.lasers_legacy.coherent.obis.ObisLX`, `ObisLS` | `obis-laser` extra |
| MPB VFL | `vxl_drivers.lasers_legacy.mpb.vfl.MpbVfl` | Serial support included |
| Oxxius LBX and LCX | `vxl_drivers.lasers_legacy.oxxius.OxxiusLBX`, `OxxiusLCX` | Shared `vxl_drivers.lasers_legacy.oxxius.OxxiusHub` |
| AA Opto-Electronic MPDSnC | `vxl_drivers.aotf.mpds.MpdsAotf` | Included `aaopto-aotf` dependency |

### Power meters

| Hardware | Target | Python support |
| --- | --- | --- |
| Thorlabs PM100-series (SCPI/VISA) | `vxl_drivers.power_meters.thorlabs.ThorlabsPowerMeter` | `thorlabs-power-meter` extra; VISA backend required |

See the [driver module](src/vxl_drivers/power_meters/thorlabs.py) for setup notes and a configuration example.

### Motion control

| Hardware | Target | Python support |
| --- | --- | --- |
| ASI Tiger controller | `vxl_drivers.tigerhub.TigerHub` | Serial support included |
| ASI Tiger linear axis | `vxl_drivers.axes.asi.TigerLinearAxis` | Configured with a `TigerHub` |
| Micronix MMC-100 controller | `vxl_drivers.axes.mmc.MMCHub` | Serial support included |
| Micronix MMC-100 linear axis | `vxl_drivers.axes.mmc.MMCLinearAxis` | Configured with an `MMCHub` |
| Thorlabs MFF101 flip mount | `vxl_drivers.axes.thorlabs.MFF101` | `thorlabs` extra |

## Install vendor support

Install only the optional dependency needed by the hardware being configured. From the Voxel workspace, for example:

```bash
uv sync --package vxl-drivers --extra egrabber-camera
```

Available extras are listed in [`pyproject.toml`](pyproject.toml). A Python extra may provide bindings without
installing the vendor's native runtime, device driver, firmware, or license; follow the corresponding vendor's
installation requirements as well.

## Develop and validate drivers

A driver implements the appropriate `vxl` device interface and exposes its public commands and properties through
rigup. It should keep vendor-specific types behind that boundary, serialize access to shared controller resources,
and release hardware deterministically from `close()`.

Run the hardware-independent checks from the workspace root:

```bash
uv sync --all-packages --all-groups
uv run ruff check drivers
uv run basedpyright drivers
uv run pytest drivers/tests
```

These checks cannot establish compatibility with a physical device or vendor runtime. Hardware validation should
name the exact model, firmware, connection, and exercised operations.


Low-level ASI Tiger command behavior is documented separately in the
[`tigerhub/ops` reference](src/vxl_drivers/tigerhub/ops/README.md).

vxl-drivers is part of the [Voxel](../) project and is available under its [MIT license](../LICENSE).
