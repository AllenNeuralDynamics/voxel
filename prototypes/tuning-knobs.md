# Tuning knobs

Discussed on 2026-11-19. Nothing is decided and nothing is built in `src/`. The UI is prototyped in the Lab
(`Voxel Station Prototype`). Earlier source: the "Tweaks" section of the Voxel Signals Prototype artifact.

## What a knob is

A tuning knob puts 1 number of a profile's timeline in the Live profile panel, under a name, so a person can tune it
during preview. Examples: the camera trigger's start offset ("Camera delay") and the left lens's wave center ("Sheet
focus").

Only timelines need knobs. Every other part of a profile already has a Live panel control: `power` (power sliders),
`props` (exposure, focus positions) and `positions` (filter wheels, selectors). A timeline has dozens of numbers and a
person tunes 2 or 3, so someone has to pick which ones show.

## Picks so far

These are the current picks, open until decided.

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
  `last`, `center`, `amplitude`, `offset`. `start` and `end` mean that edge's offset, the only number an edge has (its
  reference is a choice). Points and correction rows cannot be named this way, so they cannot have knobs.
- **No stored bounds or step.** Both only made the slider comfortable, and the system already has the real limits. They
  are worked out from existing facts (see below).
- **The control is a ruler**, not a full slider: a fixed center line on the current value over a ruler of ticks that
  shows a small window around it. Dragging scrolls the ruler; it stops at the bounds, with the part past them hatched.
  The ruler follows the pointer (8 px for each step), Shift moves 10 steps at a time; the wheel and the arrow keys move 1 step; a number box takes an exact
  value. Three looks are under test in the Lab: Track (the slider's track through the middle, ticks on it, a needle
  fixed at the center, the reading as a fill on the track), Light (a needle fixed at the center with no track, sparse ticks that fade
  toward the ends, a cap at each end of the range, the reading as a filled track) and Boxed (a framed ruler with a
  tick every step and labels). A full slider stays for values whose whole range means something (power, exposure); the ruler is for small
  moves inside a large range (focus positions, timeline offsets, a sheet-focus voltage).
- **A change is sent on release** (or Enter in the box). The wheel has no release, so a short pause counts as 1.
  Loading a cycle into a running generator stops it, re-arms it and starts it again
  (`GeneratorController.load`), so sending every small move would restart it many times a second.
- **Live panel section: "Timing".** UI words: "Add knob", "Edit knob", "Remove knob"; the star on a Timing panel row
  says "Add to the Live panel" or "Edit the knob".

## Bounds and step, worked out

| Field | Bounds |
|---|---|
| Levels (`value`, `idle`, `active`, `first`, `last`, `center`, `amplitude`) | the wire's limits in its unit; with none (`limits` defaults to empty), the generator's `voltage_range` carried up through the wire's scales |
| `start`, `end` | the edge stays between 0 and the timeline's duration |
| `delay` (follow) | ± the duration (the copy wraps around) |
| follow `offset`, `scale` | what keeps the copied volts inside the wire's limits |
| `split` | 0 to 1 |
| `phase` | 0 to 360° |
| `cycles` | above 0, at most half the samples |

The step is 1 sample for times, and a round default (near 1/1000 of the bounds) for the rest. The number box always
takes an exact value. A level step could later snap to the card's voltage resolution, as times snap to samples; the
generator does not report its resolution today.

## Mistakes

- **Never drop a knob.** Dropping it on load would erase it from state.json on the next save, with no trace.
- **Shape mistakes are refused**, like any other bad field: an empty label, an unknown `field`.
- **Fit mistakes are cautions that keep the knob** and never block an edit: the generator has no timeline in the
  profile, the wire has no signal, the signal's kind has no such field, 2 knobs on the same number. The row says
  "Not available" with the reason; Diagnostics lists the caution. Blocking would refuse unrelated edits:
  `set_generator_timeline` refuses any timeline that leaves the profile with problems, so changing `lens_left` from a
  wave to a constant would be refused because of a knob on `center`.
- **This needs warnings in the problems system.** `Issue` has `level: "error" | "warning"`, but `Problem` is always an
  error and `Problems` holds only `Problem`. Pick: a separate `Caution` (an `Issue` with `level: "warning"`) and
  `Cautions` list, so every existing `if problems:` keeps meaning "refuse". `Warning` cannot be the name: ruff reports
  `A001` (it shadows a Python builtin). `Alert` does not fit: it is wrong in a running instrument and ends by itself
  when the state changes back, while a broken knob is wrong in data and lasts until someone edits it.

## Undo

Today no save that changes a device is undoable. They write to the store directly, and their docstrings say "A save
cannot be undone": `set_device_properties`, the power edits (`_edit_power`), `set_generator_timeline`, the camera
region. Pure data edits go through `_state_edit` and are undoable (profile fields, tasks, position rules, the metadata
form, restoring defaults, writer settings). This keeps Undo's rule, "No device changes", from leaving a device out of
step with the state.

Pick: **knob turns follow the other live changes and are not undoable, for now.** Undo of live changes is 1 later
decision for all of them. If turns become undoable, `_state_edit(…, edit_id=<knob>)` already merges a run of turns on
the same knob into 1 step, and `apply_profile` puts the devices back in step after an undo.

Adding, editing and removing knobs goes through `update_profile`, so it is undoable like other profile fields.

## Locking

A turn uses the same scheduler resources as `set_generator_timeline` (the generator, the store, the active profile).
`ActivityScheduler.run` raises `ActivityBusyError` when a running activity holds 1 of them and cannot restart, so a turn
is refused during a run, and a preview that can restart restarts around it. Not checked yet: that the acquisition lists
the generator among its resources.

## Backend additions

| # | Addition | Where |
|---|---|---|
| 1 | `Caution` and `Cautions` | `vxlib/src/vxlib/issues.py` |
| 2 | `TuningKnob` (`label`, `generator`, `wire`, `field`) | `src/vxl/station/instrument/state.py` |
| 3 | `Profile.tuning_knobs`, default empty | `state.py` |
| 4 | `tuning_knobs` in the base `ProfileFields`, so every kind's `update_profile` edits the list | `state.py` |
| 5 | `Profile.cautions(config)`: the fit checks above, apart from `Profile.problems` | `state.py` |
| 6 | Bounds and step helpers (scale tables read backward for levels; edge placement for times) | `signals.py`, `samples.py` |
| 7 | A knob view in the instrument view: each knob's current value, unit, bounds, step, and whether it is available. 1 field in `InstrumentView` and 1 line in `_view_sources`. | `base.py` |
| 8 | A turn method on the base instrument, such as `set_tuning_knob(index, value)`: change 1 number, run the profile checks, load the generator, save | `base.py` |

Why a turn method rather than clients calling `set_generator_timeline`: the bounds are worked out in the backend, so 1
method keeps them in 1 place for every caller (web, Qt, a script), and a client sends 1 number.

## Names considered

- `knobs`, `tuning`: `tuning_knobs` chosen (see above).
- A single `target` string (`ao_main.camera_trigger.start`) instead of flat `generator`, `wire`, `field`: flat chosen,
  so a problem points at the exact part and it matches `SignalEdge`'s plain fields.
- Slider ends, before they were dropped: `range`, `span`, `low`/`high`, `low_high`, `extent`; and for ± around the
  current value `plus_minus`, `either_side`, `half_width`, `delta`. Taken words: `margin` (a position rule's dead zone),
  `window` (a signal's start to end), `amplitude` (a wave's swing), `bounds`, `tolerance`. Dropped because both modes
  only declared limits, which the system already has.

## Open questions

- If the ruler over the derived bounds proves too coarse, add 1 optional override (`extent`) for a narrower window.
- Undo of live changes as a whole (power, properties, camera region, timelines, knob turns).
- Whether the view says when devices differ from the profile, so the panel can offer Apply after an undo.
- That the acquisition holds the generator, so turns are refused during a run.
- A voltage-resolution fact on the generator, for level steps.
- A default step for levels with no natural unit step.

## Related findings from the Timing prototype

- The Lab ports `render()` from `src/vxl/station/instrument/samples.py` to JS. On the templates' timelines its volts
  and problem messages match the Python exactly.
- `Cycle.volts` sends a plain list of volts for each pin. At 100 kHz over 544 ms with 17 wires that is about 925,000
  numbers each time a profile loads.
- The templates moved to `instruments/src/vxl_instruments/spim/templates/`. exaSPIM now gates an AOM after each laser
  on `aom_N/ttl_in`; `z-step-4-cameras.yaml` matches the Lab's exaSPIM Max.
- The new API has no digital `train` kind; skipped for now.
