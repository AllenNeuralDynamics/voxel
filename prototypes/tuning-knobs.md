# Tuning knobs

Discussed on 2026-11-19 and 2026-11-20. **The backend is built** (2026-11-20; see "What is built"). The UI is
prototyped in the Lab (`Voxel Station Prototype`) and is not in the app yet. Earlier source: the "Tweaks" section of
the Voxel Signals Prototype artifact.

## What a knob is

A tuning knob puts 1 number of a profile's timeline in the Live profile panel, under a name, so a person can tune it
during preview. Examples: the camera trigger's start offset ("Camera delay") and the left lens's wave center ("Sheet
focus").

Only timelines need knobs. Every other part of a profile already has a Live panel control: `power` (power sliders),
`props` (exposure, focus positions) and `positions` (filter wheels, selectors). A timeline has dozens of numbers and a
person tunes 2 or 3, so someone has to pick which ones show.

## Decisions

- **Each profile owns its knobs.** Profiles can give the same wire different signal kinds (a wave in one, a constant
  in another), so a knob is tied to 1 profile's signal. Copying a profile copies its knobs.
- **They are a separate list in the profile**, not a field inside each signal. The timeline stays what the generator
  plays; the knobs say how a person tunes it.
- **They live in the profile files:** default.yaml for the knobs an instrument ships with, state.json for the ones
  people add. Not in rig.yaml.
- **Field name: `tuning_knobs`.** Plain `knobs` could be read as a physical knob on a device.
- **A knob holds only what to show and its name:**

  ```yaml
  tuning_knobs:
    - {label: Sheet focus,  generator: ao_main, wire: lens_left,      field: center}
    - {label: Camera delay, generator: ao_main, wire: camera_trigger, field: start}
  ```

  `field` is 1 of `start`, `end`, `delay`, `phase`, `cycles`, `split`, `scale`, `value`, `idle`, `active`, `first`,
  `last`, `center`, `amplitude`, `offset` (the type `TuningField`). `start` and `end` mean that edge's offset, the only
  number an edge has (its reference is a choice). Points and correction rows cannot be named this way, so they cannot
  have knobs.
- **No stored bounds or step.** The system already has the real limits, so both are worked out from existing facts
  (see "Bounds and step").
- **The control is a ruler**, not a full slider (see "The ruler"). A full slider stays for values whose whole range
  means something (power, exposure); the ruler is for small moves inside a large range (focus positions, timeline
  offsets, a sheet-focus voltage).
- **A change is sent on release** (or Enter in the box). The wheel has no release, so a short pause counts as 1. Each
  turn loads the generator (see "Locking"), so sending every small move would reload it many times a second.
- **Live panel section: "Tuning"**, the same word as the config field. "Timing" was dropped: some knobs are levels
  (volts), not times. UI words: "Add knob", "Edit knob", "Remove knob"; the star on a Timing panel row says "Add to
  the Live panel" or "Edit the knob".
- **A turn names the number it turns** (`generator`, `wire`, `field`), not the knob's place in the list. Adding,
  removing or undoing a knob then cannot make a turn hit the wrong number, and 2 knobs on the same number turn it alike.
- **The unit of a turn's value is fixed by the field**, never by the file, as `set_power` takes "the device's own
  unit": times (`start`, `end`, `delay`) in ms, levels in the wire's unit, `phase` in degrees, a follow's `offset` in
  volts, and `cycles`, `split` and `scale` with none. A file may write the same time as "250 us" or "0.25 ms", so "the
  unit the file uses" would let a client be 1000 times off. The save converts the value back to the unit the file
  used, so the file stays as it was written.
- **No knob view.** The value is in the view's `state` already, the turn keeps the bounds and step, and whether a knob
  works is its warning, shown with the alerts (see "Mistakes").

## The ruler

The control's look, input and motion are in `notes/web-ui/ruler.md`: a needle fixed at the center over moving ticks,
the value snaps to steps, a drag sends on release, Alt + wheel and the arrow keys send after a 0.4 s pause, and a plain
wheel scrolls the panel. Ticks sit only on steps ("positions the value can never stop at" are rejected), and the Boxed
look hatches past the range, so **the UI needs each knob's exact step and its range.**

- **For now the UI works them out itself**, from the state (the timeline), the config (wire units, limits, scales)
  and the generator's `voltage_range` device property. The Lab's `knobOf` copies the backend's rules, with its own
  ports of edge placement, PCHIP interpolation and `render()`.
- **The backend stays the authority.** `set_tuning_knob` keeps the value inside the bounds and on the step and returns
  the value it applied; the ruler glides onto that value. A slip in the UI copy cannot reach the hardware.
- **1 turn in flight.** Turns queue behind the scheduler's lock, so the screen sends a turn, waits for its answer, then
  sends only the latest value, never a queue of old ones.

## Bounds and step

`samples.tune` works these out (in `_tuning_bounds`), in the field's fixed unit.

| Field | Bounds | Step |
|---|---|---|
| Levels (`value`, `idle`, `active`, `first`, `last`, `center`) | the wire's limits in the highest unit that has them, or the generator's `voltage_range`, carried up to the wire's unit through its scale tables read backward | a power of 10 near 1/1000 of the range |
| `amplitude` | 0 to half the level range: a negative amplitude only flips the wave, as `phase` does | as levels |
| `start`, `end` | the edge stays between 0 and the timeline's duration; an edge that counts from another signal's edge uses that edge's resolved time | 1 sample |
| `delay` (follow) | ± the duration (the copy wraps around) | 1 sample |
| follow `offset`, `scale` | what keeps the copied volts, from the rendered source, inside the wire's V limits (or the generator's range); refused when no value does | a power of 10 near 1/1000 of the range; none when the range has no end |
| `split` | 0 to 1 | 0.001 |
| `phase` | 0 to 360° | 0.1° |
| `cycles` | 1 step to half the samples in the signal's own window | a power of 10 near 1/1000 of the range |

- Turning 1 edge checks only that edge's bounds. An edge that depends on it and so leaves the timeline is caught by
  the profile check, which refuses the turn.
- A saved value is rounded to 12 significant digits, so 3 steps of 0.1 are saved as `0.3`, not
  `0.30000000000000004`.
- The number box always takes an exact value. A level step could later snap to the card's voltage resolution, as
  times snap to samples; the generator does not report its resolution today.

## Mistakes

- **Never drop a knob.** Dropping it on load would erase it from state.json on the next save, with no trace.
- **Shape mistakes are refused**, like any other bad field: an empty or blank label, an unknown `field`.
- **Fit mistakes are warning-level problems that keep the knob** and never block an edit: the generator has no
  timeline in the profile, the wire has no signal, the signal's kind has no such field, 2 knobs on the same number.
  Codes: `profile.tuning_knob.no_timeline`, `.no_signal`, `.no_field`, `.duplicate`, each at the knob's `loc`, such as
  `("profiles", "round_1", "tuning_knobs", 0)`. Blocking would refuse unrelated edits: changing `lens_left` from a wave
  to a constant must not be refused because of a knob on `center`.
- **Warnings refuse nothing.** `Problem.level` is "error" (the default) or "warning"; refusing checks use
  `problems.errors()`, and `Problems.raise_if_any` raises only errors (built in `e2e51537`). Rejected: a separate
  `Caution` type ("Caution" is a severity word in ANSI Z535 and FAA alerting, and a laser-label word in a lab), and
  `Warning` (ruff `A001`, a Python builtin).
- **Showing the warnings waits for the alerts** (`TODO.md`, "Alerts in the core"). Until then `Profile.problems` returns
  them and nothing shows them. With the alerts, the view gets the 2 "wrong now" lists side by side: `alerts` (live
  `Alert`s, which end by themselves) and the saved state's warning-level `Problem`s (which last until an edit). Both
  are `Issue`s, so a screen draws them alike, and a knob row finds its own warning by its `loc` ("Not available" with
  the reason). A warning in saved data is never an `Alert`, and live state is never a `Problem`.

## Undo

No save that changes a device is undoable. They write to the store directly, and their docstrings say "A save cannot
be undone": `set_device_properties`, the power edits, `set_generator_timeline`, the camera region, and
`set_tuning_knob`. Pure data edits go through `_state_edit` and are undoable (profile fields, tasks, position rules, the
metadata form, restoring defaults, writer settings). This keeps Undo's rule, "No device changes", from leaving a device
out of step with the state.

Knob turns follow the other live changes and are not undoable, for now. Undo of live changes is 1 later decision for
all of them. If turns become undoable, `_state_edit(…, edit_id=<knob>)` already merges a run of turns on the same knob
into 1 step, and `apply_profile` puts the devices back in step after an undo.

Adding, editing and removing knobs goes through `update_profile`, so it is undoable like other profile fields.

## Locking

A turn requires the generator, the store and the active profile, as `set_generator_timeline` does
(`rigup/src/rigup/activity.py`: an operation restarts every activity that holds 1 of its resources, or is refused when
that activity cannot restart).

- **During a run, a turn is refused.** The acquisition holds the store, the active profile and every device, with no
  restart, so the scheduler raises `ActivityBusyError`.
- **During a preview, the preview restarts around each turn:** lights off, generators and cameras stop, the timeline
  loads, then the cameras start new live streams, the lights come on and the generators start. Kept on purpose for
  now. The generator could swap the cycle by itself (`GeneratorController.load` stops, re-arms and starts it), but
  while it swaps "each pin keeps its last value" (`Generator.stop`), so a laser or modulator it drives could stay lit
  with no blanking, and the galvos and lenses freeze.
- **Turns queue.** The scheduler runs 1 operation at a time; a second turn waits for the first.

Later, if a turn feels too slow on a real rig (measure first): darken the lights only around the swap and keep the
cameras streaming (needs a hook, since only SPIM's preview knows which lights it lit); or let a generator put its
outputs at rest before a swap (a change to the device contract); or a seamless swap of the buffer while it plays
(depends on the hardware).

## What is built

2026-11-20, in `src/vxl/instrument/` unless noted. Tests: `tests/station/test_tuning_knobs.py`.

| Part | Where |
|---|---|
| `TuningKnob` (`label`, `generator`, `wire`, `field`) and `Profile.tuning_knobs`, default empty | `state.py` |
| `tuning_knobs` in the base `ProfileFields`, so every kind's `update_profile` edits the list | `state.py` |
| The fit checks, as warning-level problems in `Profile.problems` | `state.py` |
| `TuningField`, the 15 field names | `signals.py` |
| `tune(timeline, wires, *, wire, field, value, volts) -> (timeline, applied)`: bounds and step (`_tuning_bounds`), the fit, and the write in the file's unit | `samples.py` |
| `set_tuning_knob(generator, wire, field, value) -> float`, route `@action(on="generators", key="generator", verb="set_tuning_knob")`: read the active timeline, `tune` it, load and save it with `_load_timeline(generator, timeline)`, return the value applied | `base.py` |
| `hal.signal_generator(device_id)` and `hal.area_camera(device_id)`: 1 handle by id, or `NotFoundError`; every lookup of 1 id uses them, loops use the maps | `hal.py`; callers in `base.py` and SPIM's `instrument.py` |

Why a turn method rather than clients calling `set_generator_timeline`: the bounds are worked out in the backend, so 1
method keeps them in 1 place for every caller (web, Qt, a script), and a client sends 1 number.

## Names

- Chosen: `tuning_knobs`, `TuningKnob`, `TuningField`, `tune`, `set_tuning_knob`, `hal.signal_generator`,
  `hal.area_camera`, `Problems.errors()`, the 4 warning codes.
- Rejected: `knobs` and `tuning` (for the field); a single `target` string (`ao_main.camera_trigger.start`) instead of
  flat `generator`, `wire`, `field` (flat lets a problem point at the exact part, as `SignalEdge`'s plain fields do);
  `turn_knob`; `get_signal_generator` (the HAL's `device()` has no `get_`); `Caution`, `Warning`.
- Slider ends, before stored bounds were dropped: `range`, `span`, `low`/`high`, `extent`, and for ± around the
  current value `plus_minus`, `either_side`, `half_width`, `delta`. Taken words: `margin` (a position rule's dead
  zone), `window` (a signal's start to end), `amplitude` (a wave's swing), `bounds`, `tolerance`.

## Tabled: a mark when the generator plays something else

Tabled on 2026-11-19. A knob row has nothing at its right: a turn is loaded at once, so a reading would repeat the
box. The useful fact is when the generator does not play the profile's value (a turn refused during a run, a failed
load). The row would then turn amber, as other rows that differ from their target.

The generator reports what it plays: `GeneratorController.loaded` streams the `Cycle`, which holds only volts for each
pin at each sample, not the timeline's numbers. 2 ways to know:

- **The instrument remembers the timeline it last loaded** for each generator, after each load that worked, and clears
  it when `loaded` becomes empty. A knob compares its number in the profile with the same number in that copy, so only
  that row turns amber. Cheap, and sound because only the instrument touches devices. The pick so far.
- **Compare cycles:** build the cycle from the profile and compare it with `loaded` (`load` already compares cycles).
  The generator's own word, but it says only that something on that generator differs, so every knob on it would turn
  amber; and building a cycle is heavy (about 925,000 numbers at 100 kHz), so it can run only when either side changes.

## Open questions

- If the ruler over the derived bounds proves too coarse, add 1 optional override (`extent`) for a narrower window.
- Undo of live changes as a whole (power, properties, camera region, timelines, knob turns).
- Whether the view says when devices differ from the profile, so the panel can offer Apply after an undo.
- A voltage-resolution fact on the generator, for level steps.
- The UI's copy of the bounds and step: keep it, or add a backend query (`tuning_range(generator, wire, field)`) so
  the rules live in 1 place.
- Negative wave amplitudes (to look into later). A knob on `amplitude` ranges from 0 to half the level range, but
  `AnalogWave.amplitude` still accepts a negative value with no problem reported, so turning a knob on such a wave
  snaps it to 0. Either refuse negative amplitudes in the model, or keep them and let the knob's range include them.

## Related findings from the Timing prototype

- The Lab ports `render()` from `src/vxl/instrument/samples.py` to JS. On the templates' timelines its volts
  and problem messages match the Python exactly.
- `Cycle.volts` sends a plain list of volts for each pin. At 100 kHz over 544 ms with 17 wires that is about 925,000
  numbers each time a profile loads.
- The new API has no digital `train` kind; skipped for now.
