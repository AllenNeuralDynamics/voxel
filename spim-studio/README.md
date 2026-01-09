# SPIM Studio

Web interface and CLI for controlling SPIM microscopes built with spim-rig.

## Quick Start

```bash
# From repository root
uv sync --all-packages --all-extras

# Build web UI
cd spim-studio/spim-ui && pnpm install && pnpm run build && cd ../..

# Run with simulated devices
uv run spim <config.yaml>
```

Open http://localhost:8000

## CLI

```bash
# Start rig controller with web UI
spim <config.yaml> [--port PORT] [--debug]

# Start remote node
spim-node <node_id> --rig <host[:port]> [--debug]
```
