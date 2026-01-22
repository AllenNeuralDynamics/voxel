# Voxel Rig Examples

## Quick Start

```bash
# From voxel-studio directory
uv sync --all-packages --all-extras

# Build web UI
cd voxel-ui && pnpm install && pnpm run build && cd ..

# Run simulated rig
uv run voxel rig examples/simulated.yaml
```

Open browser to http://localhost:8000

## Examples

- **`simulated.yaml`** - Simulated microscope config (default)
- **`system.yaml`** - Real hardware config

Run the demo:
```bash
uv run python examples/demo.py examples/simulated.yaml
```
