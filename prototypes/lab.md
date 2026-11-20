# Lab

Discussed on 2026-11-18, not built. Builds on `records.md`. Replaces the copy-of-records idea in
`notes/platform/lab.md` (2026-10-30).

## Parts

| Part | Runs where | Does |
| --- | --- | --- |
| `vxl station` | each station computer | runs the microscope and owns its records |
| feed proxy | each station computer, or another computer | fans out the station feed; connects out to the Lab and pushes its topics (`proxy.md`) |
| share service | each station computer, its own capped process | serves stored data: `acquisition.json`, the full log, history |
| `vxl lab` | 1 station computer or a lab server | FastAPI: keeps an index of all stations' runs, serves the Lab app |
| `web/lab` | the browser | the Lab app: SvelteKit on `@voxel/kit`, like the station app |

## Decided

- **The Lab keeps an index, not a copy.** It is built only from the public contract, and can be rebuilt from the
  share services or from the `acquisition.json` files in storage.
- **The feed proxy connects out to the Lab and pushes the Lab's topics** (decided 2026-11-19). It passes firewalls
  that block incoming connections, and the station decides when it joins. The push runs in the proxy, so the station
  pays nothing. When the Lab is down, waiting changes merge, newest per topic; the Lab catches up when it returns.
- **The Lab reads stored data from the share service.** It never subscribes to the station feed itself.

## Proposed, not confirmed

- **Pixels come from storage, never from the station:** S3 links signed by `vxl lab`, or the shared drive. A station's
  own disk is reached through its read service, at its capped rate.
- **"Operate" only links to the station app.** The Lab sends no commands; it stays read-only.

## Open

- Login, and who may see which runs (large labs, later).
- How a station finds the Lab: an address in `station.yaml` first, maybe discovery later.
- A small lab may run the lab server on the station computer: `vxl station start --with-lab` starts both (decided
  2026-11-19, see `station.md`).

## Where it will live

See the table in `station.md`.
