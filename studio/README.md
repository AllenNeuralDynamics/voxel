# Voxel Studio

Web interface and CLI for controlling Voxel microscopes.

## Quick Start

```bash
# From repository root
uv sync --all-packages --all-extras

# Build web UI
cd voxel-studio/voxel-ui && pnpm install && pnpm run build && cd ../..

# Run with simulated devices
uv run voxel <config.yaml>
```

Open http://localhost:8000

## CLI

```bash
# Start rig controller with web UI
voxel <config.yaml> [--port PORT] [--debug]

# Start remote node
voxel-node <node_id> --rig <host[:port]> [--debug]
```
