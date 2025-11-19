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

### 3. Generate SSL Certificates

To enable WebGPU support (required for the camera preview) on remote connections, you need to serve the app over HTTPS. Generate self-signed certificates:

```bash
# From the root directory
uv run python examples/spim/generate_cert.py
```

This will create `cert.pem` and `key.pem` in the `examples/spim` directory.

### 4. Run the Application

Start the simulated rig and web server:

```bash
# From the root directory
uv run python examples/spim/app.py
```

## Accessing the UI

- **Local**: Open `https://localhost:8000`
- **Remote**: Open `https://<your-ip>:8000`

**Note**: Since we are using self-signed certificates, your browser will show a "Not Secure" warning. You must manually proceed (Advanced -> Proceed to...) to access the UI and enable WebGPU.
