# vxl-drivers

Hardware drivers for Voxel microscopes. Each driver implements a device interface defined in the `vxl` package — `Camera`, `Laser`, `AOTF`, or `ContinuousAxis` — so concrete instruments plug into a rig the same way their simulated counterparts do. This package contains real-hardware drivers only; simulated devices live in the `vxl` package.

## Using the drivers

Drivers are referenced from an instrument template by their fully qualified class name. Each device in the template's `hal:` section names a `target` class and its constructor `init` arguments:

```yaml
hal:
  devices:
    camera_1:
      target: vxl_drivers.cameras.dcam.hamamatsu.HamamatsuCamera
      init: { serial: "S/N-001" }
    stage_x:
      target: vxl_drivers.axes.asi.TigerLinearAxis
      init: { hub: tiger_hub, axis_label: "X" }
```

Many drivers depend on a vendor SDK or runtime (EGrabber, DCAM, serial libraries) and require the corresponding hardware to run. To explore Voxel without any hardware, start from the `simulated-local` template, which wires up the simulated devices from the `vxl` package; swap in the drivers below when moving to a real microscope.

## Driver catalog

Grouped by the `vxl` interface each driver implements.

### Cameras (`vxl.camera.base.Camera`)

| Vendor / model | Target |
|----------------|--------|
| Vieworks (via EGrabber) | `vxl_drivers.cameras.egrabber.VieworksCamera` |
| Hamamatsu (via DCAM) | `vxl_drivers.cameras.dcam.hamamatsu.HamamatsuCamera` |
| PCO | `vxl_drivers.cameras.pco.PCOCamera` |
| Ximea | `vxl_drivers.cameras.ximea.XimeaCamera` |

### Lasers (`vxl.laser.base.Laser`)

| Vendor / model | Target |
|----------------|--------|
| Vortran Stradus | `vxl_drivers.lasers.vortran_stradus.VortranStradus` |
| Cobolt Skyra | `vxl_drivers.lasers.cobolt_skyra.CoboltSkyra` |
| Coherent Genesis MX | `vxl_drivers.lasers.coherent.genesis_mx.GenesisMX` |
| Coherent OBIS (LX / LS) | `vxl_drivers.lasers.coherent.obis.ObisLX`, `ObisLS` |
| MPB VFL | `vxl_drivers.lasers.mpb.vfl.MpbVfl` |
| Oxxius (LBX / LCX) | `vxl_drivers.lasers.oxxius.OxxiusLBX`, `OxxiusLCX` |

Oxxius lasers on a shared controller connect through `vxl_drivers.lasers.oxxius.OxxiusHub`.

### AOTF (`vxl.aotf.base.AOTF`)

| Vendor / model | Target |
|----------------|--------|
| AA OptoElectronics MPDSnC | `vxl_drivers.aotf.mpds.MpdsAotf` |

### Stage axes (`vxl.axes.continuous.base.ContinuousAxis`)

| Vendor / model | Target |
|----------------|--------|
| ASI Tiger linear axis | `vxl_drivers.axes.asi.TigerLinearAxis` |
| ASI Tiger TTL stepper | `vxl_drivers.axes.asi.TigerTTLStepper` |
| ASI Tiger XYZ stage | `vxl_drivers.axes.stage.TigerXYZStage` |

The ASI drivers share a serial-protocol layer in [`tigerhub/`](src/vxl_drivers/tigerhub) (`TigerHub`, `TigerBox`), which speaks the Tiger/MS2000 command set to an ASI controller. See [`tigerhub/ops/`](src/vxl_drivers/tigerhub/ops) for the operation, parser, and model reference.
