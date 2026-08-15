<h1>
    <div>
        <img src="voxel-logo.png" alt="Voxel Logo" width="50" height="50">
    </div>
    Voxel
</h1>

A light sheet microscopy platform for hardware control, acquisition orchestration, and data streaming. A control
**station** owns one active instrument session and exposes it to the web or desktop application. The **instrument**
combines opened hardware with persisted acquisition state. Device control is built on [rigup](rigup/), which runs
devices in-process or across networked nodes behind one API.

> [!Warning]
> Under active development. APIs, configuration schemas, and documentation are evolving.

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and [Nub](https://nubjs.com/) (for the web frontend).

```bash
uv sync --all-packages --all-extras --all-groups
uv run vxl station init --name my-microscope
```

The one-time station command creates `~/.voxel/station.yaml`, which is required by the web and desktop control
applications. Remote device nodes do not require a station; they may use an optional `~/.voxel/system.yaml`,
`VOXEL_*` environment variables, or machine defaults.

### Web interface (FastAPI + SvelteKit)

The frontend is built once, then served by the backend:

```bash
cd web-ui && nub install && nub run build && cd ..
uv run vxl serve
```

Open http://localhost:8000 and launch the `simulated-local` template to explore the full interface with no hardware attached.

### Desktop interface (PySide6)

```bash
uv run vxl qt                 # optionally: uv run vxl qt config.yaml
```

## Development

Choose the environment that matches the area you are working on:

```bash
# Core libraries and workspace packages
uv sync --all-packages --all-groups

# Web application
uv sync --all-packages --extra web --all-groups
nub install --cwd web-ui --frozen-lockfile

# Qt application
uv sync --all-packages --extra qt --all-groups

# Complete development environment
uv sync --all-packages --all-extras --all-groups
nub install --cwd web-ui --frozen-lockfile
```

Install the repository hooks after the initial setup:

```bash
uvx pre-commit install
uvx pre-commit run --all-files  # optional initial validation
```

`pre-commit` runs Ruff and updates the uv lockfile. `pre-push` adds basedpyright, the non-slow Python tests, and
frontend checks. Run the principal checks directly while developing:

```bash
uv run ruff check
uv run ruff format --check
uv run basedpyright
uv run pytest -m "not slow"
nub run --cwd web-ui check
```

Tests marked `slow` exercise networking or Zarr I/O and can be run explicitly with `uv run pytest -m slow`. Only run
hardware-dependent tests when the relevant equipment is explicitly available.

For frontend work, run the Vite development server separately from the Python backend:

```bash
nub run --cwd web-ui dev
uv run vxl serve
```

Build release artifacts with the locked frontend dependencies and generated static bundle included:

```bash
uv run scripts/build.py
```

## Concepts

- **Station** — the application lifecycle boundary. It owns at most one instrument session and publishes the session's
  complete state and preview stream through a **StationFeed**.
- **Instrument** — opened hardware (a **HAL**, the runtime device handles) together with persisted acquisition state. Cameras, lasers, stages, analog outputs, and AOTFs are reached through typed async device handles that behave the same whether the device is local or on a remote node.
- **Templates → instruments** — a microscope is described by a `.voxel.yaml` template with a `hal:` section (the hardware blueprint) and a `default:` section (the baseline acquisition state). Shipped templates live in [`src/vxl/station/templates/builtins/`](src/vxl/station/templates/builtins/). Launching one instantiates an instrument under `~/.voxel/instruments/<name>.voxel/` as `config.yaml` (hardware) and `state.json` (live state).
- **Imaging** — **channels** pair a detection path (camera + filter positions) with an illumination path (laser); **profiles** group channels with DAQ waveform timing for synchronized multi-channel acquisition.
- **Acquisition tasks** — planned stacks and tiles, persisted alongside the rest of the instrument state in `state.json`.
- **Records** — acquisitions, reusable presets, and operational logs stored through `vxl-records`; SQLite is the local
  implementation.

Start from [`simulated-local.voxel.yaml`](src/vxl/station/templates/builtins/simulated-local.voxel.yaml) — every device is simulated and runs in-process, so the whole platform is explorable without a microscope.

## Packages

Voxel is a [uv](https://docs.astral.sh/uv/) workspace. The `vxl` package at the root provides microscope orchestration; the rest are workspace members.

| Package | Description |
|---------|-------------|
| [vxl](src/vxl/) | Microscope runtime, unified CLI, and web and Qt interfaces |
| [rigup](rigup/) | Distributed device control framework |
| [vxl-drivers](drivers/) | Hardware drivers (ASI Tiger stages, Vieworks/Hamamatsu/PCO/Ximea cameras, lasers, AA Opto AOTFs) |
| [vxl-records](records/) | SQLite-backed acquisitions, presets, and operational log journal |
| [vxlib](vxlib/) | Shared types and utilities |
| [omezarr](omezarr/) | OME-Zarr streaming writer with multi-scale pyramids |
| [bench](bench/) | Non-published OME-Zarr performance and behavior benchmarks |

The Svelte frontend source lives in [`web-ui/`](web-ui/) and builds into package data served by `vxl.web`.

## License

[MIT](LICENSE) — Allen Institute, Neural Dynamics
