# Records

Discussed on 2026-11-18, decisions added on 2026-11-19, not built. Replaces `vxl_records` for the new core; `vxl_records` stays frozen for legacy and
goes with it.

## Lines

- **Records are the station's own tracker.** Only the `vxl station` that owns them reads and writes them. Their shape
  can change at any time. They live inside `vxl` (`src/vxl/records/`), not in a separate package.
- **Outsiders use a public contract**, fixed and versioned: our Lab, a lab's LIMS, metadata exporters, stitchers,
  scripts. Our Lab gets no special access.
- **Outsiders never cost the station.** No outside request runs in the station process. Image data never passes
  through it.

## The record

```text
Run
├── schema: "voxel.run/1"
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

- No motion fields. The capture reads SPIM's own frozen `Volume`s, kept in memory for the run; the record only
  describes what happened.
- Every visit and image is written `pending` at Start, so totals are known and unrun work becomes `skipped`.
- A visit stores its own status. We may derive it from its images later, if storing it gives no value.
- No separate instrument block. `instrument_config` and `instrument_state` carry the instrument, and the schema
  covers their base fields. A kind's own fields are extra.

## Metadata

- Metadata is per task. Each task in the plan has `metadata`, in the form that the state's `metadata_cls` gives. 1
  task can be 1 subject, or not; vxl does not assume either.
- The run has no `metadata` field of its own. It is in `instrument_state.plan[].metadata`, and a visit names its
  task.
- Frozen at Start. vxl gives the lab the facts as they were; a lab corrects them in its own systems.
- Later option: corrections through the share service, stored next to the run, never in it.

## Progress

- At Start, the kind gives each visit a planned total in its own unit (`2000 frames`, `12 strips`) and, when it can,
  an expected duration.
- During a visit, the kind reports `done` whenever it can (SPIM: after each batch). A kind with no midpoints reports
  nothing until the visit ends.
- The base keeps the latest value, works out the fraction, time left and run progress, and writes progress to the
  records at a capped rate, newest value only.

## Public contract

1 source, the records database, with 2 outputs that share 1 schema:

| | Share service | `run.json` |
| --- | --- | --- |
| Job | live: status, progress, search, change events | the copy that travels with the data |
| How | a separate, capped process that reads the database (WAL) | written by the station at Start, each visit end, and the end |
| Freshness | seconds | visit ends |

Both carry the record's `revision`, so a reader can tell which is newer.

## Share service

- Named `share`. `vxl station start` starts it when `station.yaml` has a `share:` section. Off by default.
- Its own process: its own GIL, its own CPU share. Reads SQLite in WAL mode, so it never blocks station writes.
- Capped: lower OS priority, a limit on requests at once.
- Big data comes from storage (Zarr, `run.json`), never through the station.

## Open

- The full public schema of `run.json`: versioned by `schema`, a new major version for a breaking change.
- Presets and logs: copied from `vxl_records` mostly as they are.
