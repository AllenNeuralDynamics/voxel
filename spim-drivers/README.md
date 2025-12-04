# SPIM Drivers

`spim-drivers` hosts hardware adapters for the SPIM rig: NI DAQ timing, AA Opto AOTFs, ASI stages, Vieworks cameras (via EGrabber), and drop-in simulated devices for local development. Each driver implements the abstract interfaces defined in `spim_rig` so you can bind real instruments in your `system.yaml`.

## Using the Drivers

- Install alongside the rest of the workspace (`uv sync …` already links the package in editable mode).
- Reference the driver classes from your rig configuration (e.g. `target: spim_drivers.daqs.ni.NIDaqTask`).
- Mix and match simulated and hardware-backed drivers to mirror whatever subset of gear you have connected.

The SPIM example (`examples/spim`) defaults to the simulated drivers so you can explore the UI without any hardware. Swap in the concrete drivers listed above when you're ready to run on an actual microscope.

## Driver Catalog

**Legend:** Status column shows Implementation + Hardware test (✅ ready, ⚠️ pending).

### AOTFs

| Driver | Target | Status | Notes |
| --- | --- | --- | --- |
| [Simulated AOTF](src/spim_drivers/aotf/simulated.py) | `spim_drivers.aotf.simulated.SimulatedAotf` | ✅ ✅ | Used by `examples/spim` for end-to-end smoke tests. |
| [AA Opto MPDS](src/spim_drivers/aotf/mpds.py) | `spim_drivers.aotf.mpds.MpdsAotf` | ✅ ⚠️ | Hardware hookup required for full validation; API settled. |

### Lasers

| Driver | Target | Status | Notes |
| --- | --- | --- | --- |
| [Simulated Laser (standalone DPSS)](src/spim_drivers/lasers/simulated.py) | `spim_drivers.lasers.simulated.SimulatedLaser` | ✅ ✅ | Adjustable power + telemetry without AOTF dependency. |
| [Simulated AOTF-shuttered Laser](src/spim_drivers/lasers/simulated.py) | `spim_drivers.lasers.simulated.SimulatedAOTFShutteredLaser` | ✅ ✅ | Uses AOTF for fast blanking while laser holds power. |
| [Simulated AOTF-modulated Laser](src/spim_drivers/lasers/simulated.py) | `spim_drivers.lasers.simulated.SimulatedAOTFModulatedLaser` | ✅ ✅ | Passive source—AOTF sets both blanking and RF drive power. |

### Cameras

| Driver | Target | Status | Notes |
| --- | --- | --- | --- |
| [Simulated camera](src/spim_drivers/cameras/simulated) | `spim_drivers.cameras.simulated.SimulatedCamera` | ✅ ✅ | Procedural frames + ROI/binning validation in the SPIM demo. |
| [Vieworks via EGrabber](src/spim_drivers/cameras/egrabber) | `spim_drivers.cameras.egrabber.vieworks.VieworksCamera` | ✅ ⚠️ | Requires Vieworks hardware + EGrabber runtime to exercise. |

### DAQ / Timing

| Driver | Target | Status | Notes |
| --- | --- | --- | --- |
| [Simulated DAQ](src/spim_drivers/daqs/simulated.py) | `spim_drivers.daqs.simulated.SimulatedDaq` | ✅ ✅ | Drives the simulated timing stack in `examples/spim`. |
| [NI PCIe-6738](src/spim_drivers/daqs/ni.py) | `spim_drivers.daqs.ni.NiDaq` | ✅ ⚠️ | Awaiting lab timing tests; structure mirrors deployed rigs. |

### Axes & Motion

| Driver | Target | Status | Notes |
| --- | --- | --- | --- |
| [Simulated Linear Axis](src/spim_drivers/axes/simulated.py) | `spim_drivers.axes.simulated.SimulatedLinearAxis` | ✅ ✅ | Includes optional simulated TTL stepper for stage scanning. |
| [Simulated Discrete Axis](src/spim_drivers/axes/simulated.py) | `spim_drivers.axes.simulated.SimulatedDiscreteAxis` | ✅ ✅ | Ideal for filter wheels, turrets, and other indexed devices. |
| [ASI Tiger linear axes](src/spim_drivers/axes/asi.py) | `spim_drivers.axes.asi.TigerLinearAxis` | ✅ ⚠️ | Integrates with Tiger hub ops; needs on-hardware sweep. |

### Support Modules

| Module | Target | Status | Notes |
| --- | --- | --- | --- |
| [Tiger hub shared protocol](src/spim_drivers/tigerhub) | n/a | ✅ ⚠️ | Dependency for ASI drivers; protocol helpers still evolving. |
