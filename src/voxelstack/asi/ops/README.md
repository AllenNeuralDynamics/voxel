# Operations, Parser and Models overview

---

## Operations

### MotionOP

| Op        | Verb | Input              | Example                      | Reply          | Output            | Notes                |
| --------- | ---- | ------------------ | ---------------------------- | -------------- | ----------------- | ---------------------|
| `Where`   | `W`  | `Axes`             | `W X Z\r`                    | `X=10.0 Z=5.0` | `dict[str,float]` | Maps values to axes; |
| `MoveAbs` | `M`  | `dict[axis,float]` | `M X=1.000000 Y=2.500000\r`  | `:A`           | `None`            | Absolute move.       |
| `MoveRel` | `R`  | `dict[axis,float]` | `R X=0.010000 Z=-0.050000\r` | `:A`           | `None`            | Relative move.       |
| `Here`    | `H`  | `dict[axis,float]` | `H X=0.0 Y=0.0\r`            | `:A`           | `None`            | Reset logical origin.|
| `Home`    | `!`  | `Axes`             | `! X Y\r`                    | `:A`           | `None`            | Start homing.        |
| `Halt`    | `\\` | none               | `\\\r`                       | `:A`           | `None`            | Immediate stop.      |

Errors always raise `ASIDecodeError("<OP>", reply)`.

### ParamOP

Param operations take a `TigerParam` spec (verb, type converter).

#### Common Parameters

```python
SPEED        verb=S    float   # mm/s
ACCEL        verb=AC   int     # ms or steps/s^2
BACKLASH     verb=B    float
HOME_POS     verb=HM   float
LIMIT_LOW    verb=SL   float
LIMIT_HIGH   verb=SU   float
JOYSTICK_MAP verb=J    int
CONTROL_MODE verb=PM   str
ENCODER_CNTS verb=CNTS float
AXIS_ID      verb=Z2B  int
PID_P        verb=KP   float
PID_I        verb=KI   float
PID_D        verb=KD   float
HOME_SPEED   verb=HS   float
```

#### Get

| Op            | Verb           | Input                | Example     | Reply         | Output        |
| ------------- | -------------- | -------------------- | ----------- | ------------- | ------------- |
| `ParamOP.Get` | `<verb>` + `?` | `(TigerParam, Axes)` | `S X? Y?\r` | `X=5.5 Y=6.0` | `dict[str,T]` |

#### Set

| Op            | Verb             | Input                       | Example           | Reply | Output |
| ------------- | ---------------- | --------------------------- | ----------------- | ----- | ------ |
| `ParamOP.Set` | `<verb>` + `K=V` | `(TigerParam, dict[str,T])` | `S X=5.5 Y=6.0\r` | `:A`  | `None` |

### StatusOP

| Op            | Verb       | Input            | Example         | Reply        | Output            | Notes                                            |
| ------------- | ---------- | ---------------- | --------------- | ------------ | ----------------- | -------------------------------------------------|
| `Busy`        | `/`        | none             | `/\r`           | `B` / `N`    | `bool`            | Motion state.                                    |
| `Who`         | `N`        | none             | `N\r`           | roster text  | `str`             | Use `ASIBoxInfo` to parse cards/axes.            |
| `Version`     | `V`        | none             | `V\r`           | version text | `str`             | Unaddressed version query.                       |
| `VersionAddr` | `<addr>V`  | `addr`           | `31V\r`         | version text | `str`             | Card-addressed version query.                    |
| `SetMode`     | `VB`       | \`ASIMode        | bool\`          | `VB F=1\r`   | `:A`              | `None` `True/TIGER → F=1`, `False/MS2000 → F=0`. |
| `SetModeAddr` | `<addr>VB` | `(addr,ASIMode)` | `31VB F=1\r`    | `:A`         | `None`            | Addressed variant for some firmwares.            |
| `Rdstat`      | `RS`       | `Axes`           | `RS X? Y? Z?\r` | `BNN`        | `dict[str,bool]`  | `B`=moving, `N`=not moving.                      |

---

## Parser

* `asi_parse(raw, requested_axes=None)` returns `(Reply, ASIMode)`
* Handles Tiger vs. MS2000 framing automatically.
* Filters key–value replies to requested axes when provided.

---

## Models

* `ASIBoxInfo(who_text)` → card roster with:

  * `.comm_addr` (int | None)
  * `.axes_flat` (`set[str]`)
  * `.axes_by_card` (`dict[int,set[str]]`)
  * `.cards` (list of `CardInfo`)

Pretty-printed `repr` helps with logging/debug.

### TTLMode

What each TTL field means (from ChatGPT: confirm accuracy with ASI docs)

>⚠️ Reality check: exact meanings and enumerations vary by card & firmware. Think of the fields as “slots” that each card interprets. Always verify by round-tripping (SetModes → GetModes) and by watching behavior on the bench.

X — IN0 mode (input function / routing)

Selects how the primary TTL input is interpreted (e.g., rising/falling edge trigger, armed gating, start/stop of scan, enable/disable, etc.).

Numeric codes map to firmware-defined behaviors (which differ per card family).

Y — OUT0 mode (output function / routing)

Selects which event is driven onto the primary TTL output (e.g., “move done” pulse, scan line clock, exposure trigger, continuous high/low, etc.).

Again: card/firmware specific enumerations.

Z — AUX state / immediate latch

Often a direct “auxiliary” state (write Z=1 to force a line high, Z=0 low), or a small sub-mode latch. On some cards it’s read-only status; on others it’s writeable to poke the output.

F — Output polarity / inversion

Usually 0 = active-high, 1 = active-low (invert). Some cards treat this as a bitmask if multiple lines exist.

R — AUX mask / enable bits

Frequently a bitmask enabling which sub-sources/events feed the TTL logic (e.g., “OR of these axes,” “include scanner busy,” etc.). Values are card-specific.

T — AUX mode / timing parameter

Commonly a mode selector or timer (e.g., pulse width, debounce time, gating mode). Semantics vary widely by card.
