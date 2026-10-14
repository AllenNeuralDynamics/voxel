# barseq

**TDI strip-scan acquisition for the BARSeq microscope, built on Voxel's libraries.**

This package uses Voxel as a set of building blocks rather than as an application:

| Voxel library | Used for |
| --- | --- |
| [`rigup`](../rigup/) | Device RPC: WS1 devices run in-process, each acquisition workstation runs a node |
| `vxl.devices` | `Camera` + `CameraController` (OME-Zarr writer, preview, storage checks), axis and laser contracts |
| [`ome_zarr_writer`](../omezarr/) | Streaming each camera's Z-stack of strips to OME-Zarr on its own workstation |
| [`vxl_records`](../records/) | Acquisition manifests (one volume per strip) and captured logs in SQLite |

Voxel's `Instrument`/`Station` layer is not used. Its acquisition model (NI-DAQ waveforms as the timing
master, frame-by-frame Z-stacks) doesn't match an ACS-mastered continuous TDI scan.

## Model

- **Stage axes:** `x` is the scan axis, moving continuously during a pass; `y` is the step axis, moved
  between strips.
- **Pass:** one constant-velocity sweep of a strip. The scan controller (the ACS stage buffer program)
  drives every gate in hardware:
  - Frame Gate → frame grabbers
  - Line Trigger → cameras
  - Power Gate → lasers
  - Z-Ramp Gate → Z controller
- **Camera frame:** one **full strip**. Each camera writes `(planes, strip_lines, width)` OME-Zarr per
  strip, at `<storage>/<slide>/strip_NNN/<channel>.ome.zarr`.
- **Bidirectional scan:** passes alternate direction across the run. Cameras mirror reverse passes while
  copying grabber blocks (`place_block`), so every stored plane is in specimen order.
- **Focus:** `FocusSurface` is fitted from the pre-coarse scan. Each strip arms a `ZRamp` along its center
  line; each Z plane replays it shifted by the plane offset.

```
for strip:                                   # one manifest volume
    move y, configure pass, set strip_lines, open stacks on all cameras, lasers on
    for plane:
        load Z ramp(offset), set direction → arm cameras → run pass → wait pass + frames
    lasers off, abort pass, drain writers, record outcome
```

## Code map

| Module | Contents |
| --- | --- |
| `devices/scan.py` | `ScanController` (timing master contract), `ScanConfig`, `ScanControllerHandle` |
| `devices/tdi.py` | `TdiCamera` (strip-as-frame camera base), `place_block` |
| `devices/zramp.py` | `ZRampAxis` (focus-following Z), `ZRamp`, `ZPoint` |
| `devices/simulated.py` | Simulated scan controller, Z ramp axis, and TDI camera (specimen-locked pattern) |
| `plan.py` | `AcquisitionPlan` → `plan_strips()`; `FocusSurface.fit()` |
| `config.py` | `BarseqConfig`: rig plus device roles, lasers, magnification, scan velocity, writer settings |
| `hardware.py` | `open_hardware()`: opens the rig and checks every role's device type |
| `acquire.py` | `BarseqAcquisition.run()`: the strip loop, cleanup, and records |
| `cli.py` | `barseq plan` and `barseq run` |

## Try it (no hardware)

```bash
uv sync --all-packages
uv run barseq plan barseq/configs/plan.example.yaml --strip-width-um 256
uv run barseq run barseq/configs/simulated.barseq.yaml barseq/configs/plan.example.yaml --storage demo/run1
uv run barseq run barseq/configs/simulated-distributed.barseq.yaml barseq/configs/plan.example.yaml --storage demo/run2
```

Data lands under each camera node's `VOXEL_STORE` (default `~/.voxel/store`). Records go to
`~/.voxel/barseq.sqlite3`.

## Moving to hardware

Real drivers subclass the same contracts and replace the simulated targets in the config:

| Role | Base class | Hardware / SDK |
| --- | --- | --- |
| scan controller | `ScanController` | ACS SPiiPlus (buffer program, PEG line trigger, gate outputs) |
| step axis | `vxl.devices.axes.ContinuousAxis` | ACS axis |
| z axis | `ZRampAxis` | PI C-414 via pipython (wave generator armed by the Z-Ramp Gate) |
| cameras | `TdiCamera` | Basler TDI + frame grabber (follow `vxl_drivers/cameras/egrabber.py`) |
| lasers | existing `vxl_drivers.lasers.mpb.MpbVfl` | pass `wavelength` explicitly |
| EDOF flip mounts | existing `vxl_drivers.axes.thorlabs.MFF101` | |

Requirements for a real `TdiCamera` driver:

- **`_grab_strip` must time out:** if a pass is aborted, cleanup must not hang waiting for lines that never
  arrive.
- **Writer RAM** is `slots × batch_z × strip bytes` per camera. Size `VOXEL_MAX_RAM_FRACTION` on each
  acquisition workstation accordingly.

With only a few Z planes, keep `writer.max_level` at 0. The writer's isotropic 2×2×2 pyramid would merge Z
planes, and its 64-voxel Z chunks are larger than a short stack. XY-only pyramids need a small change to
`ome_zarr_writer`.
