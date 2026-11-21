# Lab

Discussed on 2026-11-18, reworked on 2026-11-20 for the server model (`server.md`). Not built. Builds on
`records.md`. Replaces the copy-of-records idea in `notes/platform/lab.md` (2026-10-30).

## Parts

| Part | Runs where | Does |
| --- | --- | --- |
| `vxl station` | each station computer | the station service: runs the microscope and owns its records |
| server | each station computer, and the lab computer | the same program everywhere: the web front of 1 service (`server.md`) |
| `vxl lab` | the lab computer, or a station computer | the lab service, a peer of the station service: lab topics, its HTTP operations (`vxl.web.lab`) |
| `web/lab` | the browser | the lab page: SvelteKit on `@voxel/kit`, like the station app |

`vxl lab start` reads `~/.voxel/lab.yaml` and starts the lab service and a server for it. On a station computer that
also runs the lab, the 2 servers use 2 ports.

## Decided

- **The lab is a service, not a server in the middle.** It owns lab state (the known stations, later alert
  acknowledgements) and publishes it as topics. Its HTTP operations (`vxl.web.lab`) come with the first lab
  operation.
- **The lab service reads each station's server as an ordinary reader** (`vxl.web.client`), as a notebook does: the
  small topics (status, run progress, alerts). It publishes what it reads as lab topics, so the lab page reads from
  the lab's server only. Decided on 2026-11-20; before, each station's gateway connected out to a gateway on the lab
  computer.
- **Opening a station from the lab sends the browser to that station's server.** The window then talks to that
  station only: frames, commands and history. No frame passes the lab computer.
- **The lab must be able to reach each station computer,** as in a VPN. A station that the lab cannot reach is a
  later case (`server.md` › Decided on 2026-11-20).
- **The lab keeps an index, not a copy.** It is built only from the public contract, and can be rebuilt from the
  stations' servers or from the `acquisition.json` files in storage.

## Data viewer

Later: a Zarr v3 viewer in the lab page. The browser reads `zarr.json`, then only the chunks it shows; sharded images
need HTTP Range requests.

- Remote storage (S3, MinIO, a file server) serves itself. The record holds the URL. The lab can hand out signed,
  short-lived URLs through its HTTP operations.
- Local data is served by the server on the machine that has the disk, at `/data/...`; a station's disk is reached
  at that station's server.

## Open

- How the lab learns each station's address: a list in `lab.yaml`, or each station tells the lab.
- Login, and who may see which runs: each station's server must check who the person is (`server.md` › Open).
- The lab page's history across stations: from the lab service's index, or from each station's server.
- Reading a station's local data while it runs (`server.md`).

## Where it will live

See the table in `station.md`.
