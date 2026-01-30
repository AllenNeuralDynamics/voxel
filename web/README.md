# Voxel Studio

Web interface and CLI for controlling Voxel microscopes.

## Quick Start

```bash
# From repository root
uv sync --all-packages --all-extras

# Build web UI
cd web/ui && pnpm install && pnpm run build && cd ../..

# Run
uv run vxl
```

Open http://localhost:8000

## CLI

```bash
# Start remote node
voxel-node <node_id> --rig <host[:port]> [--debug]
```
