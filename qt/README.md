# vxl-qt

The desktop interface for Voxel: a PySide6 application integrated with asyncio through [qasync](https://github.com/CabbageDevelopment/qasync), so Qt widgets and the async device stack share one event loop.

The app is IDE-style, with two top-level windows:

- **LaunchWindow** — the home. Owns the `vxl.app.VoxelApp` (and thus the instrument lifecycle), lists instruments, and launches one.
- **MainWindow** — the control workspace for a launched instrument. Owns the instrument-scoped device stores and panels (`preview/`, `devices/`, `waveforms.py`, `grid.py`, `channels.py`, `logs.py`), rebuilt per launch.

## Development

Requires [uv](https://docs.astral.sh/uv/). Run from the repository root:

```bash
uv run vxl-qt                 # launch; optionally: uv run vxl-qt config.yaml
uv run vxl-qt -v              # verbose (debug) logging
```

Panels bind directly to the instrument's reactive state (`state`, `active_profile_id`). Styling uses design tokens with a dark theme. Per Qt convention this package uses camelCase method names, so ruff's `N802`/`N815` naming rules are relaxed for `qt/`.
