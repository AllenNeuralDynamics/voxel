# Lab

Discussed on 2026-11-18, not built. Builds on `records.md`. Replaces the copy-of-records idea in
`notes/platform/lab.md` (2026-10-30).

## Parts

| Part | Runs where | Does |
| --- | --- | --- |
| `vxl station` | each station computer | runs the microscope and owns its records |
| read service | each station computer, its own capped process | serves the public contract and pushes change events |
| `vxl lab` | 1 station computer or a lab server | FastAPI: keeps an index of all stations' runs, serves the Lab app |
| `web/lab` | the browser | the Lab app: SvelteKit on `@voxel/kit`, like the station app |

## Decided

- **The Lab keeps an index, not a copy.** It is built only from the public contract, and can be rebuilt from the
  read services or from the `run.json` files in storage.
- **The read service connects out to the Lab and pushes changes.** It passes firewalls that block incoming
  connections, and the station decides when it joins. The push runs in the read service, so the station pays nothing.
  When the Lab is down, waiting changes merge, newest per run; the Lab catches up when it returns.

## Proposed, not confirmed

- **Pixels come from storage, never from the station:** S3 links signed by `vxl lab`, or the shared drive. A station's
  own disk is reached through its read service, at its capped rate.
- **"Operate" only links to the station app.** The Lab sends no commands; it stays read-only.

## Open

- Login, and who may see which runs (large labs, later).
- How a station finds the Lab: an address in `station.yaml` first, maybe discovery later.
- Whether a small lab runs `vxl lab` on the station computer, and whether 1 command starts both.
