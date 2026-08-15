# Web interface

The SvelteKit frontend for `vxl.web`. Its production build is package data served by the FastAPI application from
`src/vxl/web/static/`.

From this directory:

```bash
nub install
nub run build
nub run dev       # hot-reload frontend; proxy API requests to localhost:8000
nub run check     # type checking and linting
```

The state, preview, and log WebSockets are independent lanes: state is reliable and ordered, preview is latest-frame
delivery, and logs stream committed journal entries.

## Third-party licenses

The frontend uses [`@bokuweb/zstd-wasm`](https://github.com/bokuweb/zstd-wasm) as a fallback for browsers without
native Zstandard decompression. Its TypeScript glue is MIT-licensed, while the compiled Zstandard decoder uses the
BSD 3-Clause License. Packaged releases must include the applicable notices in `THIRD_PARTY_NOTICES.md`.
