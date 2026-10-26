# Laser API

`Laser` represents controlled light from one vendor product or a source combined with a modulator or shutter.
Its output boundary precedes the microscope optics owned by `IlluminationAssembly`.
The canonical contract lives in `vxl.devices.laser`, with physical implementations in `vxl_drivers.lasers`.
Instrument commands, UI controls, and templates are still being migrated to this contract.
Older drivers live in `vxl_drivers.lasers_legacy` and report `laser_legacy`; they remain discoverable through
`hal.devices`, but are excluded from `hal.lasers` and illumination assignments.

## Contract

| Interface | Module | Purpose |
| --- | --- | --- |
| `Laser` | [base.py](base.py) | Source settings plus controlled output |
| `LaserSource` | [source.py](source.py) | Source permission, modulation, and optical-power setpoint in mW |
| `CurrentControlledLaserSource` | [source.py](source.py) | Source permission, modulation, and diode-current setpoint in mA |

`Laser` extends `LaserSource` and is the intended microscope-facing API. Only `Laser` is exported from the package root.
Concrete drivers supply the read-only `wavelength` in nm; compositions forward their source's wavelength.

| Control | Meaning |
| --- | --- |
| `source_enable(*, wait=False)` | Grant source permission while preserving output inhibition |
| `source_disable()` | Block output and clear both permissions, retaining settings |
| `output_enable(*, wait=False)` | Require source permission and permit output in the established mode |
| `output_disable()` | Block output regardless of external inputs, retaining source permission and settings |
| `is_source_enabled`, `is_output_enabled` | Permission flags; they do not measure emission or readiness |
| `source_power_setpoint_mw` | Requested source power, or the saved reference in a composition that scales source power |
| `source_power_mw` | Source-reported or estimated optical power; `None` when unavailable |
| `output_level_percent` | Saved software/digital operating level; inactive in analog mode |
| `output_power_mw` | Measured power at the laser output boundary; `None` when unavailable |

Enable commands are idempotent. Setpoints do not enable either layer. Source permission may be logical: a source-only
implementation defers physical startup until output is enabled.

Numeric properties expose their range/resolution or allowed options. A fixed source has one mW option;
a binary output can expose `(0, 100)`. Zero is optional; where supported in software/digital mode it blocks light
without clearing output permission. Use `output_disable()` for off independently of the saved level.
At 100%, the available output corresponds to the selected source reference. Intermediate percentages describe the
implementation's modulation setting; optical linearity requires an appropriate mapping or calibration.

For a fixed or manually adjusted source, the driver can accept a user-measured operating power during construction.
Changing that physical setting requires updating the configured reference. A power value alone cannot supply
missing emission-switching hardware. Power-meter placement and association with a laser remain explicit workflow
choices; registering a meter does not populate `output_power_mw` automatically.

## Modulation and command completion

| `modulation_mode` | What sets intensity | What controls timing |
| --- | --- | --- |
| `software` | `output_level_percent` | Software output commands |
| `digital` | `output_level_percent` sets the active level | External digital signal, subject to output permission |
| `analog` | External analog waveform; saved percentage is inactive | External signal, subject to output permission |

The read-only `@enumerated` property reports the established mode and supported choices.
Use `set_modulation_mode()` with a `ModulationMode` member or lowercase string; unsupported modes raise `ValueError`.
The base blocks mode changes while source permission is enabled on `LaserSource`, or output permission is enabled
on `Laser`. Selecting the current mode is a no-op. Mode selection belongs in setup commands or imaging preparation,
not property defaults or saved profile properties. Drivers implement `_get_modulation_modes()`, `_read_modulation_mode()`, and
`_configure_modulation_mode()`; the base stores no mode state.

A source's mode describes its direct modulation. A composition declares modes for its complete output control;
for example, an AOM can accept analog modulation while its source remains in software mode.
Mode configuration preserves inhibition and restores the saved level when entering software/digital mode.
In analog mode, valid percentage assignments only save the value, without warning. The same numeric constraints
apply in every mode. The microscope owns external signals, wiring, and sequencing.

With `wait=True`, enable commands use the driver's bounded startup check or configured delay. They never wait for
an asserted external signal or nonzero output, and do not guarantee optical stability. Source-only startup and its
wait may be deferred to `output_enable()`. Setters add no settling wait. Drivers surface transaction failures;
permission flags alone do not establish hardware state after a failed operation.

## Hardware arrangements

| Hardware arrangement | `Laser` implementation | Output level | Output disable |
| --- | --- | --- | --- |
| Integrated source and output controls | Vendor `Laser` driver | Internal modulation | Device output inhibit |
| Adjustable source alone | `SourceOnlyLaser` | Scales the source reference | Stops source emission |
| Fixed-power source alone | `SourceOnlyLaser` | Only 100% | Stops source emission |
| Source + external shutter | Future composition | Typically only 100%; source scaling can provide adjustment | Closes shutter |
| Source + AOM/AOTF | `MPDSLaser` or another composition | Modulator attenuation or source scaling | Modulator inhibition or source shutdown |
| Source + attenuator + separate shutter | Future composition | Attenuator setting | Closes shutter |

### SourceOnlyLaser

[`SourceOnlyLaser`](source_only.py) borrows a source and disables it during construction. Register both devices on
the same rigup node and inject the source by UID; source-specific properties remain discoverable on the source.
Closing the adapter inhibits output but leaves the source connection to its owner.

The initial reference is the source's existing setpoint, the level is 100%, and both permissions are off.
In software/digital mode, the physical command is `reference_mw * output_level_percent / 100`.
The source reports that reduced command; the adapter retains the reference. Analog mode programs the full reference
and leaves intensity to the external input. Supported modes come from the source.

Source constraints become percentage constraints: a 200 mW minimum with a 400 mW reference gives a 50–100% range;
at 800 mW it gives 25–100%. Fixed sources and zero references expose only 100%. Unattainable levels are rejected,
while source resolution can round a valid level. Reference changes that make the saved level unattainable are
rejected before writing hardware. Output disable preserves reference and level.

Failed enables attempt inhibition and revoke output permission. Failed disables retain previous permissions;
close can be retried after inhibition fails. If an operation and cleanup both fail, both errors are reported.
Direct source writes bypass the adapter. Each registered device has its own worker, so cross-device access still
requires coordination; constructor injection alone does not serialize calls from separate controllers.

### Physical drivers and calibration

| Implementation | Role and current behavior |
| --- | --- |
| [GenesisMXSource](../../../../drivers/src/vxl_drivers/lasers/genesis_mx.py) | Software-only source using the Coherent SDK; wrap with `SourceOnlyLaser` or compose with MPDS |
| [MPDS controller](../../../../drivers/src/vxl_drivers/lasers/mpds/controller.py) | Shared serial connection, RF lines, common blanking, and line reservations |
| [MPDSLaser](../../../../drivers/src/vxl_drivers/lasers/mpds/laser.py) | Source plus one MPDS line; software, digital, and analog modes |
| [OxxiusLBXSource](../../../../drivers/src/vxl_drivers/lasers/oxxius/lbx.py) | Native source modulation with calibrated current control for digital mode; wrap with `SourceOnlyLaser` |
| [OxxiusLCXLaser](../../../../drivers/src/vxl_drivers/lasers/oxxius/lcx.py) | LCX with linked AOM, using source shutdown to inhibit output |

Module docstrings contain configuration examples and pending hardware checks. Physical behavior remains unverified
on the installed instruments. Genesis uses configured power limits and an optional `startup_delay_s`; the default
zero adds no startup delay. The Oxxius drivers share an [L4Cc/L6Cc controller](../../../../drivers/src/vxl_drivers/lasers/oxxius/controller.py).

`MPDSLaser` independently selects `level_control` and `output_switch` as `aotf` or `source`.
AOTF switching parks the line in internal OFF and restores external mode on enable. Source switching defers source
startup until output enable. Common blanking remains internal ON and belongs to the shared controller.
`MPDSSettings` accepts optional optical calibration; without it, AOTF percentages interpolate the RF-dBm interval.
The [calibration CLI](../../../../drivers/src/vxl_drivers/lasers/mpds/cli.py) searches RF settings, measures the response,
and exports copyable YAML, raw readings, and optional plots. Run `vxl-calibrate-mpds --example` for input configuration.

[`vxlib.calibration`](../../../../vxlib/src/vxlib/calibration.py) supplies polynomial and piecewise-linear models,
bounded inversion, and explicit inverse-solution selection. The general `CurrentToPowerAdapter` remains planned;
it will adapt a `CurrentControlledLaserSource` using measured current-to-power calibration.

## Simulation

[`SimulatedLaser`](simulated.py) provides linear attenuation with configurable source-power noise. It starts with
both permissions off, zero power and level, and the first configured modulation mode.
`power_noise_percent` defaults to 0.5: each power read samples Gaussian noise with a standard deviation of
0.5% of the source setpoint. Set it to zero for deterministic readings. Output readings inherit the source noise.
`source_enable_delay_s` defaults to zero. Non-waiting source enable starts a deadline; repeated enable calls
preserve it. Source and output enable with `wait=True` wait for any remaining startup time. Simulated power
remains zero until startup finishes, independently of source permission.
All modulation modes use `source_power_mw * output_level_percent / 100` while output is enabled.
This application simulator does not model external DAQ signals; analog mode deliberately uses the saved level too.

```python
from vxl.devices.laser.simulated import SimulatedLaser

laser = SimulatedLaser("test_laser", wavelength=488, max_power_mw=100, power_noise_percent=0)
try:
    laser.source_power_setpoint_mw = 40
    laser.output_level_percent = 25
    laser.set_modulation_mode("digital")
    laser.source_enable()
    laser.output_enable()
    assert laser.output_power_mw == 10
finally:
    laser.close()
```

## Microscope integration and pending work

Digital preview supplies exposure-synchronized gates; live intensity changes adjust the saved level.
Analog intensity changes require DAQ waveform updates. Manual viewing can select software mode or hold an external
input active. The microscope owns DAQ mapping and keeps inputs inactive during configuration.

Named waveform groups remain a proposed approach: `frame` for acquisition and, for example, `laser_488` for continuous
light without camera triggers. These would be alternative configurations of one generator. The current NI generator
reserves all configured pins, so a second on-demand task cannot claim the same output. See the local
[waveform-group investigation](</Users/walter.mwaniki/Library/Mobile Documents/iCloud~md~obsidian/Documents/Microscopy/voxel/plans/illumination-waveform-groups.md>).

Remaining work:

- Finish instrument, template, and UI migration; consider typed handles and manual-viewing sequencing.
- Define ownership of direct component writes while a composition is operating. A source write can bypass
  `SourceOnlyLaser`'s saved reference; serial transaction locks do not keep that reference synchronized.
- Revisit dependency-aware teardown separately from this migration: close compositions before borrowed sources
  and controllers. Current drivers tolerate confirmed component shutdown, but rigup does not guarantee this order.
  See [rigup composition lifecycle](../../../../rigup/README.md#composition-lifecycle-and-access).
- Current-to-power adapter, current quantization, and effective power constraints.
- Discrete shutter compositions and verification of Genesis direct modulation.
- Consistent state reporting after partial configuration failures and timeouts.

Public timing metadata and user-selectable current/power regulation remain deferred.
Run the source-only checks with `uv run pytest tests/devices/laser/test_source_only.py`.
