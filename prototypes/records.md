# Records

Discussed on 2026-11-18 and 2026-11-19. **Built** in `src/vxl/records/` (2026-11-19), tested in
`tests/records/`. The share service and the public schema are not built. Replaces `vxl_records` for the new core;
`vxl_records` stays frozen for legacy and goes with it. The loop that writes the records is in `acquisition.md`.

## Lines

- **Records are the station's own tracker.** Only the `vxl station` that owns them reads and writes them. Their shape
  can change at any time. They live inside `vxl` (`src/vxl/records/`), not in a separate package.
- **Outsiders use a public contract**, fixed and versioned: our Lab, a lab's LIMS, metadata exporters, stitchers,
  scripts. Our Lab gets no special access.
- **Outsiders never cost the station.** No outside request runs in the station process. Image data never passes
  through it.

## How it works

The record is in `acquisition.py`, the database and files in `store.py`, and `Records.record` in `records.py`.

- **1 writer.** The acquisition loop is the only code that changes an acquisition. It holds the record in memory.
- **Context managers set each start and end.** `async with records.record(acquisition) as run`, then
  `async with run.visit(index) as visit`. A normal exit completes; a cancel cancels; any other error fails, and goes
  on up. Visits that never started are skipped. The loop never names a status.
- **Facts only are stored:** times, results, failures, `frames_written` and locations. Each status is worked out from
  them, so a wrong mix cannot be stored. `acquisition.json` adds the statuses for readers.
- **The store keeps snapshots,** newest revision wins (`UPDATE ... WHERE revision < ?`), then writes the file and
  notifies subscribers.
- **Rules** (each tested):
  - A group of errors (capture and cleanup) gives 1 failure each.
  - An ending save is shielded from a 2nd cancel, and its own failure is logged; it never hides the real error.
    A record left open is marked interrupted at the next start (`AcquisitionStore.interrupt_open`).
  - A normal exit with missing frames fails the visit (`acquisition.frames_missing`).
  - The run cannot be used after its block ends.
  - `visit.images_opened(locations)` comes after the visit starts: a stage move can fail before any image opens.
  - Progress (`visit.frames(camera, written)`) is saved at most every second, without a file write.
  - The log window opens and closes with the acquisition.

## The record

```text
Acquisition
├── schema: "voxel.acquisition/1"
├── id, revision, operator, host, times, result, failures, storage
├── instrument_config, instrument_state     # what ran, frozen at Start
└── visits                                  # 1 per planned SPIM Volume
    └── Visit
        ├── task, profile, times, result, failures
        └── channels.<channel>.<camera>: Image
            ├── format, transform           # pixel index -> stage µm; axis 0 counts the frames
            ├── locations
            └── frames_written
```

- "Acquisition" everywhere: the operation (`start_acquisition`), the activity (`acquisition`), the record
  (`Acquisition`, `AcquisitionStatus`), the store (`AcquisitionStore`) and the file (`acquisition.json`).
- No motion fields. The loop reads SPIM's own frozen `Volume`s; the record only describes what happened.
- Every visit and image is written at Start, so totals are known (`Image.frames_total` from its transform) and unrun
  work becomes `skipped`.
- A visit stores its own result. We may derive it from its images later, if storing it gives no value.
- No separate instrument block. `instrument_config` and `instrument_state` carry the instrument.

## Dropped frames

Agreed on 2026-11-20, not built. A sweep may drop whole batches when the writer is full (`writer.md`).

- `Image.dropped: list[FrameRange]`, empty by default.
- `Visit.missing()` counts only frames neither written nor dropped. So a sweep with drops completes, and a step scan
  that lost frames still fails.
- New image status `gaps`: every frame is accounted for, but some were dropped. `completed` stays for "every frame
  written".
- `VisitRecording.frames_dropped(camera, ranges)`: the loop reports the drops before the visit ends.
- No new result or state for "completed with drops": a result says how a visit ended, and the drops are facts on
  the images. When a reader needs it (a screen, `acquisition.json` readers), add `frames_dropped` sums on `Visit`
  and `Acquisition`, worked out from the images, and show them in `for_readers()`.

## Metadata

- Metadata is per task. Each task in the plan has `metadata`, in the form that the state's `metadata_cls` gives. 1
  task can be 1 subject, or not; vxl does not assume either.
- The acquisition has no `metadata` field of its own. It is in `instrument_state.plan[].metadata`, and a visit names
  its task.
- Frozen at Start. vxl gives the lab the facts as they were; a lab corrects them in its own systems.
- Later option: corrections through the share service, stored next to the acquisition, never in it.

## Writes

- Every life step commits a new revision to SQLite, then rewrites `acquisition.json` at the storage root (local or
  S3): create, start, visit start, images opened, visit end, acquisition end. Progress is never written to the file.
- SQLite is the truth. A failed file write is logged and does not stop the acquisition; the next save writes it
  again.

## Logs

- `LogJournal` keeps the log lines: each line goes to SQLite first, then to subscribers.
- Live lines reach every screen through the station feed and the feed proxy.
- The share service serves the full log of 1 acquisition.
- At the end, `acquisition.log.jsonl` is written next to `acquisition.json`, 1 time, so the log travels with the data.
  S3 cannot add lines to a file. `AcquisitionStore.write_log` exists; `Records.record` does not call it yet.

## Public contract

Live data comes through the feed proxy. Stored data has 1 source, the records database, with 2 outputs that share 1
schema:

| | Feed proxy | Share service | `acquisition.json` |
| --- | --- | --- | --- |
| Job | live: status, progress, logs, frames | stored: history, search, full logs | the copy that travels with the data |
| How | 1 feed from the station, fanned out (`proxy.md`) | a separate, capped process that reads the database (WAL) | written by the station at each life step |
| Freshness | live | as stored | life steps |

The share service and `acquisition.json` carry the record's `revision`, so a reader can tell which is newer.

## Share service

Not built.

- Stored data only. Live data goes through the feed proxy.
- Named `share`. `vxl station start` starts it when `station.yaml` has `share:` and `--no-share` is not given (see
  `station.md`).
- Its own process: its own GIL, its own CPU share. Reads SQLite in WAL mode, so it never blocks station writes.
- Capped: lower OS priority, a limit on requests at once.
- Big data comes from storage (Zarr, `acquisition.json`), never through the station.

## Open

- The full public schema of `acquisition.json`: versioned by `schema`, a new major version for a breaking change.
- Presets are left out: the default state covers 1 saved setup; named setups, if labs need them, go as files in the
  instrument folder, not in the records.
