# Records

Discussed on 2026-11-18, decisions added on 2026-11-19 (names, writes, logs, share service), not built. Replaces
`vxl_records` for the new core; `vxl_records` stays frozen for legacy and goes with it. The acquisition loop that
writes the records is in `acquisition.md`.

## Lines

- **Records are the station's own tracker.** Only the `vxl station` that owns them reads and writes them. Their shape
  can change at any time. They live inside `vxl` (`src/vxl/records/`), not in a separate package.
- **Outsiders use a public contract**, fixed and versioned: our Lab, a lab's LIMS, metadata exporters, stitchers,
  scripts. Our Lab gets no special access.
- **Outsiders never cost the station.** No outside request runs in the station process. Image data never passes
  through it.

## The design (canonical)

Chosen on 2026-11-19: design A. Its prototype was removed once it was built in `src/vxl/records/`. Design B (an
event log, `prototypes/records/b_events.py`) stays as the option we did not take. A lives in `acquisition.py` (the
record), `store.py` (the database and the files) and `records.py` (`Records.record`), tested in
`tests/records/test_acquisition_records.py`.

- **1 writer.** The acquisition loop is the only code that changes an acquisition. It holds the record in memory.
- **Context managers set each start and end.** `async with recording(store, acquisition) as run`, then
  `async with run.visit(index) as visit`. A normal exit completes; a cancel cancels; any other error fails, and goes
  on up. Visits that never started are skipped. The loop never names a status.
- **Facts only are stored:** times, results, failures, `frames_written` and locations. Each status is worked out from
  them, so a wrong mix cannot be stored. `acquisition.json` adds the statuses for readers.
- **The store keeps snapshots,** newest revision wins (`UPDATE ... WHERE revision < ?`), then writes the file and
  notifies subscribers.
- **Rules from the validation** (each tested in `tests/records/test_acquisition_records.py`):
  - A group of errors (capture and cleanup) gives 1 failure each.
  - An ending save is shielded from a 2nd cancel, and its own failure is logged; it never hides the real error.
    A record left open is marked interrupted at the next start.
  - A normal exit with missing frames fails the visit (`acquisition.frames_missing`).
  - The run cannot be used after its block ends.
  - `visit.images_opened(locations)` comes after the visit starts: a stage move can fail before any stack opens.
  - Progress is stored at most every second; the live count goes through the activity.
  - The log window opens and closes with the acquisition.

## The record

```text
Acquisition
├── schema: "voxel.acquisition/1"
├── id, operator, status, times, failure, storage
├── instrument_config, instrument_state     # what ran; replaces hardware_snapshot and state_snapshot
└── visits                                  # was volumes; 1 per planned SPIM Volume
    └── Visit
        ├── task, profile, status, failure
        ├── progress: {done, total, unit}, expected_s
        └── channels.<channel>.<camera>: Image
            ├── shape, transform            # pixel index -> stage µm
            ├── status, format
            └── locations
```

- "Acquisition" everywhere: the operation (`start_acquisition`), the activity (`acquisition`), the record
  (`Acquisition`, `AcquisitionStatus`), the store (`AcquisitionStore`) and the file (`acquisition.json`).
- No motion fields. The acquisition reads SPIM's own frozen `Volume`s, kept in memory for the acquisition; the record only
  describes what happened.
- Every visit and image is written `pending` at Start, so totals are known and unrun work becomes `skipped`.
- A visit stores its own status. We may derive it from its images later, if storing it gives no value.
- No separate instrument block. `instrument_config` and `instrument_state` carry the instrument, and the schema
  covers their base fields. A kind's own fields are extra.

## Metadata

- Metadata is per task. Each task in the plan has `metadata`, in the form that the state's `metadata_cls` gives. 1
  task can be 1 subject, or not; vxl does not assume either.
- The acquisition has no `metadata` field of its own. It is in `instrument_state.plan[].metadata`, and a visit names its
  task.
- Frozen at Start. vxl gives the lab the facts as they were; a lab corrects them in its own systems.
- Later option: corrections through the share service, stored next to the acquisition, never in it.

## Writes

- Every life step commits a new revision to SQLite, then rewrites `acquisition.json` at the storage root (local or
  S3), as `vxl_records` does today: create, start, visit start, images registered, visit end, acquisition end.
  Progress is never written to the file.
- SQLite is the truth. A failed file write raises an alert and does not stop the acquisition; the next write tries
  again. Today `ManifestSyncError` reaches the loop.

## Logs

- The records keep the log lines, as `LogJournal` does today: each line goes to SQLite first, then to subscribers.
- Live lines reach every screen through the station feed and the feed proxy.
- The share service serves the full log of 1 acquisition.
- At the end (completed, failed or cancelled), the station writes `acquisition.log.jsonl` next to
  `acquisition.json`, 1 time, so the log travels with the data. S3 cannot add lines to a file, so it is written once.

## Progress

- At Start, the kind gives each visit a planned total in its own unit (`2000 frames`, `12 strips`) and, when it can,
  an expected duration.
- During a visit, the kind reports `done` whenever it can (SPIM: after each batch). A kind with no midpoints reports
  nothing until the visit ends.
- The base keeps the latest value, works out the fraction, time left and acquisition progress, and writes progress to the
  records at a capped rate, newest value only.

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

- Stored data only. Live data goes through the feed proxy.
- Named `share`. `vxl station start` starts it when `station.yaml` has a `share:` section. Off by default.
- Its own process: its own GIL, its own CPU share. Reads SQLite in WAL mode, so it never blocks station writes.
- Capped: lower OS priority, a limit on requests at once.
- Big data comes from storage (Zarr, `acquisition.json`), never through the station.

## Open

- The full public schema of `acquisition.json`: versioned by `schema`, a new major version for a breaking change.
- Logs: copied from `vxl_records` mostly as they are. Presets are left out: the default state covers 1 saved setup;
  named setups, if labs need them, go as files in the instrument folder, not in the records.
