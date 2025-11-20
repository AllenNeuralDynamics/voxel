# SPIM Rig Example

This example demonstrates how to run the SPIM rig control software with a simulated microscope and a web-based user interface.

## Prerequisites

- Python 3.13+
- `uv` package manager
- `pnpm` (for building the UI)

## Setup Instructions

### 1. Install Python Dependencies

From the root of the `pyrig` repository:

```bash
uv sync --all-packages --all-extras
```

### 2. Build the Web UI

The Python backend serves the pre-built UI files. You need to build them first.

```bash
cd spim-rig/spim-ui
pnpm install
pnpm run build
```

This will generate the static files in `spim-rig/src/spim_rig/web/static`.

### 3. Run the Application

Start the simulated rig and web server:

```bash
# From the root directory
uv run python examples/spim/app.py
```

## Accessing the UI

Open your browser to:
- **Local**: `http://localhost:8000`

The application runs on localhost only by default. For remote access with HTTPS support, see the [Certificate Management Tool](../../scripts/cert.py) documentation.

