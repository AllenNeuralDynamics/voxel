<h1>
    <div>
        <img src="voxel-logo.png" alt="Voxel Logo" width="50" height="50">
    </div>
    Voxel
</h1>

Light sheet microscopy platform built on [PyRig](pyrig/).

> [!Warning]
> Under active development. APIs, configuration schemas, and documentation are evolving.

## Packages

| Package | Description |
|---------|-------------|
| [vxl](src/vxl/) | Microscope orchestration, acquisition, and configuration |
| [vxl-drivers](drivers/) | Hardware drivers (NI DAQ, ASI stages, Vieworks/Hamamatsu/Ximea cameras, AA Opto AOTFs) |
| [vxl-web](web/) | Web interface (FastAPI + SvelteKit) |
| [vxl-qt](qt/) | Desktop interface (PySide6) |
| [pyrig](pyrig/) | Distributed device control framework |
| [vxlib](vxlib/) | Shared types and utilities |

## Quick Start

```bash
uv sync --all-packages --all-extras
uv run vxl          # Web interface
uv run vxl-qt       # Desktop interface
```

## License

[MIT](LICENSE) - Allen Institute for Neural Dynamics
