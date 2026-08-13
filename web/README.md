# vxl-web

The web interface for Voxel: a FastAPI backend that owns the open instrument and a SvelteKit frontend that talks to it over HTTP and WebSocket. The backend runs as a single process per microscope — it holds the hardware, the message bus, and one event loop.

- **Backend** (`src/vxl_web/`) — FastAPI composed around `vxl.station.Station`. `app.py` owns process setup, `router.py` exposes station/session/instrument operations, and `realtime.py` delivers station state, preview frames, and logs over WebSockets.
- **Frontend** (`ui/`) — SvelteKit, Svelte 5, Tailwind CSS v4. The built assets are served by the backend from `src/vxl_web/static/`.

## Development

Requires [uv](https://docs.astral.sh/uv/) and [Nub](https://nubjs.com/). Run from the repository root.

Build the frontend, then start the backend (which serves the built assets):

```bash
cd web/ui && nub install && nub run build && cd ../..
uv run vxl                    # http://localhost:8000  (--host, --port, --debug)
```

For frontend work with hot reload, run the Vite dev server alongside the backend:

```bash
cd web/ui
nub run dev                   # Vite dev server
nub run check                 # type-check (svelte-check) + lint
```

## Third-party licenses

The frontend uses [`@bokuweb/zstd-wasm`](https://github.com/bokuweb/zstd-wasm) as a fallback for browsers
without native Zstandard decompression. Its TypeScript glue is licensed under the MIT License, and the compiled
[Zstandard](https://github.com/facebook/zstd) decoder is licensed under the BSD 3-Clause License. Distributions
must retain the applicable copyright notices, license terms, and disclaimers.

Before a packaged release, include the complete upstream notices in a dedicated `THIRD_PARTY_NOTICES.md` file.
