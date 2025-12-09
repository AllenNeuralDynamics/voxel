# SPIM Rig

A complete selective plane illumination microscope implementation using PyRig. Includes device drivers, typed clients/services, web UI, and CLI.

## Quick Start

```bash
# From repository root
uv sync --all-packages --all-extras

# Build web UI
cd spim-rig/spim-ui
pnpm install
pnpm run build
cd ../../

# Run simulated rig
uv run spim rig spim-rig/examples/simulated.yaml
```

Open http://localhost:8000

## CLI Usage

```bash
# Start rig controller with web UI
spim rig <config.yaml> [--port PORT] [--debug]

# Start node service
spim node <node_id> --rig <host[:port]> [--debug]
```

See [examples/README.md](examples/README.md) for more examples and demos.
