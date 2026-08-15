# vxl-records

`vxl-records` is the durable record boundary for Voxel. It stores revisioned
acquisition manifests, reusable instrument presets, and an ordered operational log journal behind focused
`AcquisitionCatalog`, `PresetCatalog`, and `LogJournal` APIs.

`SQLiteRecords` composes those APIs over one database; application code should depend on the `VoxelRecords`
protocol when it does not require SQLite-specific behavior. The initial implementation uses a local SQLite database. Acquisition-root
`manifest.json` files remain portable projections of the authoritative
relational acquisition record.

Existing file-backed acquisition history can be imported non-destructively with
`vxl station import-catalog`. The operation is transactional and safe to rerun;
legacy files remain available as a rollback source.

`LogJournal.capture()` installs a non-blocking root logging handler for an
explicit application-lifecycle context. Captured records pass through a bounded
queue to one SQLite writer, and subscribers receive only committed `LogEntry`
values. Queue overflow is represented by a durable warning entry.

Run `uv run pytest records/tests` from the workspace to validate changes.
