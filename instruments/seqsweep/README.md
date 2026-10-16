# SeqSweep

**TDI strip-scan acquisition for the BARSeq microscope, built on Voxel's libraries.**

SeqSweep is the imaging instrument of [BARseq](https://github.com/AllenInstitute/BARseq). The BARseq
orchestrator coordinates sequencing cycles across fluidics (SeqFlow, on
[Mixology](https://github.com/AllenNeuralDynamics/brainwasher)) and imaging (SeqSweep), and talks to SeqSweep
over one_liner: run `uv run seqsweep` to serve it.

This package uses Voxel as a set of building blocks rather than as an application:

| Voxel library | Used for |
| --- | --- |
| [`rigup`](../../rigup/) | Device RPC: WS1 devices run in-process, each acquisition workstation runs a node |
| `vxl.devices` | `Camera` + `CameraController` (OME-Zarr writer, preview, storage checks), axis and laser contracts |
| [`ome_zarr_writer`](../../omezarr/) | Streaming each camera's Z-stack of strips to OME-Zarr on its own workstation |
| [`vxl_records`](../../records/) | Acquisition manifests (one volume per strip) and captured logs in SQLite |

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
