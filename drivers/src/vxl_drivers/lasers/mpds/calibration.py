"""Measurement and fitting for MPDS calibration; callers own device lifetimes.

Frequency search and response collection use software RF control. Limits and steps
must be on the MPDS command grid. Every reading is written immediately so interrupted
runs retain their data. The selected monotonic branch contains the measured maximum;
noise or reversals shorten it rather than silently changing the measurements.
"""

import csv
from collections.abc import Callable
from contextlib import ExitStack
from functools import partial
from itertools import pairwise
from math import isclose, isfinite
from pathlib import Path
from statistics import mean
from time import sleep
from typing import Literal, Self, TextIO

from pydantic import Field, FiniteFloat, model_validator
from vxlib.calibration import CalibrationModel, PiecewiseLinearCalibration, PolynomialCalibration
from vxlib.schema import FrozenModel

from vxl.devices.laser.source import LaserSource, ModulationMode
from vxl.devices.power_meter import PowerMeter
from vxl_drivers.lasers.mpds.controller import MPDS, InputMode
from vxl_drivers.lasers.mpds.settings import MPDSCalibration, MPDSSettings


class SweepConfig(FrozenModel):
    """Bounded search grid, source reference, and measurement timing."""

    line: int = Field(ge=1)
    source_power_mw: FiniteFloat = Field(gt=0)
    min_frequency_mhz: FiniteFloat = Field(gt=0)
    max_frequency_mhz: FiniteFloat = Field(gt=0)
    frequency_step_mhz: FiniteFloat = Field(gt=0)
    min_rf_power_dbm: FiniteFloat = Field(ge=0)
    max_rf_power_dbm: FiniteFloat = Field(ge=0)
    rf_power_step_dbm: FiniteFloat = Field(gt=0)
    settle_s: FiniteFloat = Field(default=0.5, ge=0)
    samples_per_point: int = Field(default=3, ge=1)
    sample_interval_s: FiniteFloat = Field(default=0.05, ge=0)
    measurement_location: str = "unspecified"

    @model_validator(mode="after")
    def _validate_grid(self) -> Self:
        grid(self.min_frequency_mhz, self.max_frequency_mhz, self.frequency_step_mhz, 3)
        powers = grid(self.min_rf_power_dbm, self.max_rf_power_dbm, self.rf_power_step_dbm, 1)
        if len(powers) < 2:
            raise ValueError("power sweep requires at least two RF settings")
        return self


def grid(lower: float, upper: float, step: float, digits: int) -> list[float]:
    """Inclusive grid with exact hardware-resolution endpoints and no hidden rounding."""
    if upper < lower or step <= 0:
        raise ValueError("sweep limits must be ordered and step positive")
    for value in (lower, upper, step):
        if not isfinite(value) or not isclose(value, round(value, digits), rel_tol=0, abs_tol=1e-9):
            raise ValueError(f"sweep values must use {10**-digits:g} increments")
    count = (upper - lower) / step
    if not isclose(count, round(count), rel_tol=0, abs_tol=1e-7):
        raise ValueError("sweep step must divide the interval exactly")
    if count > 100000:
        raise ValueError("sweep axis exceeds 100000 intervals")
    return [round(lower + i * step, digits) for i in range(round(count) + 1)]


class Measurement(FrozenModel):
    """Mean optical power at one RF command; individual readings remain in CSV."""

    frequency_mhz: float
    rf_power_dbm: float
    power_mw: float


class SweepResult(FrozenModel):
    search: tuple[Measurement, ...]
    response: tuple[Measurement, ...]
    wavelength_nm: float
    source_reference_mw: float


def collect(
    source: LaserSource,
    mpds: MPDS,
    meter: PowerMeter,
    config: SweepConfig,
    output: TextIO,
    progress: Callable[[str, int, int], None],
) -> SweepResult:
    """Collect both sweeps; inhibit RF and source even on failure or interruption."""
    frequencies = grid(config.min_frequency_mhz, config.max_frequency_mhz, config.frequency_step_mhz, 3)
    powers = grid(config.min_rf_power_dbm, config.max_rf_power_dbm, config.rf_power_step_dbm, 1)
    for frequency in frequencies:
        mpds.validate_frequency(frequency)
    for power in powers:
        mpds.validate_power(power)
    if ModulationMode.SOFTWARE not in source.modulation_mode.options:
        raise ValueError("calibration requires a software-controlled source")
    writer = csv.writer(output)
    writer.writerow(("phase", "frequency_mhz", "rf_power_dbm", "sample", "power_mw"))
    output.flush()
    with ExitStack() as cleanup:
        cleanup.callback(source.source_disable)
        cleanup.callback(mpds.inhibit_line, config.line)
        mpds.inhibit_line(config.line)
        source.source_disable()
        source.set_modulation_mode(ModulationMode.SOFTWARE)
        if source.modulation_mode != ModulationMode.SOFTWARE:
            raise RuntimeError("source did not establish software modulation")
        source.source_power_setpoint_mw = config.source_power_mw
        reference = float(source.source_power_setpoint_mw)
        if not isclose(reference, config.source_power_mw, rel_tol=0, abs_tol=1e-6):
            raise ValueError("source cannot represent the requested calibration reference")
        wavelength = float(source.wavelength)
        meter.wavelength_nm = wavelength
        if not isclose(float(meter.wavelength_nm), wavelength, rel_tol=0, abs_tol=1e-6):
            raise ValueError("meter cannot represent the source wavelength")
        mpds.blanking_mode = InputMode.INTERNAL
        mpds.blanking_enabled = True
        mpds.set_input_mode(config.line, InputMode.INTERNAL)
        source.source_enable(wait=True)
        if not source.is_source_enabled:
            raise RuntimeError("source did not enable")

        measure = partial(_measure, source, mpds, meter, config, output)

        search = []
        total = len(frequencies) * len(powers)
        for power in powers:
            for frequency in frequencies:
                search.append(measure("search", frequency, power))
                progress("Search", len(search), total)
        best = max(search, key=lambda point: point.power_mw)
        response = []
        for power in powers:
            response.append(measure("response", best.frequency_mhz, power))
            progress("Response", len(response), len(powers))
        return SweepResult(
            search=tuple(search), response=tuple(response), wavelength_nm=wavelength, source_reference_mw=reference
        )


def _measure(
    source: LaserSource,
    mpds: MPDS,
    meter: PowerMeter,
    config: SweepConfig,
    output: TextIO,
    phase: str,
    frequency: float,
    power: float,
) -> Measurement:
    mpds.set_enabled(config.line, False)
    mpds.set_frequency(config.line, frequency)
    mpds.set_power(config.line, power)
    mpds.set_enabled(config.line, True)
    sleep(config.settle_s)
    writer = csv.writer(output)
    readings = []
    for sample in range(config.samples_per_point):
        if sample:
            sleep(config.sample_interval_s)
        if not source.is_source_enabled:
            raise RuntimeError("source enable was lost during calibration")
        reading = meter.power_mw
        if not isfinite(reading):
            raise ValueError("meter returned a nonfinite reading")
        readings.append(reading)
        writer.writerow((phase, frequency, power, sample, reading))
        output.flush()
    return Measurement(frequency_mhz=frequency, rf_power_dbm=power, power_mw=mean(readings))


def fit_settings(
    result: SweepResult,
    *,
    kind: Literal["piecewise_linear", "polynomial"] = "piecewise_linear",
    degree: int = 3,
) -> MPDSSettings:
    """Select a measured monotonic branch and fit optical percent versus RF dBm."""
    response = result.response
    peak = max(range(len(response)), key=lambda index: response[index].power_mw)
    full_scale = response[peak].power_mw
    if full_scale <= 0:
        raise ValueError("no positive optical response measured")
    left = right = peak
    while left > 0 and 0 <= response[left - 1].power_mw < response[left].power_mw:
        left -= 1
    while right + 1 < len(response) and 0 <= response[right + 1].power_mw < response[right].power_mw:
        right += 1
    branches = [response[left : peak + 1], response[peak : right + 1]]
    usable = [branch for branch in branches if len(branch) >= 2]
    if not usable:
        raise ValueError("no monotonic branch reaches the maximum; inspect CSV and adjust sampling")
    branch = min(usable, key=lambda values: min(point.power_mw for point in values))
    points = tuple((point.rf_power_dbm, point.power_mw / full_scale * 100) for point in branch)
    domain = (points[0][0], points[-1][0])
    mapping: CalibrationModel
    if kind == "piecewise_linear":
        mapping = PiecewiseLinearCalibration(domain=domain, points=points)
    else:
        fitted = PolynomialCalibration.fit(points, degree=degree)
        endpoint_maximum = max(fitted.forward(domain[0]), fitted.forward(domain[1]))
        if endpoint_maximum <= 0:
            raise ValueError("polynomial fit has no positive full-scale response")
        mapping = PolynomialCalibration(
            domain=domain, coefficients=tuple(value * 100 / endpoint_maximum for value in fitted.coefficients)
        )
    return MPDSSettings(
        frequency_mhz=response[peak].frequency_mhz,
        min_rf_power_dbm=domain[0],
        max_rf_power_dbm=domain[1],
        calibration=MPDSCalibration(
            wavelength_nm=result.wavelength_nm,
            source_reference_mw=result.source_reference_mw,
            measured_full_scale_mw=full_scale,
            mapping=mapping,
        ),
    )


def save_plot(result: SweepResult, settings: MPDSSettings, path: Path) -> None:
    """Save sweep heatmap and selected-frequency fit in one figure without opening a GUI."""
    import numpy as np  # noqa: PLC0415
    from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: PLC0415
    from matplotlib.figure import Figure  # noqa: PLC0415

    frequencies = sorted({point.frequency_mhz for point in result.search})
    powers = sorted({point.rf_power_dbm for point in result.search})
    readings = {(point.frequency_mhz, point.rf_power_dbm): point.power_mw for point in result.search}
    data = [[readings[(frequency, power)] for frequency in frequencies] for power in powers]
    figure = Figure(figsize=(12, 5), layout="constrained")
    FigureCanvasAgg(figure)
    sweep_ax, response_ax = figure.subplots(1, 2)

    def edges(values: list[float], resolution: float) -> list[float]:
        if len(values) == 1:
            return [values[0] - resolution / 2, values[0] + resolution / 2]
        return [
            values[0] - (values[1] - values[0]) / 2,
            *((left + right) / 2 for left, right in pairwise(values)),
            values[-1] + (values[-1] - values[-2]) / 2,
        ]

    heatmap = sweep_ax.pcolormesh(edges(frequencies, 0.001), edges(powers, 0.1), data, shading="flat", cmap="viridis")
    figure.colorbar(heatmap, ax=sweep_ax, label="Measured power (mW)")
    best = max(result.search, key=lambda point: point.power_mw)
    sweep_ax.plot(best.frequency_mhz, best.rf_power_dbm, "r*", markersize=14, label="Measured maximum")
    sweep_ax.set(xlabel="RF frequency (MHz)", ylabel="RF power (dBm)", title="Frequency / power search")
    sweep_ax.legend()
    calibration = settings.calibration
    if calibration is None:
        raise ValueError("plot requires calibrated settings")
    x = np.linspace(settings.min_rf_power_dbm, settings.max_rf_power_dbm, 300)
    y = [calibration.mapping.forward(float(value)) / 100 * calibration.measured_full_scale_mw for value in x]
    response_ax.scatter(
        [point.rf_power_dbm for point in result.response],
        [point.power_mw for point in result.response],
        label="Measured means",
    )
    response_ax.plot(x, y, label=calibration.mapping.kind)
    response_ax.axvspan(
        settings.min_rf_power_dbm, settings.max_rf_power_dbm, alpha=0.1, color="green", label="Operating interval"
    )
    response_ax.set(
        xlabel="RF power (dBm)", ylabel="Optical power (mW)", title=f"Response at {settings.frequency_mhz:g} MHz"
    )
    response_ax.legend()
    figure.suptitle(f"{result.wavelength_nm:g} nm | Source reference {result.source_reference_mw:g} mW")
    figure.savefig(path, dpi=160)
