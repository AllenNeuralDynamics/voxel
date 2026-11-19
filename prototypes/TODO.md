# To do

Work to remember, in no particular order.

## Alerts in the core

`Issue`, `Problem` and `Alert` are defined in `vxlib.issues`. Not built yet:

1. **A watchdog prototype for "a camera stopped sending".** The relay notes when each camera that has a stream last
   sent a frame; a small task keeps a set of stalled cameras (a `Cell`) that changes when a camera goes quiet for too
   long and when it sends again. That set is 1 more trigger for the alerts. Build it here first, to see how much code
   it adds, before anything goes into `src`.
2. **The first alerts.** A `Computed` of `Alert`s over cached state in the base `Instrument`, each check a small pure
   function, with `since` kept from the last result for the same code and `loc`. An instrument kind adds its own
   checks through a hook, as it adds view fields. Start with `camera.no_frames` (from the watchdog) and
   `router.not_at_profile` (each router's slot against the profile). They go out as `instrument.alerts`.

The app keeps its own request failures as a separate feature. See `feed.md` for how alerts reach a screen.

## Records rework

`vxl_records` (`records/src/vxl_records/`) is built for 1 setup: a stage stack along z, with 1 dataset per channel. It
likely needs a lot of rework before it can record runs on a wide range of setups (exaSPIM, open-top light sheet,
SeqSweep line scan, and later others). What ties it to 1 setup today:

- `PlannedVolume` has fixed axis fields: `x`, `y`, `z_start`, `z_step`, `z_end`. The scan axis is always z, and
  `frames_total` is worked out from z. The new SPIM `Volume` has `start: Vec3D`, `scan: AxisRun` (any axis),
  `positions` and `transforms`.
- `routes: dict[str, str]` holds the old route names. The new core has router positions.
- `datasets` is keyed by `ChannelName`. A channel now holds many cameras, so 1 key per channel is not enough.
- A run is a list of volumes. A line scan run (SeqSweep) may not be made of volumes.
- `state_snapshot` and `hardware_snapshot` are untyped dicts.

The lifecycle (create, start, the steps for each volume, then complete, cancel or fail), the datasets, the locations,
the storage and the log window look general and can likely stay. Design the rework before the SPIM capture writes
records, or let the capture write a small SPIM-shaped record first and rework it later.
