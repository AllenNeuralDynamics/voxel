# Lab

Discussed on 2026-11-18, reworked on 2026-11-20 for the gateway model (`gateway.md`). Not built. Builds on
`records.md`. Replaces the copy-of-records idea in `notes/platform/lab.md` (2026-10-30).

## Parts

| Part | Runs where | Does |
| --- | --- | --- |
| `vxl station` | each station computer | runs the microscope and owns its records; a publisher |
| gateway | each station computer, and the lab computer | the same program everywhere: cache, fan-out, routing, records history, local `/data` |
| `vxl lab` | the lab computer, or a station computer | a publisher, a peer of the station: lab topics, `vxl.lab.api` |
| `web/lab` | the browser | the lab page: SvelteKit on `@voxel/kit`, like the station app |

`vxl lab start` reads `~/.voxel/lab.yaml` and starts the lab and a gateway side by side. The lab does not run a
gateway inside it; the gateway connects to the lab as to any publisher.

## Decided

- **The lab is a publisher, not a server in the middle.** It owns lab state (the known stations, later alert
  acknowledgements) and publishes it as topics. `vxl.lab.api` comes with the first lab operation.
- **Station gateways connect out to the lab computer** (`gateway.upstream` in `station.yaml`). They pass firewalls
  that block incoming connections, and the station decides when it joins. A station joins only the lab computers in
  its own settings.
- **Each station gets a token from the lab**, which the gateway on the lab computer checks. Details later.
- **Small topics always flow up; frames only on demand.** Status, run progress and alerts always reach the lab
  computer. Frames leave a station computer only while a window at the lab watches that station.
- **The lab page reads from its gateway only.** History and full logs come from each station's gateway, routed under
  `/stations/<id>/`.
- **The lab keeps an index, not a copy.** It is built only from the public contract, and can be rebuilt from the
  station gateways or from the `acquisition.json` files in storage.
- **Opening a station from the lab** opens a normal station window through the lab computer, at `/stations/<id>/`.

## Data viewer

Later: a Zarr v3 viewer in the lab page. The browser reads `zarr.json`, then only the chunks it shows; sharded images
need HTTP Range requests.

- Remote storage (S3, MinIO, a file server) serves itself. The record holds the URL. The lab can hand out signed,
  short-lived URLs through `vxl.lab.api`.
- Local data is served by the gateway on the machine that has the disk, at `/data/...`; a station's disk is reached
  at `/stations/<id>/data/...`.

## Open

- The token: how the lab issues it and how a station stores it.
- Login, and who may see which runs (large labs, later).
- Reading a station's local data while it runs (`gateway.md`).

## Where it will live

See the table in `station.md`.
