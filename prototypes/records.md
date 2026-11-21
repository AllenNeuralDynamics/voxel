# Records

Discussed on 2026-11-18 and 2026-11-19. **Built** in `src/vxl/records/` (2026-11-19), tested in
`tests/records/`. The records history in the gateway and the public schema are not built. Replaces `vxl_records` for the new core;
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

Agreed and built on 2026-11-20 (`Image.dropped`, the `gaps` status, `frames_dropped`), except the sums on
`Visit` and `Acquisition`, which wait for a reader. A sweep may drop whole batches when the writer is full (`writer.md`).

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
- Later option: corrections through `vxl.station.api`, stored next to the acquisition, never in it.

## Writes

- Every life step commits a new revision to SQLite, then rewrites `acquisition.json` at the storage root (local or
  S3): create, start, visit start, images opened, visit end, acquisition end. Progress is never written to the file.
- SQLite is the truth. A failed file write is logged and does not stop the acquisition; the next save writes it
  again.

## Logs

- `LogJournal` keeps the log lines: each line goes to SQLite first, then to subscribers.
- Live lines reach every window through the station feed and the gateway.
- The gateway serves the full log of 1 acquisition.
- At the end, `acquisition.log.jsonl` is written next to `acquisition.json`, 1 time, so the log travels with the data.
  S3 cannot add lines to a file. `AcquisitionStore.write_log` exists; `Records.record` does not call it yet.

## Public contract

Live data comes through the gateway. Stored data has 1 source, the records database, with 2 outputs that share 1
schema:

| | Gateway, live | Gateway, records history | `acquisition.json` |
| --- | --- | --- | --- |
| Job | live: status, progress, logs, frames | stored: history, search, full logs | the copy that travels with the data |
| How | 1 feed from the station, fanned out (`gateway.md`) | the gateway's capped process reads the database (WAL) | written by the station at each life step |
| Freshness | live | as stored | life steps |

The records history and `acquisition.json` carry the record's `revision`, so a reader can tell which is newer.

## Records history in the gateway

Not built. Replaces the share service (2026-11-20, `gateway.md`).

- The gateway serves stored data next to the live feed: history, `acquisition.json`, full logs.
- Its own process: its own GIL, its own CPU share. Reads SQLite in WAL mode, so it never blocks station writes.
- Capped: lower OS priority, a limit on requests at once.
- It reads the database through the public read schema, so a gateway in another language can read it too.
- Big data comes from storage (Zarr, `acquisition.json`), never through the station.

## Listing and filters

Discussed on 2026-11-21 for the History page. Nothing here is built.

**For now: only filters the database answers with its indexes.** History filters by status and by a range of the
created time ("Any time", "Today", "Last 7 days", "Last 30 days"), newest first.

- The table already has what they need (`migrations/0001_initial.sql`): `created_at_us`, an index on it for
  acquisitions that are not archived, and an index on `status, created_at_us`. "Failed, in the last 7 days" is an
  indexed query.
- Missing: a store method with conditions. `AcquisitionStore` has only `list_all()`, which returns every record in full.
  Add 1 list method taking an instrument, a status and a from/to time, using those indexes.
- Add an index on `instrument, created_at_us`: each station page lists 1 instrument, and the `instrument` column has
  no index today.
- A custom range, in the app only (not the Lab): a last menu item, "Custom range…", opens bits-ui's date range
  picker; the box then shows the range ("Created: 12–18 Nov"). The kit already depends on `bits-ui` and
  `@internationalized/date` but has no date picker part yet. The created-time index serves any from/to range, so the
  backend needs nothing more than the list method above.

**Later, by what each needs:**

| Filter | Where the value is | What it needs |
|---|---|---|
| Operator | `operator`, top level of every record: a fixed place | Its own column written on save (as `status`), or an index on `json_extract(acquisition_json, '$.operator')`, or a generated column |
| Key value (the subject), task names | Each task's metadata in `instrument_state.plan[].metadata`, shaped by the instrument's metadata form | A side table filled on save, `acquisition_keys(acquisition_id, field, value)`, indexed on `value` or `field, value` |
| Profile | `visits[].profile` | The same side table, or its own `acquisition_profiles(acquisition_id, profile)` |
| Free text (notes, names, key values) | Anywhere in the record | An FTS5 table filled on save |

Why a path index does not fit metadata: an index on an expression holds 1 value per row and 1 fixed path. The
metadata form differs per instrument (exaSPIM's key field is `subject_id`; another form may use `slide_id` or have no
key), and 1 acquisition has several tasks, so several values. A side table holds field names as data and 1 row per
task, so it works for any form.

References: [indexes on expressions](https://www.sqlite.org/expridx.html),
[JSON functions](https://www.sqlite.org/json1.html), [generated columns](https://www.sqlite.org/gencol.html),
[FTS5](https://www.sqlite.org/fts5.html).

## Open

- The full public schema of `acquisition.json`: versioned by `schema`, a new major version for a breaking change.
- Presets are left out: the default state covers 1 saved setup; named setups, if labs need them, go as files in the
  instrument folder, not in the records.
