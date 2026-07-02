<h1>
    <div>
        <img src="voxel-logo.png" alt="Voxel Logo" width="50" height="50">
    </div>
    Voxel
</h1>

A light sheet microscopy platform for hardware control, acquisition orchestration, and data streaming. Voxel models a microscope as an **instrument** — its opened hardware plus a persisted acquisition state — and drives it from either a web interface or a desktop application. Device control is built on [rigup](rigup/), a distributed framework that runs devices in-process or across networked nodes with a single API.

> [!Warning]
> Under active development. APIs, configuration schemas, and documentation are evolving.

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and [bun](https://bun.sh/) (for the web frontend).

```bash
uv sync --all-packages --all-extras --all-groups
```

### Web interface (FastAPI + SvelteKit)

The frontend is built once, then served by the backend:

```bash
cd web/ui && bun install && bun run build && cd ../..
uv run vxl
```

Open http://localhost:8000 and launch the `simulated-local` template to explore the full interface with no hardware attached.

### Desktop interface (PySide6)

```bash
uv run vxl-qt                 # optionally: uv run vxl-qt config.yaml
```

## Development

After the initial `uv sync`, install the git hooks:

```bash
uvx pre-commit install          # wires pre-commit and pre-push hooks
uvx pre-commit run --all-files  # optional: one-time pass over the tree
```

`pre-commit` runs ruff (format + lint) and `uv-lock` sync. `pre-push` adds basedpyright and `pytest -m "not slow"`. Slow-flagged tests (ZMQ networking, zarr I/O) run only in CI.

Manual commands:

```bash
uv run ruff check
uv run ruff format
uv run basedpyright
uv run pytest                # full suite
uv run pytest -m "not slow"  # pre-push subset
```

For frontend work with hot reload:

```bash
cd web/ui && bun run dev      # Vite dev server
bun check                     # type checking
```

## Concepts

- **Instrument** — the central object: opened hardware (a **HAL**, the runtime device handles) together with a **Bench** of persisted acquisition state. Cameras, lasers, stages, analog outputs, and AOTFs are reached through typed async device handles that behave the same whether the device is local or on a remote node.
- **Templates → instruments** — a microscope is described by a `.voxel.yaml` template with a `hal:` section (the hardware blueprint) and a `default:` section (the baseline acquisition state). Shipped templates live in [`src/vxl/_templates/`](src/vxl/_templates/). Launching one instantiates an instrument under `~/.voxel/instruments/<name>.voxel/` as `config.yaml` (hardware) and `bench.json` (live state).
- **Imaging** — **channels** pair a detection path (camera + filter positions) with an illumination path (laser); **profiles** group channels with DAQ waveform timing for synchronized multi-channel acquisition.
- **Acquisition tasks** — planned stacks and tiles, persisted alongside the rest of the instrument state in `bench.json`.

Start from [`simulated-local.voxel.yaml`](src/vxl/_templates/simulated-local.voxel.yaml) — every device is simulated and runs in-process, so the whole platform is explorable without a microscope.

## Packages

Voxel is a [uv](https://docs.astral.sh/uv/) workspace. The `vxl` package at the root provides microscope orchestration; the rest are workspace members.

| Package | Description |
|---------|-------------|
| [vxl](src/vxl/) | Microscope orchestration, instrument/acquisition model, and configuration (root package) |
| [rigup](rigup/) | Distributed device control framework |
| [vxl-drivers](drivers/) | Hardware drivers (ASI Tiger stages, Vieworks/Hamamatsu/PCO/Ximea cameras, lasers, AA Opto AOTFs) |
| [vxl-web](web/) | Web interface (FastAPI + SvelteKit) |
| [vxl-qt](qt/) | Desktop interface (PySide6) |
| [vxlib](vxlib/) | Shared types and utilities |
| [omezarr](omezarr/) | OME-Zarr streaming writer with multi-scale pyramids |

## License

[MIT](LICENSE) — Allen Institute, Neural Dynamics
