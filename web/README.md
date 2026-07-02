# vxl-web

The web interface for Voxel: a FastAPI backend that owns the open instrument and a SvelteKit frontend that talks to it over HTTP and WebSocket. The backend runs as a single process per microscope — it holds the hardware, the message bus, and one event loop.

- **Backend** (`src/vxl_web/`) — FastAPI. `app.py` (factory + entrypoint), `router.py` (the `VoxelApp` and active-`Instrument` routes), `live.py` (per-instrument WebSocket feed), `wire.py` (msgpack message bus).
- **Frontend** (`ui/`) — SvelteKit, Svelte 5, Tailwind CSS v4. The built assets are served by the backend from `src/vxl_web/static/`.

## Development

Requires [uv](https://docs.astral.sh/uv/) and [bun](https://bun.sh/). Run from the repository root.

Build the frontend, then start the backend (which serves the built assets):

```bash
cd web/ui && bun install && bun run build && cd ../..
uv run vxl                    # http://localhost:8000  (--host, --port, --debug)
```

For frontend work with hot reload, run the Vite dev server alongside the backend:

```bash
cd web/ui
bun run dev                   # Vite dev server
bun check                     # type-check (svelte-check) + lint
```
