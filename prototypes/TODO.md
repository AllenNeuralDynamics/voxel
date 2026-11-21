# To do

All pending work, with a link to the note that holds the detail. In no particular order. Updated on
2026-11-20.

## Acquisition and cameras

- **Dropped frames from the drivers** (`dropped-frames.md`): 1 rule for every driver (frames lost since the last
  `start()`), fix pco, ximea and Hamamatsu to it, then read it after each batch into the record.
- **Memory per camera** (`writer.md` › Memory per camera): memory per slot from the image and writer settings,
  checked at Start, with a warning under 2 slots.
- **Writer leftovers** (`writer.md` › Open): name axis 0 truthfully (`scan`, not `z`); check napari and BigStitcher
  with 0.6 transforms; warn when a sweep's frame rate is above the rig's measured write rate.
- **Drop sums on `Visit` and `Acquisition`** (`records.md` › Dropped frames): only when a reader needs them.

## Drivers on real hardware

- **ASI Tiger linear axis:** the 6 checks in `drivers/README.md` › "ASI Tiger linear axis: checks on the real stage".
- **Micronix MMC-100 linear axis:** a first run on a real controller (moves, limits, faults, homing).

## Alerts in the core

`Issue`, `Problem` and `Alert` are defined in `vxlib.issues`. Not built yet:

1. **A watchdog prototype for "a camera stopped sending".** `LiveRelay` notes when each camera that has a stream last
   sent a frame; a small task keeps a set of stalled cameras (a `Cell`) that changes when a camera goes quiet for too
   long and when it sends again. That set is 1 more trigger for the alerts. Build it here first, to see how much code
   it adds, before anything goes into `src`.
2. **The first alerts.** A `Computed` of `Alert`s over cached state in the base `Instrument`, each check a small pure
   function, with `since` kept from the last result for the same code and `loc`. An instrument kind adds its own
   checks through a hook, as it adds view fields. Start with `camera.no_frames` (from the watchdog) and
   `device.inconsistent_with_profile` (named 2026-11-20): each device's live value against the active profile, for
   selectors, wheels, laser power, focus axes and camera settings. They go out as `instrument.alerts`. The app adds
   Restore to these rows and lists them under Issues › Now (the Lab's "live changes" list).

The app keeps its own request failures as a separate feature. See `feed.md` for how alerts reach a screen.

## Tuning knobs

- **The UI in the app** (`tuning-knobs.md`): the backend is built; the panel exists only in the Lab prototype.
- **Open questions** (`tuning-knobs.md` › Open questions), for example undo of live changes and negative amplitudes.

## Web layer

Not built. Agreed in `station.md`, `feed.md`, `gateway.md` and `lab.md`.

- **The new station web app**, built to the design of the Lab prototype,
  [Voxel Station Prototype](https://claude.ai/artifact/UzEN1tGhqsHrEzcZEgBXJA) (a private Claude artifact): the Run,
  History, Light, Timing, Profiles, Devices and Config pages, the Live profile panel and the stage view. Its folder in
  `web/` is still to be picked.

- **The feed** (`feed.md`): topics instead of whole views, global topic names with the publisher's prefix, 2 sockets
  per window, slow clients merged, never dropped.
- **The station API** (`interface.md`, `station.md`): FastAPI routes in `vxl.station.api`, following the HTTP rules
  in `interface.md`; decide its open points. Then delete the try-out in `prototypes/interface/`.
- **The gateway** (`gateway.md`): cache, fan-out, routing, records history, local `/data`, web app files; the
  written feed spec and black-box tests, so another gateway program can replace it.
- **`vxl station start`** (`station.md`): the station plus a supervised gateway; `--no-gateway`; the `gateway:`
  settings.
- **The lab** (`lab.md`): `vxl lab start`, `lab.yaml`, lab topics, the lab page; later the token, login and the Zarr
  viewer.
- **The public schema of `acquisition.json`** (`records.md` › Open), which the gateway and outside readers use.
- **Measure the local gateway hop again** when the real feed exists (`gateway.md` › Measured).

## Metadata UI

- **The Task card and the History Tasks tab** (`metadata.md`), and its 4 open questions, for example a `/` in key
  values.
