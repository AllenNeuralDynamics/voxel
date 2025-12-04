# SPIM Rig

`spim-rig` is a reference implementation of a selective plane illumination microscope built on top of PyRig. It bundles the orchestration layer (`spim_rig` Python package), a FastAPI/WebSocket control service, and the companion Svelte UI (`spim-ui`) that compiles down to static assets served by the backend.

## What's Inside

- `src/spim_rig`: typed device clients/services, rig configuration schema, and the FastAPI surface for browsers.
- `spim-ui`: the front-end project. `pnpm run build` drops its assets into `src/spim_rig/web/static`.

## Quick Start

1. Install dependencies from the repository root: `uv sync --all-packages --all-extras`.
2. Build the UI assets: `cd spim-rig/spim-ui && pnpm install && pnpm run build && cd ../../`.
3. Launch the simulated rig + web app: `uv run python -m examples.spim.app` and browse to http://localhost:8000.

See [examples/spim/README.md](../examples/spim/README.md) for detailed walkthroughs plus HTTPS/remote access notes.
