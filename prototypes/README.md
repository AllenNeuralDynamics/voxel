# Prototypes

Agreed designs and try-out code, before they go into `src/`. Each note says at the top when it was discussed and
whether it is built.

## Notes

| Note | What | State |
| --- | --- | --- |
| `acquisition.md` | The acquisition loop in SPIM: commands, live state, resources, the batch loop for steps and sweeps | built; to-do list in the note |
| `records.md` | The station's records of acquisitions and logs, and the public contract | built, except the records history in the gateway |
| `writer.md` | How images reach storage, OME-Zarr 0.6 geometry, line scan | mostly built; memory per camera is not |
| `dropped-frames.md` | Frames the camera drivers lose, and 1 rule for every driver | not built |
| `interface.md` | Instrument operations declared with decorators, and the HTTP rules for the station API | built; HTTP is a try-out |
| `metadata.md` | Task metadata on the Run and History pages | not built |
| `feed.md` | The station feed with topics | not built |
| `gateway.md` | The gateway: cache, fan-out, routing, records history, local data; 1 kind at every level | not built |
| `lab.md` | The lab publisher, its lab page and the later data viewer | not built |
| `station.md` | How the station's parts fit together, and where each will live | not built |
| `tuning-knobs.md` | Tuning knobs | backend built; UI in the Lab only |
| `TODO.md` | All pending work, in 1 list, with links to the notes | — |

## Code

| File | What |
| --- | --- |
| `demo.py` | A session on a simulated SPIM microscope (`uv run -m prototypes.demo`) |
| `interface/` | HTTP routes from the interface of an open instrument (`uv run python -m prototypes.interface.demo`) |
| `calibration.py` | Power meter readings on each light path, in `calibration.json` |
