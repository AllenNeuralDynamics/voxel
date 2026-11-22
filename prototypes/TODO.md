# To do

All pending work, with a link to the note that holds the detail. In no particular order. Updated on
2026-11-21.

## Acquisition and cameras

- **Dropped frames from the drivers** (`dropped-frames.md`): 1 rule for every driver (frames lost since the last
  `start()`), fix pco, ximea and Hamamatsu to it, then read it after each batch into the record.
- **Memory per camera** (`writer.md` › Memory per camera): memory per slot from the image and writer settings,
  checked at Start, with a warning under 2 slots. Seen on 2026-11-21: the simulated `z-step.yaml` with its own
  writer settings starts, makes a record, and fails at the first visit on a 16 GB laptop.
- **Writer leftovers** (`writer.md` › Open): name axis 0 truthfully (`scan`, not `z`); check napari and BigStitcher
  with 0.6 transforms; warn when a sweep's frame rate is above the rig's measured write rate.
- **Drop sums on `Visit` and `Acquisition`** (`records.md` › Dropped frames): only when a reader needs them.

## Drivers on real hardware

- **ASI Tiger linear axis:** the 6 checks in `drivers/README.md` › "ASI Tiger linear axis: checks on the real stage".
- **Micronix MMC-100 linear axis:** a first run on a real controller (moves, limits, faults, homing, and the step
  of the position it reports: the driver guesses 1 encoder count).

## Alerts in the core

`Issue`, `Problem` and `Alert` are defined in `vxlib.issues`.

Built on 2026-11-20, in `src/vxl/instrument/base.py`, tested in `tests/station/test_base.py`:

- **`alerts` in the view** (`instrument.alerts`): a `Computed` over cached state, with `since` kept for the same code
  and `loc`. `Instrument._live_issues()` gives what is wrong now; a kind adds its own with `super()`.
- **`device.inconsistent_with_profile`**, a warning for each value at `("devices", <id>, "props", <name>)`: each
  property and position that the active profile sets against the value the device last reported. A number differs
  by more than half of the property's step. The position of an axis with named slots is compared by its label.
- **`operation` in the view** (`instrument.operation`): the name of the operation that runs now, from the new
  `ActivityScheduler.operation` in rigup. The alerts stay as they were while an operation runs, so a profile apply
  shows no false alert. A screen can show it ("Apply the profile…"), for operations that last longer than about 0.3 s.
- **`save_to_profile(device_id, properties)`**: the profile takes the device's last value; 1 edit, can be undone.
  **`restore_from_profile(device_id, properties)`**: the device takes the profile's value; cannot be undone.

Not built yet:

1. **More of `device.inconsistent_with_profile`:** laser power (it depends on the power mode and a router's position;
   with brightness by DAQ voltage the laser's setpoint says nothing) and timelines (the generator reports volts only,
   see `tuning-knobs.md` › Tabled). The devices that follow the stage are left out on purpose: they move only on a
   profile apply or a run.
2. **Check the MMC axis' position step on a real controller.** A continuous axis reports the step of its `position`
   (`_get_position_step`, 2026-11-20): the Tiger axis gives 0.1 µm, so a profile position within half of it is the
   same place. The MMC driver gives 1 encoder count (`ENC?`, µm per count, read when it opens). That is a guess: its
   `position` is the controller's theoretical position, whose real step is not known, and an open-loop axis may differ.
3. **`camera.no_frames`,** with a watchdog: `LiveRelay` notes when each camera that has a stream last sent a frame; a
   small task keeps a set of stalled cameras (a `Cell`) as 1 more trigger for the alerts. 2 open points: only the
   kind knows that a preview runs (a camera keeps its stream after the preview stops), and the time limit must come
   from the frame period, not a fixed number. Build it here first, to see how much code it adds.
4. **In the app:** Restore and Save to profile on these rows, listed under Issues › Now (the Lab's "live changes"
   list), and the operation name in the diagnostics bar.

The app keeps its own request failures as a separate feature. See `feed.md` for how alerts reach a screen.

## Tuning knobs

- **The UI in the app** (`tuning-knobs.md`): the backend is built; the panel exists only in the Lab prototype.
- **Open questions** (`tuning-knobs.md` › Open questions), for example undo of live changes and negative amplitudes.

## Web layer

Built on 2026-11-20 and 21: the feed (messages, publisher, sockets, reader), the station service (topics, HTTP
operations, `StationService`), the server and `vxl station start`; all of it is in `src/vxl/web/`. Agreed in
`station.md`, `feed.md`, `server.md` and `lab.md`. Battle-tested on 2026-11-21 (`server.md` › Battle test). Left:

- **The new station web app**, built to the design of the Lab prototype,
  [Voxel Station Prototype](https://claude.ai/artifact/UzEN1tGhqsHrEzcZEgBXJA) (a private Claude artifact): the Run,
  History, Light, Timing, Profiles, Devices and Config pages, the Live profile panel and the stage view. It goes in
  `web/station`, which holds an empty app today.

- **The feed's written spec** (`feed.md`), next to the code, and a typed view on the reader's side.
- **The generator's `loaded` property** (`feed.md` › Device topics): about 460 kB on the feed each time a cycle
  loads. A candidate for bytes, or for a cycle that is not a property.
- **The 2 HTTP rules that are not built** (`interface.md` › HTTP rules): `202` with a `Location` for an action that
  starts an activity (`POST /acquisition:start` answers `200` with the id), and the merge of a PATCH in the HTTP
  layer. Also the open points (`interface.md` › Open).
- **The server's leftovers** (`server.md` › As built): a window that subscribes to only some topics, the cap on the
  process, the public read schema of the records, frames read only while a window watches, and a release step that
  builds the web app before the wheel.
- **Children that outlive the station** (`orphans.md`): researched and prototyped; picks made, not built. Left:
  the flag's name, 1 run on Windows, and a go for the changes in `rigup/` and `omezarr/`.
- **A setting for the station's local port** (`station.md` › Open), and a way to create an instrument folder from a
  template without Python (`Station.create_instrument` has no command and no route).
- **`vxl station info`** (`station.md` › The CLI around it): shows the station's id, name, folder, instruments and
  storage.
- **History listing** (`records.md` › Listing and filters): the server's list with its filters is built; an index
  on `instrument, created_at_us` is not.
- **The lab** (`lab.md`): `vxl lab start`, `lab.yaml`, lab topics, the lab page; later the token, login and the Zarr
  viewer.
- **The public schema of `acquisition.json`** (`records.md` › Open), which the server and outside readers use.
- **Measure the local server hop again** when the real feed exists (`server.md` › Measured).
- **What the battle test did not cover** (`server.md` › Battle test): a client that disappears without a close, many
  readers at once, a slow reader with frames of several MB, a bad `server:` section, `--headless`.

## Found in the battle test

2026-11-21, in the core, through the HTTP routes. Fixed on that day: a bad position rule (`set_position_rule` now
runs the open's check while the instrument is open), and the `500` answers for ordinary bad input
(`server.md` › Battle test). Left:

- **A failure of a device during a move answers `500` with an `ExceptionGroup`** (`gather_all`). It is a real
  failure, but the answer names no device.
- **A number that is not finite is accepted in state fields** by a Python caller. The HTTP layer refuses it in a
  body, and the feed sends `null` for it.
- **`Station.close()` can raise `BusyError`** when an operation still holds the instrument. Seen once, not
  confirmed.
- **The simulated `z-step.yaml` cannot acquire with its own writer settings** on a 16 GB laptop (Acquisition and
  cameras › Memory per camera). With `batch_frames: 2` and `max_level: 1` it completes.

## Metadata UI

- **The Task card and the History Tasks tab** (`metadata.md`), and its 4 open questions, for example a `/` in key
  values.
- **The rest of its backend** (`metadata.md` › Backend changes needed, To decide): the lock of
  provenance fields after a run, which needs a design first. Built:
  the nested exaSPIM models, `key()`, `key_field()`, `required()` with its check at Start, the deep merge of a metadata edit, and `metadata_schema` in the view.
- **`Instrument.interface` has no path to a window** (the instrument's operations and the view's schema). It is fixed
  for the session, so it can be a topic sent only in a full message, as `instrument.config`.
