<h1>
    <div>
        <img src="voxel-logo.png" alt="Voxel Logo" width="50" height="50">
    </div>
    Voxel
</h1>

Light sheet microscopy platform built on [rigup](rigup/).

> [!Warning]
> Under active development. APIs, configuration schemas, and documentation are evolving.

## Getting Started

Requires [uv](https://docs.astral.sh/uv/) and [bun](https://bun.sh/) (for the web frontend).

```bash
uv sync --all-packages --all-extras
```

### Web UI (FastAPI + SvelteKit)

```bash
cd web/ui && bun install && bun run build && cd ../..
uv run vxl
```

Open http://localhost:8000. For frontend development with hot reload:

```bash
cd web/ui && bun run dev      # Vite dev server
bun check                     # Type checking
```

### Desktop UI (PySide6)

```bash
uv run vxl-qt                 # Optionally: uv run vxl-qt config.yaml
```

## vxl

The core package that models a light sheet microscope as a coordinated **rig** of devices.

- **Rig** — manages cameras, lasers, DAQs, stages, AOTFs, and filter wheels. Can run locally or distributed across networked nodes. Defined entirely in YAML.
- **Optical layout** — detection and illumination paths describe the physical light paths. Channels pair a detection path with an illumination path and set filter positions.
- **Profiles** — group channels with DAQ waveform timing for synchronized multi-channel acquisition.
- **Sessions** — manage an experiment end-to-end: tile grid planning, per-stack Z ranges, and acquisition execution. Persisted to disk as `.voxel.yaml` so they survive restarts.
- **Device handles** — typed async APIs for each device class (camera, laser, stage, etc.). Work identically whether the device is local or remote.

Example configs are in [`src/vxl/_configs/`](src/vxl/_configs/) — start with `simulated.local.rig.yaml` to explore without hardware.

## Packages

| Package | Description |
|---------|-------------|
| [vxl](src/vxl/) | Microscope orchestration, acquisition, and configuration |
| [vxl-drivers](drivers/) | Hardware drivers (NI DAQ, ASI stages, Vieworks/Hamamatsu/Ximea cameras, AA Opto AOTFs) |
| [vxl-web](web/) | Web interface (FastAPI + SvelteKit) |
| [vxl-qt](qt/) | Desktop interface (PySide6) |
| [rigup](rigup/) | Distributed device control framework |
| [vxlib](vxlib/) | Shared types and utilities |
| [omezarr](omezarr/) | OME-Zarr streaming writer with multi-scale pyramids |

## License

[MIT](LICENSE) - Allen Institute for Neural Dynamics
