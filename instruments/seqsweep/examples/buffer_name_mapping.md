# ACS buffer names -> Python names

Maps the variables in `Stage buffer_062226.txt` to the SeqSweep Python names.

| Buffer | Meaning | Python name |
|---|---|---|
| `AX_X` / `AX_Y` | axis indices | `axis_x` / `axis_y` (`AcsControllerConfig`) |
| `X0` | scan start, imaged range | `scan_start_mm` (job) |
| `X_end` | scan end, imaged range | `scan_end_mm` (job) |
| `Y_SAMP_1/2/3` | chamber Y positions (lower edge) | `chambers_step_mm` (`{1: 200.25, 2: 155.0, 3: 109.75}`) |
| `Y0` | first strip's Y; `Y0 - Y_SAMP_n` is the offset from the chamber edge | `step_margin_mm` (job, mm; the same for every chamber in the job) |
| `Y_POS` | strip-axis position of strip `i` (`Y0 + i * FOV_Y`), calculated | `strip_pos_mm` (proposed name, not in the code yet); see the worked example below |
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
| `X_ABS_MIN/MAX`, `Y_ABS_MIN/MAX` | stage range | `limits_mm` (`AcsControllerConfig`) |
| `X_SCAN_MIN/MAX` | scan ± margin | derived from `scan_start_mm`, `scan_end_mm`, `scan_margin_mm`; may not have its own name |
| `origin` | home | `origin_mm` |
| `LINE_RATE` | camera line rate | `line_rate_hz` (job); `max_line_rate_hz` is only the limit it is checked against |
| `VEL_X` | scan speed, calculated: `LINE_RATE * PIXEL_SIZE` | `scan_speed_mm_s` (`seqsweep.py`: `line_rate_hz * pixel_size_um / 1000`) |
| `LINE_PULSE_MS` | line pulse width | `line_pulse_width_ms` |
| `ACC` / `DEC` (X) | accel / decel | `scan_accel` / `scan_decel` |
| `VEL(AX) = 50` | positioning speed | `move_velocity_mm_s` |

## Worked example: `strip_pos_mm`

`strip_pos_mm = chamber_start_mm + strip_index * tdi_image_width_mm`

With the default optics (`tdi_pixel_um` 5, `magnification` 20, `tdi_image_width_px` 480):

- `pixel_size_um` = 5 / 20 = 0.25 µm
- `tdi_image_width_um` = 480 × 0.25 = 120 µm = 0.12 mm

| Chamber | `chamber_start_mm` | strip 0 | strip 1 | strip 2 |
|---|---|---|---|---|
| 1 | 200.25 | 200.25 | 200.37 | 200.49 |
| 2 | 155.0 | 155.0 | 155.12 | 155.24 |
| 3 | 109.75 | 109.75 | 109.87 | 109.99 |

The buffer's own `Y_POS` is the chamber 2 row (`Y0 = Y_SAMP_2 = 155`), strip 0, so the value is 155.0 for `NUM_STRIPS = 1`.
Chambers step towards lower Y (200.25, 155.0, 109.75), but strips step towards higher Y, so check that `num_strips * 0.12` mm stays inside the 45.25 mm chamber pitch (see the TODO in `job_model.py:41`).
