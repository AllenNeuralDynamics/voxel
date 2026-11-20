# Prototypes

Agreed designs and try-out code, before they go into `src/`. Each note says at the top when it was discussed and
whether it is built.

## Notes

| Note | What | State |
| --- | --- | --- |
| `acquisition.md` | The acquisition loop in SPIM: commands, live state, resources, the batch loop for steps and sweeps | built; to-do list in the note |
| `records.md` | The station's records of acquisitions and logs, and the public contract | built, except the share service |
| `writer.md` | How images reach storage, OME-Zarr 0.6 geometry, line scan | mostly built |
| `interface.md` | Instrument operations declared with decorators, and their HTTP routes | built; HTTP is a try-out |
| `feed.md` | The station feed with topics | not built |
| `proxy.md` | The feed proxy that fans the feed out | not built |
| `lab.md` | The lab server and its browser app | not built |
| `station.md` | How the station's parts fit together, and where each will live | not built |
| `tuning-knobs.md` | Tuning knobs | discussed, nothing decided |
| `TODO.md` | Work to remember: alerts | not built |

## Code

| File | What |
| --- | --- |
| `demo.py` | A session on a simulated SPIM microscope (`uv run -m prototypes.demo`) |
| `interface/` | HTTP routes from the interface of an open instrument (`uv run python -m prototypes.interface.demo`) |
| `panels.py` | The panels of a preview: cameras that see 1 plane, and each picture placed in it |
| `calibration.py` | Power meter readings on each light path, in `calibration.json` |
| `specimen-simulation.png` | Frames from the simulated specimen camera |
