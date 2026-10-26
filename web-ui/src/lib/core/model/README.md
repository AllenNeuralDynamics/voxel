# Application model

The data and models of the station: discovery, the connection, the open instrument, its devices and its commands. It
has no UI. It reports errors through `reportFailure` in [`core/failures.ts`](../failures.ts).

## Commands

A command goes to the backend in 1 of 2 ways. The backend runs 1 command at a time, in the order they arrive.

- **Queue:** `instrument.edits.run` sends 1 command at a time, in order, and waits for each answer. If a command fails,
  the commands behind it are not sent. A control with `onEditStart={instrument.edits.hold}` holds the queue while you
  edit it, so undo is off until the edit ends. A hold sends nothing.
- **Direct:** the command goes at once. It can pass commands that still wait in the queue.

### Rules

1. A command that changes or reads the saved state goes through the queue, so it sees every edit made before it: the
   profile, channel, output, metadata, routing rule and task edits, undo and redo, a profile switch, restore default,
   apply preset, Start, save preset, "Restore all" and "Back to rule".
2. A command that only drives the hardware goes direct: `selectRoute`, the preview channels, preview start and stop,
   the viewport message, stage and wheel moves, the laser commands and the commands on the device page.
3. Stop and halt always go direct.

### Exceptions

`setProps`, the camera ROI and `updateSignals` drive the hardware and also save in the profile. They go direct: they
must go at once, they build on no other edit, and undo does not touch them. In the queue, a failed edit would drop a
laser change behind it, and undo would turn off during each slider drag.

`launch`, `close`, `archiveState` and the presets of a saved run use the station's own busy flag. `close` first waits
for the queue of the instrument, so no edit is lost. Reads and feeds change nothing, so they go direct.

## Presets

A preset holds the protocol, not the whole app.

| Group      | Holds                                                                       | In a preset |
| ---------- | --------------------------------------------------------------------------- | ----------- |
| Instrument | Devices and calibration, from `config.yaml`                                 | No          |
| Protocol   | Channels, profiles, signals, routing, output format, required sample fields | Yes         |
| Session    | Tasks, sample values and the destination                                    | No          |

### Rules

1. Apply never touches the tasks or the sample values. A preset holds tasks only when "Include tasks" is on, and then
   apply asks before it replaces them.
2. Calibration stays with the instrument, so an old preset cannot bring back old values.
3. Each run saves a full copy of its settings, so History proves what a run used. Presets need no versions or locks,
   and a preset can be updated in place.
4. A preset is never edited in a form. You change the working settings, then save them to a preset.
5. "Instrument default" is a preset from `config.yaml`. It cannot be changed or deleted, and "Restore default" is a
   normal apply.
6. Apply stores the preset ID as `from_preset`. The app compares the protocol with that preset to show "matches" or
   "edited". There is no change counter. Each run saves `from_preset` and whether the settings were edited.
7. Apply first shows the changes. It stops if the preset uses a device the instrument no longer has, it is 1 undo
   step, and it is not possible during an acquisition.
8. A preset has a name and a note. The list also shows its channels, its profiles and when it was last updated.

### Where presets show

- Presets page: the list, the settings of a preset and its changes from now, apply, rename, note and delete.
- Run page: "Preset: X" with an "edited" tag. The tag opens the changes, apply again and update.
- History run page: "Save as preset" and "Use these settings".

### Decisions

- Left out: versions, change counters, presets that hold part of the protocol, and editing a preset without applying it.
- The routes are `presets/` and `presets/[presetId]`. The ID `default` opens the default. Saved presets have UUIDs.
- The Config page shows only `config.yaml` and `state.json`, and it links to the default preset on the Presets page.
