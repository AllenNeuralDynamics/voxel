# Voxel Drivers

`voxel-drivers` hosts hardware adapters for the Voxel rig: NI DAQ timing, AA Opto AOTFs, ASI stages, Vieworks cameras (via EGrabber), and drop-in simulated devices for local development. Each driver implements the abstract interfaces defined in `voxel` so you can bind real instruments in your `system.yaml`.

## Using the Drivers

- Install alongside the rest of the workspace (`uv sync …` already links the package in editable mode).
- Reference the driver classes from your rig configuration (e.g. `target: voxel_drivers.daqs.ni.NIDaqTask`).
- Mix and match simulated and hardware-backed drivers to mirror whatever subset of gear you have connected.

The Voxel example (`examples/voxel`) defaults to the simulated drivers so you can explore the UI without any hardware. Swap in the concrete drivers listed above when you're ready to run on an actual microscope.

## Driver Catalog

**Legend:** Status column shows Implementation + Hardware test (✅ ready, ⚠️ pending).

| Device Type | Target | Status | Notes |
| --- | --- | --- | --- |
| **AOTF** | [`voxel_drivers.aotf.simulated.SimulatedAotf`](src/voxel_drivers/aotf/simulated.py) | ✅ ✅ | Used by `examples/voxel` for end-to-end smoke tests. |
| **AOTF** | [`voxel_drivers.aotf.mpds.MpdsAotf`](src/voxel_drivers/aotf/mpds.py) | ✅ ⚠️ | Hardware hookup required for full validation; API settled. |
| **Laser** | [`voxel_drivers.lasers.simulated.SimulatedLaser`](src/voxel_drivers/lasers/simulated.py) | ✅ ✅ | Standalone DPSS: adjustable power + telemetry without AOTF dependency. |
| **Laser** | [`voxel_drivers.lasers.simulated.SimulatedAOTFShutteredLaser`](src/voxel_drivers/lasers/simulated.py) | ✅ ✅ | Uses AOTF for fast blanking while laser holds power. |
| **Laser** | [`voxel_drivers.lasers.simulated.SimulatedAOTFModulatedLaser`](src/voxel_drivers/lasers/simulated.py) | ✅ ✅ | Passive source—AOTF sets both blanking and RF drive power. |
| **Camera** | [`voxel_drivers.cameras.simulated.SimulatedCamera`](src/voxel_drivers/cameras/simulated) | ✅ ✅ | Procedural frames + ROI/binning validation in the Voxel demo. |
| **Camera** | [`voxel_drivers.cameras.egrabber.vieworks.VieworksCamera`](src/voxel_drivers/cameras/egrabber) | ✅ ⚠️ | Requires Vieworks hardware + EGrabber runtime to exercise. |
| **DAQ** | [`voxel_drivers.daqs.simulated.SimulatedDaq`](src/voxel_drivers/daqs/simulated.py) | ✅ ✅ | Drives the simulated timing stack in `examples/voxel`. |
| **DAQ** | [`voxel_drivers.daqs.ni.NiDaq`](src/voxel_drivers/daqs/ni.py) | ✅ ⚠️ | NI PCIe-6738: awaiting lab timing tests; structure mirrors deployed rigs. |
| **Continuous Axis** | [`voxel_drivers.axes.simulated.SimulatedContinuousAxis`](src/voxel_drivers/axes/simulated.py) | ✅ ✅ | Includes optional simulated TTL stepper for stage scanning. |
| **Continuous Axis** | [`voxel_drivers.axes.asi.TigerLinearAxis`](src/voxel_drivers/axes/asi.py) | ✅ ⚠️ | ASI Tiger: integrates with Tiger hub ops; needs on-hardware sweep. |
| **Discrete Axis** | [`voxel_drivers.axes.simulated.SimulatedDiscreteAxis`](src/voxel_drivers/axes/simulated.py) | ✅ ✅ | Ideal for filter wheels, turrets, and other indexed devices. |
| **Support** | [Tiger hub shared protocol](src/voxel_drivers/tigerhub) | ✅ ⚠️ | Dependency for ASI drivers; protocol helpers still evolving. |
