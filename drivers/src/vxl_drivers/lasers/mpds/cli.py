"""Calibrate MPDS RF control with a source and power meter, outside the microscope runtime.

    python -m vxl_drivers.lasers.mpds.cli --example > sweep.yaml
    python -m vxl_drivers.lasers.mpds.cli sweep.yaml --output run-001 --plot

Edit the example with actual device addresses, hardware limits, and sweep limits.
This command opens and exclusively controls the configured source, MPDS, and meter.
It searches for maximum light, repeats the power sweep at the best frequency, and
fits a monotonic response. It inhibits RF and source on completion or interruption.

Progress and summaries go to stderr; the final stdout is a copyable MPDSLaser init
fragment. Output includes raw.csv, run.json, and settings.yaml. --plot saves and
opens calibration.png; a headless launch keeps the image even if opening fails.
Install vxl-drivers[mpds-calibration] plus the extras/backends for your devices.
Default fitting is piecewise linear; --fit polynomial --degree 3 selects a polynomial.
The utility does not write instrument configuration or calibrate analog DAQ inputs.
"""

import argparse
import json
import logging
import sys
import webbrowser
from contextlib import ExitStack, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import model_validator
from rich.console import Console
from rich.progress import Progress, TaskID
from rigup.build import BuildConfig
from vxlib.schema import FrozenModel

from rigup import Device
from vxl.devices.laser.source import LaserSource
from vxl.devices.power_meter import PowerMeter
from vxl_drivers.lasers.mpds.calibration import SweepConfig, SweepResult, collect, fit_settings, save_plot
from vxl_drivers.lasers.mpds.controller import MPDS
from vxl_drivers.lasers.mpds.settings import MPDSSettings


class CalibrationConfig(FrozenModel):
    """Three standalone rigup build entries and the requested measurement grid."""

    devices: dict[Literal["source", "mpds", "meter"], BuildConfig]
    sweep: SweepConfig

    @model_validator(mode="after")
    def _check_devices(self) -> "CalibrationConfig":
        if set(self.devices) != {"source", "mpds", "meter"}:
            raise ValueError("devices must contain exactly source, mpds, and meter")
        for config in self.devices.values():
            if "uid" in config.init:
                raise ValueError("device UIDs are supplied by the source/mpds/meter role names")
        return self


def _open_device[D: Device](uid: str, config: BuildConfig, expected: type[D], stack: ExitStack) -> D:
    driver = config.get_obj_class()
    if not issubclass(driver, expected):
        raise TypeError(f"{uid} must implement {expected.__name__}")
    device = driver(uid=uid, **config.init)
    stack.callback(device.close)
    for name, value in (config.defaults or {}).items():
        setattr(device, name, value)
    return device


def _meter_metadata(meter: PowerMeter, console: Console) -> dict[str, Any]:
    metadata: dict[str, Any] = {"driver": f"{type(meter).__module__}.{type(meter).__name__}"}
    for name in ("identification", "sensor_identification", "averaging_count", "autorange", "range_mw"):
        try:
            value = getattr(meter, name, None)
            if value is not None:
                metadata[name] = value
        except Exception as error:
            console.print(f"Could not read meter {name}: {error}", markup=False)
    return metadata


def run(
    config: CalibrationConfig,
    output: Path,
    *,
    fit: Literal["piecewise_linear", "polynomial"] = "piecewise_linear",
    degree: int = 3,
    plot: bool = False,
    console: Console | None = None,
) -> dict[str, Any]:
    """Collect and save a candidate; never overwrite a previous run directory."""
    if degree < 1:
        raise ValueError("polynomial degree must be positive")
    console = console or Console(stderr=True)
    if plot:
        # Detect a missing optional plotting dependency before opening any hardware.
        from matplotlib.figure import Figure  # noqa: PLC0415

        _ = Figure
    output.mkdir(parents=True, exist_ok=False)
    record: dict[str, Any] = {
        "version": 1,
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "configuration": config.model_dump(mode="json"),
        "fit": fit,
        "degree": degree if fit == "polynomial" else None,
    }
    record_path = output / "run.json"
    record_path.write_text(json.dumps(record, indent=2) + "\n")
    try:
        with ExitStack() as stack:
            # Construct/inhibit the controller before opening a source.
            mpds = _open_device("mpds", config.devices["mpds"], MPDS, stack)
            source = _open_device("source", config.devices["source"], LaserSource, stack)
            meter = _open_device("meter", config.devices["meter"], PowerMeter, stack)
            record["meter"] = _meter_metadata(meter, console)
            record_path.write_text(json.dumps(record, indent=2) + "\n")
            with (output / "raw.csv").open("x", newline="") as raw, Progress(console=console) as progress:
                tasks: dict[str, TaskID] = {}

                def update(phase: str, completed: int, total: int) -> None:
                    if phase not in tasks:
                        tasks[phase] = progress.add_task(phase, total=total)
                    progress.update(tasks[phase], completed=completed)

                result = collect(source, mpds, meter, config.sweep, raw, update)
        # Hardware is closed before any fitting, file formatting, or display work.
        settings = fit_settings(result, kind=fit, degree=degree)
        snippet = _snippet(settings, config.sweep.line)
        (output / "settings.yaml").write_text(_dump_yaml(snippet))
        best = max(result.search, key=lambda point: point.power_mw)
        record["search_maximum"] = best.model_dump()
        record["response"] = [point.model_dump() for point in result.response]
        record["settings"] = settings.model_dump(mode="json")
        console.print(
            f"Search maximum: {best.power_mw:g} mW at {best.frequency_mhz:g} MHz, {best.rf_power_dbm:g} dBm.",
            markup=False,
        )
        console.print(
            f"Selected RF interval: {settings.min_rf_power_dbm:g}-{settings.max_rf_power_dbm:g} dBm; "
            f"optical level: {settings.minimum_level_percent:g}-100%.",
            markup=False,
        )
        if plot:
            _plot(result, settings, output, console)
        record["status"] = "complete"
        console.print(f"Saved measurements and configuration to {output.resolve()}", markup=False)
        return snippet
    except BaseException as error:
        record["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        record["error"] = str(error)
        raise
    finally:
        record["finished_at"] = datetime.now(UTC).isoformat()
        record_path.write_text(json.dumps(record, indent=2) + "\n")


def _snippet(settings: MPDSSettings, line: int) -> dict[str, Any]:
    data = settings.model_dump(mode="json")
    if settings.calibration is not None:
        mapping = settings.calibration.mapping
        data["calibration"]["mapping"] = {
            "kind": mapping.kind,
            **mapping.model_dump(mode="json", exclude_defaults=True),
        }
    return {
        "init": {
            "source": "source",
            "mpds": "mpds",
            "line": line,
            "settings": data,
        }
    }


class _CalibrationDumper(yaml.SafeDumper):
    """Keep numeric vectors and point pairs compact in copyable YAML."""


def _sequence(dumper: _CalibrationDumper, values: list[Any]) -> yaml.SequenceNode:
    return dumper.represent_sequence(
        "tag:yaml.org,2002:seq", values, flow_style=all(not isinstance(value, (list, dict)) for value in values)
    )


_CalibrationDumper.add_representer(list, _sequence)


def _dump_yaml(data: dict[str, Any]) -> str:
    return yaml.dump(data, Dumper=_CalibrationDumper, sort_keys=False)


def _plot(result: SweepResult, settings: MPDSSettings, output: Path, console: Console) -> None:
    path = output / "calibration.png"
    save_plot(result, settings, path)
    try:
        opened = webbrowser.open(path.resolve().as_uri())
    except Exception as error:
        console.print(f"Plot saved; could not open viewer: {error}", markup=False)
        return
    if not opened:
        console.print(f"Plot saved; open {path.resolve()} to view it.", markup=False)


_EXAMPLE = """# Standalone devices exclusively owned by this calibration run.
# Replace addresses, limits, and sensor location for your installation.
devices:
  source:
    target: vxl_drivers.lasers.genesis_mx.GenesisMXSource
    init:
      serial: YOUR_SERIAL
      wavelength: 561
      min_power_mw: 200
      max_power_mw: 1000
      startup_delay_s: 5
  mpds:
    target: vxl_drivers.lasers.mpds.controller.MPDS
    init:
      port: YOUR_PORT
      min_frequency_mhz: 80
      max_frequency_mhz: 120
      min_power_dbm: 0
      max_power_dbm: 20
    defaults:
      external_voltage_range: 5
  meter:
    target: vxl_drivers.power_meters.thorlabs.ThorlabsPowerMeter
    init:
      resource: USB0::0x1313::0x8078::YOUR_SERIAL::INSTR
    defaults:
      averaging_count: 10
      autorange: true
sweep:
  line: 1
  source_power_mw: 300
  min_frequency_mhz: 95
  max_frequency_mhz: 105
  frequency_step_mhz: 1
  min_rf_power_dbm: 0
  max_rf_power_dbm: 20
  rf_power_step_dbm: 1
  settle_s: 0.5
  samples_per_point: 3
  sample_interval_s: 0.05
  measurement_location: AOTF output
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", type=Path, nargs="?", help="YAML device and sweep configuration")
    parser.add_argument("--output", type=Path, help="New directory for raw data and calibration files")
    parser.add_argument("--plot", action="store_true", help="Save and open the sweep/response figure")
    parser.add_argument("--fit", choices=("piecewise_linear", "polynomial"), default="piecewise_linear")
    parser.add_argument("--degree", type=int, default=3, help="Polynomial degree (default: 3)")
    parser.add_argument("--example", action="store_true", help="Print example input YAML without opening hardware")
    args = parser.parse_args()
    if args.example:
        sys.stdout.write(_EXAMPLE)
        return
    if args.config is None or args.output is None:
        parser.error("config and --output are required unless --example is used")
    console = Console(stderr=True)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        config = CalibrationConfig.model_validate(yaml.safe_load(args.config.read_text()))
        # Vendor SDK prints must not contaminate the final YAML on stdout.
        with redirect_stdout(sys.stderr):
            snippet = run(config, args.output, fit=args.fit, degree=args.degree, plot=args.plot, console=console)
    except KeyboardInterrupt:
        console.print("Calibration interrupted; collected readings remain in the output directory.")
        raise SystemExit(130) from None
    except Exception as error:
        console.print(f"Calibration failed: {error}", markup=False)
        raise SystemExit(1) from None
    console.print("Copy the following init fragment into your laser entry; adjust component UIDs as needed.")
    sys.stdout.write(_dump_yaml(snippet))


if __name__ == "__main__":
    main()
