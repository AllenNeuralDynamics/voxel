# ACS buffer names -> Python names

Maps the variables in Miki's `Stage buffer_112026.txt` to the SeqSweep names. Where a value is a global of our own buffers
(`scan_pass.acsp`, `home.acsp`), the buffer variable has the same name as the config or job value it comes from.

## Miki's buffer variables

| Buffer | Meaning | Python name |
|---|---|---|
| `AX_X` / `AX_Y` | axis indices | `axis_x` / `axis_y` (`AcsControllerConfig`) |
| `X0` | scan start, imaged range | `scan_start_mm` (job) |
| `X_end` | scan end, imaged range | `scan_end_mm` (job) |
| `Y_SAMP_1/2/3` | chamber Y positions (edge not confirmed with Miki) | `chambers_step_mm` (default, `{1: 200.25, 2: 155.0, 3: 109.75}`) |
| `Y0` | first strip's Y; `Y0 - Y_SAMP_n` is the offset from the chamber edge | `step_margin_mm` (job, mm; the same for every chamber in the job; temporary) |
| `Y_POS` | strip-axis position of strip `i` (`Y0 + i * FOV_Y`), calculated | computed in `SeqSweep._run_passes`; see the worked example below |
| `NUM_STRIPS` | frames per chamber | `num_strips` (job, default 1) |
| `TDI_PIXEL_SIZE` | sensor pixel size | `optics.tdi_pixel_um` |
| `MAG` | magnification | `optics.magnification` |
| `TDI_PIX_WIDTH` | sensor width (px) | `optics.tdi_image_width_px` |
| `TDI_STAGES` | unused in the new buffer (was the lead-in, in pixels) | none |
| `PIXEL_SIZE` (mm) | pixel on sample | `pixel_size_um` (µm); also the stage travel per line trigger |
| `FOV_Y` | strip width on sample | `tdi_image_width_um` |
| `MARGIN` | lead-in/out distance | `scan_margin_mm` (job, mm) |
| `CAPTURE_DISTANCE` | `abs(X_end - X0)` | `capture_mm` |
| `travel_len` | capture plus 2 × margin | `travel_mm` |
| `X_ABS_MIN/MAX`, `Y_ABS_MIN/MAX` | stage range for scans and positioning moves | `limits_mm` (`AcsControllerConfig`); also `scan_safe_range_mm` (default) for the scan range |
| `X_SCAN_MIN/MAX` | scan ± margin | derived from `scan_start_mm`, `scan_end_mm`, `scan_margin_mm`; checked in the buffer against the limits |
| `START 8, homeA` (buffer 0) | home move to (0, 0); Miki is moving homing to buffer 2 | `home_buffer` + `home_mm`, program `home.acsp` (see below) |
| `LINE_RATE` | camera line rate | `line_rate_hz` (job); `max_line_rate_hz` is only the limit it is checked against |
| `VEL_X` | scan speed, calculated: `LINE_RATE * PIXEL_SIZE` | `scan_speed_mm_s` (`seqsweep.py`: `line_rate_hz * pixel_size_um / 1000`) |
| `LINE_PULSE_MS` | line pulse width | `line_pulse_width_ms` |
| `ACC` / `DEC` (X) | accel / decel | `scan_accel` / `scan_decel` |
| `VEL(AX) = 50` | positioning speed | `move_velocity_mm_s` |
| `lc.LaserEnable()` / `lc.LaserDisable()` | arm the LCI around the scan move (it also gates the line trigger); not a per-laser switch | always called in `scan_pass.acsp`; no laser setting |

## Our buffers

Controller buffers (`AcsControllerConfig`): Miki uses 1 (scan) and 2 (homing); 0 stays blank for the vendor software.

| Config | Buffer | Holds |
|---|---|---|
| `scan_buffer` | 3 | `scan_pass.acsp`, one strip pass |
| `home_buffer` | 4 | `home.acsp`, the home move |
| `d_buffer` | 10 | the D-Buffer (global `LCI lc` declaration); the number depends on the firmware |

Global variables of the buffers, written by `AcsController`:

| Buffer variable | Comes from |
|---|---|
| `scan_start_mm`, `scan_end_mm` | job (`scan_end_mm` first for a reverse strip) |
| `scan_margin_mm` | job |
| `scan_dir` | strip direction, from the traversal |
| `pixel_size_mm` | `pixel_size_um` / 1000 (mm in the buffer, µm in Python) |
| `scan_speed_mm_s` | derived: `line_rate_hz * pixel_size_um / 1000` |
| `line_pulse_width_ms` | config |
| `move_velocity_mm_s` | config (also used by `home.acsp`) |
| `scan_accel`, `scan_decel` | config |
| `limit_min_mm`, `limit_max_mm` | `limits_mm` of the scan axis |
| `scan_axis` | axis index from `scan_axis` and `axis_x` / `axis_y` |
| `pulse_count` | result: line pulses fired in the pass |
| `home_x_mm`, `home_y_mm` | `home_mm` |
| `home_axis_x`, `home_axis_y` | `axis_x`, `axis_y` |

`home.acsp` is a plain move of both axes to `home_mm` at `move_velocity_mm_s`, with no limit check, so (0, 0) can lie outside
`limits_mm`. It is not Miki's `homeA` itself; what `homeA` does (limit-switch homing or only a move) is still to be confirmed.

## Worked example: strip position

`strip_y_mm = chambers_step_mm[chamber] + step_margin_mm + strip_index * tdi_image_width_mm`

With the default optics (`tdi_pixel_um` 5, `magnification` 20, `tdi_image_width_px` 4352):

- `pixel_size_um` = 5 / 20 = 0.25 µm
- `tdi_image_width_um` = 4352 × 0.25 = 1088 µm = 1.088 mm

With the example job (`step_margin_mm` 8.33, `num_strips` 5):

| Chamber | `chambers_step_mm` | strip 0 | strip 1 | strip 2 | strip 3 | strip 4 |
|---|---|---|---|---|---|---|
| 1 | 200.25 | 208.580 | 209.668 | 210.756 | 211.844 | 212.932 |
| 3 | 109.75 | 118.080 | 119.168 | 120.256 | 121.344 | 122.432 |

For chamber 3 the first strip is `Y0 = 118.08` in Miki's buffer. Strips step towards higher Y from the chamber value.
