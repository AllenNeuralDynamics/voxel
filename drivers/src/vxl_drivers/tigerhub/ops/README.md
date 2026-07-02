# Tiger serial protocol reference

The operations, parser, and models that make up the ASI Tiger / MS2000 serial command layer used by the ASI drivers (`vxl_drivers.axes`). `TigerHub` and `TigerBox` drive these operations; this document is the wire-level reference behind them.

## Common shape

Each operation is a small class in [`ops/`](.) with two halves:

- `encode(...) -> bytes` — builds the ASCII command line to send.
- `decode(reply: Reply) -> T` — turns the controller's parsed reply into a typed result (`None` for commands with no return value).

Command lines are assembled by helpers in [`../protocol/linefmt.py`](../protocol/linefmt.py): `_line(verb, payload=None, addr=None)` joins the verb, an optional payload, and an optional card address, terminating with `\r`. When an operation targets a specific card, its hex address is prepended to the verb (e.g. `V` → `31V`).

Replies are parsed by `asi_parse` (see [Parser](#parser)) into a `Reply`. Operations that detect an error reply raise `ASIDecodeError(operation, reply)` from [`../protocol/errors.py`](../protocol/errors.py). Read-only queries that parse free-form text (`GetWhoOp`, `GetVersionOp`, `GetAxisStateOp`, `GetBuildOp`, `GetCardMods`) return parsed objects or empty defaults instead of raising.

## Motion — [`motion.py`](motion.py)

| Op | Verb | Input | Example command | Output |
|----|------|-------|-----------------|--------|
| `WhereOp` | `W` | axes | `W X Y\r` | `dict[str, float]` |
| `MoveAbsOp` | `M` | `Mapping[axis, float]` | `M X=1.000000 Y=2.500000\r` | `None` |
| `MoveRelOp` | `R` | `Mapping[axis, float]` | `R X=0.010000\r` | `None` |
| `HereOp` | `H` | `Mapping[axis, float]` | `H X=0.000000\r` | `None` |
| `HomeOp` | `!` | axes | `! X Y\r` | `None` |
| `HaltOp` | `\` | none | `\\r` | `None` |
| `IsAxisBusyOp` | `RS` | axes | `RS X? Y?\r` | `dict[str, bool]` (`B` → moving, `N` → idle) |

Position values are formatted to six decimal places. Each op raises `ASIDecodeError` (with a name such as `"WHERE"`, `"MOVE_ABS"`, `"RDSTAT"`) on an error reply.

## Parameters — [`params.py`](params.py)

Parameter access is generic over a `TigerParam` spec:

```python
@dataclass(frozen=True)
class TigerParam[T: (int | float | str | bool)]:
    name: str        # "SPEED"
    verb: str        # "S"
    typ: Callable[[str], T]  # converter applied to each reply value
    per_axis: bool = True
```

| Op | Command form | Input | Example | Output |
|----|--------------|-------|---------|--------|
| `GetParamOp` | `<verb> <axis>?…` | `(TigerParam, axes)` | `S X? Y?\r` | `dict[str, T]` |
| `SetParamOp` | `<verb> <axis>=<value>…` | `(TigerParam, Mapping[axis, T])` | `S X=5.5 Y=6.0\r` | `None` |

Both raise `ASIDecodeError(f"GET {verb}" / f"SET {verb}", reply)` on an error reply.

The `TigerParams` registry defines the known parameters:

| Name | Verb | Type | Name | Verb | Type |
|------|------|------|------|------|------|
| `SPEED` | `S` | float | `CONTROL_MODE` | `PM` | str |
| `ACCEL` | `AC` | int | `ENCODER_CNTS` | `CNTS` | float |
| `BACKLASH` | `B` | float | `AXIS_ID` | `Z2B` | int |
| `HOME_POS` | `HM` | float | `PID_P` | `KP` | float |
| `LIMIT_LOW` | `SL` | float | `PID_I` | `KI` | float |
| `LIMIT_HIGH` | `SU` | float | `PID_D` | `KD` | float |
| `JOYSTICK_MAP` | `J` | int | `HOME_SPEED` | `HS` | float |

## Status — [`status.py`](status.py)

| Op | Verb | Input | Output | Errors |
|----|------|-------|--------|--------|
| `GetWhoOp` | `N` | none | `list[WhoReportItem]` | returns `[]` on empty |
| `IsBoxBusyOp` | `/` | none | `bool` (`B` → busy) | raises `ASIDecodeError("STATUS")` |
| `GetVersionOp` | `V` | addr? | `str` | returns reply text |
| `SetModeOp` | `VB` | `(ASIMode, addr?)` | `None` | raises `ASIDecodeError("VB")` |
| `GetAxisStateOp` | `INFO` | axis | `AxisState` | delegates to `AxisState.from_reply` |
| `GetPiezoInfoOp` | `PZINFO` | addr | `str` | returns reply text |
| `GetBuildOp` | `BU X` | addr? | `BuildReport` | delegates to `BuildReport.from_reply` |
| `GetCardMods` | `BU X` | addr? | `set[str]` | returns parsed module names |

`SetModeOp` sends `VB F=1` for Tiger mode and `VB F=0` for MS2000.

## Scan — [`scan.py`](scan.py)

| Op | Verb | Input | Output |
|----|------|-------|--------|
| `ScanBindAxesOp` | `SCAN` | `(card, fast_axis_id, slow_axis_id, pattern)` | `None` |
| `ScanROp` | `SCANR` | `(card, ScanRConfig)` | `None` |
| `ScanVOp` | `SCANV` | `(card, ScanVConfig)` | `None` |
| `ScanRunOp` | `SCAN` | `(card, "S"` start `/ "P"` stop`)` | `None` |
| `ArrayOp` | `AR` | `(card, ArrayScanConfig?)` | `None` |
| `AutoHomeOp` | `AH` | `(card, AutoHomeConfig)` | `None` |

All scan ops are card-addressed and raise `ASIDecodeError` on an error reply. The `SCANR` / `SCANV` key/value fields are built by `ScanRConfig.to_kv()` / `ScanVConfig.to_kv()`:

- **`SCANR`** (fast axis): `X` start [mm], `Y` stop [mm] (distance mode), `Z` encoder ticks between pulses, `F` pixel count (pixel-count mode), `R` retrace speed [%].
- **`SCANV`** (slow axis): `X` start [mm], `Y` stop [mm], `Z` number of lines, `F` extra settle time [ms], `T` overshoot factor.

## Step-and-shoot and TTL — [`step_shoot.py`](step_shoot.py)

| Op | Verb | Input | Output |
|----|------|-------|--------|
| `SetRingBufferModeOp` | `RM` | `(addr?, clear_buffer, enabled_mask, mode)` | `None` |
| `LoadBufferedMoveOp` | `LD` | `(addr?, Mapping[axis, float])` | `None` |
| `SetTTLModesOp` | `TTL` | `(addr?, TTLConfig)` | `None` |
| `GetTTLModesOp` | `TTL` | addr | `TTLConfig` |
| `ProbeTTLOutOp` | `TTL O?` | addr | `bool` |
| `ProbeTTLOutOp2` | `TTL` | addr? | `bool` (legacy fallback) |

### TTL configuration

`TTLConfig` is the same object for SET (`to_kv`) and GET (`from_reply`). Each field maps to one TTL key:

| Field | Key | Type | Meaning |
|-------|-----|------|---------|
| `in0_mode` | `X` | `TTLIn0Mode \| int` | IN0 input function |
| `out0_mode` | `Y` | `TTLOut0Mode \| int` | OUT0 output function |
| `aux_state` | `Z` | int | Auxiliary state / immediate latch |
| `out_polarity_inverted` | `F` | bool | Output polarity — encoded `-1` if inverted, else `1` |
| `aux_mask` | `R` | int | Auxiliary mask / enable bits |
| `aux_mode` | `T` | int | Auxiliary mode / timing parameter |

`X` and `Y` have named enums; `Z`, `R`, and `T` are passed through as raw integers because their meaning is card- and firmware-specific.

```python
class RingBufferMode(Enum):
    TTL = 0; ONE_SHOT = 1; REPEATING = 2

class TTLIn0Mode(Enum):
    OFF = 0
    MOVE_TO_NEXT_ABS_POSITION = 1
    REPEAT_LAST_REL_MOVE = 2
    AUTOFOCUS = 3
    ZSTACK_ENABLE = 4
    POSITION_REPORTING = 5
    INTERRUPT_ENABLED = 6
    ARRAY_MODE_MOVE_TO_NEXT_POSITION = 7
    IN0_LOCK_TOGGLE = 9
    OUT0_TOGGLE_STATE = 10
    SERVOLOCK_MODE = 11
    MOVE_TO_NEXT_REL_POSITION = 12
    SINGLE_AXIS_FUNCTION = 30

class TTLOut0Mode(Enum):
    ALWAYS_LOW = 0; ALWAYS_HIGH = 1; PULSE_AFTER_MOVING = 2
```

## Card — [`card.py`](card.py)

| Op | Verb | Input | Output |
|----|------|-------|--------|
| `CardAssistOp` | `CCA` | `(addr?, dict[str, Any])` | `None` |

## Joystick — [`joystick.py`](joystick.py)

| Op | Command form | Input | Output |
|----|--------------|-------|--------|
| `JoystickSetMappingOp` | `J X=2 Y=3…` | `(card, Mapping[axis, JoystickInput])` | `None` |
| `JoystickGetMappingOp` | `J X? Y?…` | `(card, axes)` | `dict[str, JoystickInput]` |
| `JoystickEnableOp` | `J X+ Y-…` | `(card, enable_axes, disable_axes)` | `None` |
| `JoystickPolarityOp` | `CCA Z=<code>` | `(card, axis_index, inverted)` | `None` |

Joystick inputs are selected from the `JoystickInput` enum (`NONE=0`, `DEFAULT=1`, `JOYSTICK_X=2`, `JOYSTICK_Y=3`, `CONTROL_KNOB=4`, wheels, `FOOTSWITCH=8`, `Z_WHEEL=22`, `F_WHEEL=23`, …). `JoystickPolarityOp` maps to a `CCA Z` code: `22 + axis_index * 2`, plus one when not inverted.

## Parser — [`../protocol/parser.py`](../protocol/parser.py)

```python
def asi_parse(raw: bytes, requested_axes: list[str] | None = None) -> tuple[Reply, ASIMode]
```

- Detects framing automatically: `:N` → MS2000 error, `:A` → MS2000 ack/data, empty → Tiger ack, bare text → Tiger data.
- Returns the parsed `Reply` and the detected `ASIMode` (`TIGER` / `MS2000`).
- When `requested_axes` is given, key/value replies are filtered to those axes.

## Models — [`../model/`](../model/)

- **`Reply`**, **`ASIMode`**, **`ASIAxisInfo`** ([`models.py`](../model/models.py)) — the parsed reply, the controller dialect, and per-axis descriptors.
- **`WhoReportItem`**, **`CardInfo`** ([`card_info.py`](../model/card_info.py)) — one entry of a `WHO` roster and its per-card aggregation.
- **`AxisState`** ([`axis_state.py`](../model/axis_state.py)) — decoded `INFO` axis state.
- **`BuildReport`** ([`build_report.py`](../model/build_report.py)) — decoded `BU X` build/module report.
- **`BoxInfo`** ([`box_info.py`](../model/box_info.py)) — the assembled controller inventory, built from structured reports rather than raw text:

  ```python
  BoxInfo(who: list[CardInfo], build: BuildReport | None = None, *,
          pzinfo=None, version=None, axis_ids=None, enc_cnts_per_mm=None)
  ```

  Key properties: `comm_addr` (`int | None`), `cards` (`list[CardInfo]`), `axes` (`dict[str, ASIAxisInfo]`), `motor_axes` (motors only), `axes_by_card` (`dict[int, set[ASIAxisInfo]]`), `build`, `version`, `controller`, and `issues` (diagnostics).
