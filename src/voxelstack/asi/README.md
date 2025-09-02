# ASI Tiger Driver (voxelstack)

Structured Python driver for **ASI Tiger / MS2000** controllers.

* Thread‑safe serial I/O via `TigerBox._tx()`
* Typed parameter access with `TigerParam`
* Stateless encode/decode ops
* Caching for controller info + joystick mappings

---

## Quickstart

```python
from voxelstack.asi.driver import TigerBox

box = TigerBox(port="COM3")
info = box.info(refresh=True)
print("Cards:", [c.addr for c in info.cards])
print("Axes:", sorted(info.axes.keys()))
```

## Motion

```python
# Read positions for a subset of axes
pos = box.get_position(["X", "Y", "Z"])   # {"X":..., "Y":..., "Z":...}

# Absolute / relative moves
box.move_abs({"X": 10.0, "Y": 5.0}, wait=True)
box.move_rel({"Z": -0.25}, wait=True)

# Logical coordinates
box.set_logical_position({"X": 0.0})  # alias for HERE
box.zero_axes(["X", "Y"])            # convenience: HERE X=0 Y=0

# Homing & halting
box.home_axes(["X", "Y"], wait=True)
box.halt()

# Busy state
box.wait_until_idle(["X", "Y"])       # poll until not moving
busy = box.is_axis_moving(["X", "Y"])  # {"X": bool, "Y": bool}
```

## Parameters (typed)

```python
from voxelstack.asi.ops.params import TigerParams

axes = ["X", "Y", "Z"]

# Get multiple params at once
speeds   = box.get_param(TigerParams.SPEED, axes)         # {axis: float}
accel    = box.get_param(TigerParams.ACCEL, axes)         # {axis: int}
backlash = box.get_param(TigerParams.BACKLASH, axes)      # {axis: float}

# Set per‑axis
box.set_param(TigerParams.SPEED, {"X": 5.0, "Y": 7.5})
box.set_param(TigerParams.ACCEL, {"Z": 200})
```

| Verb | Name          | Type  |
| ---- | ------------- | ----- |
| S    | SPEED         | float |
| AC   | ACCEL         | int   |
| B    | BACKLASH      | float |
| HM   | HOME\_POS     | float |
| SL   | LIMIT\_LOW    | float |
| SU   | LIMIT\_HIGH   | float |
| J    | JOYSTICK\_MAP | int   |
| PM   | CONTROL\_MODE | str   |
| CNTS | ENCODER\_CNTS | float |
| Z2B  | AXIS\_ID      | int   |
| KP   | PID\_P        | float |
| KI   | PID\_I        | float |
| KD   | PID\_D        | float |
| HS   | HOME\_SPEED   | float |

## Scanning (fast/slow)

Short line scans where one axis (fast) sweeps continuously while another (slow) steps between lines. Useful for raster or serpentine imaging.

```python
from voxelstack.asi.ops.scan import ScanPattern, ScanRConfig, ScanVConfig

# Bind axes on a single card
box.configure_scan(fast_axis="X", slow_axis="Y", pattern=ScanPattern.SERPENTINE)

# Program fast axis (line)
actual_um = box.configure_scan_r(
    ScanRConfig(
        start_mm=0.0,
        stop_mm=5.0,            # or num_pixels=2048
        pulse_interval_um=1.0,  # enc‑derived, returns actual interval
        retrace_speed_percent=67,
    )
)

# Program slow axis (steps/lines)
box.configure_scan_v(
    ScanVConfig(
        start_mm=0.0,
        stop_mm=5.0,
        line_count=100,
        overshoot_time_ms=5,    # optional
        overshoot_factor=0.0,   # optional
    )
)

box.start_scan()
# ... acquire data ...
box.stop_scan()
```

## Array scan (+ optional auto‑home)

Tile‑based stage movement: move to a grid of XY positions with defined spacing and optional auto‑home behavior.

```python
from voxelstack.asi.ops.scan import ArrayScanConfig, AutoHomeConfig

arr = ArrayScanConfig(
    x_points=10,
    y_points=8,
    delta_x_mm=0.5,
    delta_y_mm=0.5,
)

home = AutoHomeConfig(x_start_mm=0.0, y_start_mm=0.0)

# Card inferred from X/Y if possible (same card required)
box.configure_array_scan(arr_scan_cfg=arr, auto_home_cfg=home)
box.start_array_scan()
```

## Step & Shoot (ring buffer + TTL)

Queue discrete absolute or relative positions into the controller’s ring buffer. Each hardware TTL pulse (IN0) advances one step. Ideal for triggered acquisitions.

```python
from voxelstack.asi.ops.step_shoot import StepShootConfig, TTLIn0Mode

cfg = StepShootConfig(
    axes=["X", "Y"],
    clear_buffer_first=True,
    in0_mode=TTLIn0Mode.MOVE_TO_NEXT_ABS_POSITION,  # or MOVE_TO_NEXT_REL_POSITION
    # out0_mode / aux_* as needed
)

box.configure_step_shoot(cfg)

# Queue targets (ABS mode)
box.queue_step_shoot_abs({"X": 1.0, "Y": 2.0})
box.queue_step_shoot_abs({"X": 3.0, "Y": 4.0})

# Hardware pulses on IN0 advance the queue
```

## Joystick helpers (mapping cache aware)

Convenience methods to read, disable, re‑enable, and overwrite joystick axis mappings. Cached state allows toggling without losing user bindings.

```python
# Read mapping
mapping = box.get_joystick_mapping()

# Disable inputs (caches current mapping so you can restore later)
box.disable_joystick_inputs(["X", "Y"])  # or None for all

# Re‑enable and restore previous bindings for affected axes
box.enable_joystick_inputs(["X", "Y"])

# Overwrite mapping explicitly
box.set_joystick_mapping({"X": mapping["X"], "Y": mapping["Y"]})
```

## Status & metadata

Helpers to check controller mode, busy state, and detailed axis status or version information.

```python
print("Mode:", box.current_mode())
print("Busy:", box.is_busy())
state = box.get_axis_state("X")         # AxisState
version = box.info().version
```

## Notes

* All methods raise `ASIDecodeError` on firmware errors; blocking helpers raise `TimeoutError`.
* `TigerBox.TIMEOUT_S` is the default timeout used by blocking calls.
