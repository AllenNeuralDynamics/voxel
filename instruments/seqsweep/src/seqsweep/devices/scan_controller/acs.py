"""ACS scan controller driver for the BARSeq XY stage.

Talks to the controller through the vendor ``SPiiPlusPython`` library (install the wheel from the SPiiPlus ADK Suite;
it is not redistributable). Connection, status, positioning and abort are implemented. Programming and running a
scan pass (``configure`` / ``run``) is still TODO.

Positions and speeds are in the controller's user units, which are assumed to be mm and mm/s.
"""

import re
import threading
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from rigup import describe
from seqsweep.job_model import DerivedScan, ScanDirection, ScanPassConfig
from vxlib.schema import FrozenModel

from .base import AxisStatus, ScanController, StageStatus, XYPosition

MST_ENABLE = 0x00000001  # Motor state flags (SPiiPlus Python manual, 6.16)
MST_INPOS = 0x00000010
MST_MOVE = 0x00000020
MST_ACC = 0x00000040
PST_RUN = 0x00000002  # Program state flag: the buffer is running (manual, ProgramStates)

SCAN_PASS_FILE = Path(__file__).with_name("scan_pass.acsp")  # ACSPL+ program for one strip pass
HOME_FILE = Path(__file__).with_name("home.acsp")  # ACSPL+ program that moves both axes to home_mm, with no limit check
NO_INDEX = -1  # ACSC_NONE: "global variable" buffer, and "no array index" for scalars
LCI_DECLARATION = "global LCI lc"  # the LCI struct the scan pass calls as lc.*
LCI_DECLARATION_PATTERN = re.compile(r"^\s*global\s+LCI\s+lc\b", re.IGNORECASE | re.MULTILINE)
CLEAR_ALL_LINES = 100_000
UPLOAD_BYTES = 65_536


class AcsControllerConfig(FrozenModel):
    """Connection, wiring and motion settings of the ACS controller (mm, mm/s). Every value comes from the config; no defaults."""

    communication_option: Literal["ethernet_tcp", "simulator"] = Field(
        description="How the host talks to the controller; 'simulator' uses the SPiiPlus stand-alone simulator"
    )
    address: str | None = Field(default=None, min_length=1, description="Controller IP or host name; ethernet_tcp only")
    port: int | None = Field(default=None, gt=0, le=65535, description="Controller TCP port (701 is the SPiiPlus stream port); ethernet_tcp only")
    axis_x: int = Field(ge=0, description="Controller axis index of the scan axis (X)")
    axis_y: int = Field(ge=0, description="Controller axis index of the strip axis (Y)")
    scan_buffer: int = Field(ge=0, description="Controller program buffer that holds the scan pass; it is overwritten on connect")
    home_buffer: int = Field(ge=0, description="Controller program buffer that holds the home move; it is overwritten on connect")
    d_buffer: int = Field(ge=0, description="Index of the controller's D-Buffer, where the global LCI struct is declared; depends on the firmware")
    line_pulse_width_ms: float = Field(gt=0, description="Width of each line trigger pulse")
    scan_accel: float = Field(gt=0, description="Acceleration of the scan axis")
    scan_decel: float = Field(gt=0, description="Deceleration of the scan axis")
    home_mm: tuple[float, float] = Field(description="Home position (X, Y); reached by the home buffer, so it may lie outside limits_mm")
    limits_mm: dict[Literal["x", "y"], tuple[float, float]] = Field(description="Reachable range per axis")

    @model_validator(mode="after")
    def _check_ranges(self) -> Self:
        if self.communication_option == "ethernet_tcp" and (self.address is None or self.port is None):
            raise ValueError("address and port are required when communication_option is ethernet_tcp")
        if self.scan_buffer == self.home_buffer:
            raise ValueError("scan_buffer and home_buffer must be different buffers")
        if max(self.scan_buffer, self.home_buffer) >= self.d_buffer:
            raise ValueError(f"scan_buffer and home_buffer must be below d_buffer {self.d_buffer}")
        for axis, (low, high) in self.limits_mm.items():
            if low >= high:
                raise ValueError(f"limits_mm.{axis} must be [min, max], got [{low}, {high}]")
        return self


class AcsController(ScanController):
    """The real ACS scan controller; the keyword arguments after ``move_velocity_mm_s`` are the ``AcsControllerConfig`` fields."""

    def __init__(self, uid: str, *, move_velocity_mm_s: float, motion_timeout_s: float, **config: object) -> None:
        super().__init__(uid, move_velocity_mm_s=move_velocity_mm_s, motion_timeout_s=motion_timeout_s)
        self._config = AcsControllerConfig.model_validate(config)
        self._lock = threading.RLock()  # one vendor handle: serialize calls and multi-call sequences
        self._sp = self._import_library()
        self._hc = -1
        self._pass: tuple[ScanPassConfig, DerivedScan] | None = None
        self._connect()
        self._enable_axes()
        self._load_scan_pass()
        self._load_home()

    # -- library and connection -------------------------------------------------------------------------------

    @staticmethod
    def _import_library():  # noqa: ANN205
        import numpy as np

        if not hasattr(np, "chararray"):  # the vendor wheel (UploadBuffer, GetErrorString) still uses the numpy 1 name
            np.chararray = np.char.chararray  # type: ignore[attr-defined]
        try:
            import SPiiPlusPython as sp  # type: ignore[import-not-found]
        except ImportError as e:
            raise ImportError(
                "SPiiPlusPython is not installed. Install the wheel from the SPiiPlus ADK Suite "
                "('SPiiPlus Python Library' folder); the SPiiPlus Runtime Kit is also required."
            ) from e
        return sp

    def _connect(self) -> None:
        """Open the channel to the controller, or to the SPiiPlus simulator."""
        sp = self._sp
        address, port = self._config.address, self._config.port
        simulated = self._config.communication_option == "simulator"
        target = "SPiiPlus simulator" if simulated else f"{address}:{port}"
        with self._lock:
            if simulated:
                self._hc = sp.OpenCommSimulator()
            elif address is None or port is None:
                raise ValueError("address and port are required for ethernet_tcp")  # also checked by the config
            else:
                self._hc = sp.OpenCommEthernetTCP(address, port)
            if self._hc == -1:
                error = sp.GetLastError()
                raise ConnectionError(f"Could not connect to the ACS controller ({target}), error {error}")
        self.log.info("Connected to ACS controller (%s)", target)

    def close(self) -> None:
        """Stop motion, close every gate, switch the axes off and close the connection."""
        if self._hc == -1:
            return
        try:
            self.abort()
            with self._lock:
                for axis in self._axes:
                    self._sp.Disable(self._hc, axis, self._sp.SYNCHRONOUS, True)
        finally:
            with self._lock:
                self._sp.CloseComm(self._hc, True)
                self._hc = -1
            self.log.info("Closed connection to ACS controller")

    def _enable_axes(self) -> None:
        with self._lock:
            for axis in self._axes:
                self._sp.Enable(self._hc, axis, self._sp.SYNCHRONOUS, True)
                self._sp.WaitMotorEnabled(self._hc, axis, 1, int(self._motion_timeout_s * 1000), True)
                self._sp.SetVelocity(self._hc, axis, self._move_velocity_mm_s, self._sp.SYNCHRONOUS, True)
                self._sp.SetAcceleration(self._hc, axis, self._config.scan_accel, self._sp.SYNCHRONOUS, True)
                self._sp.SetDeceleration(self._hc, axis, self._config.scan_decel, self._sp.SYNCHRONOUS, True)

    @property
    def _axes(self) -> tuple[int, int]:
        return self._config.axis_x, self._config.axis_y

    def _axis_index(self, axis: Literal["x", "y"]) -> int:
        return self._config.axis_x if axis == "x" else self._config.axis_y

    def _declare_lci(self) -> None:
        """Make sure the D-Buffer declares the LCI struct ``lc``; the scan pass uses it and structs must be global there."""
        sp = self._sp
        with self._lock:
            # The D-Buffer cannot change while another buffer is compiled, so decompile our buffers first.
            for buffer in (self._config.scan_buffer, self._config.home_buffer):
                sp.StopBuffer(self._hc, buffer, sp.SYNCHRONOUS, True)
                sp.ClearBuffer(self._hc, buffer, 1, CLEAR_ALL_LINES, sp.SYNCHRONOUS, True)
            d_buffer = self._config.d_buffer
            declarations = sp.UploadBuffer(self._hc, d_buffer, 0, UPLOAD_BYTES, sp.SYNCHRONOUS, True)
            if LCI_DECLARATION_PATTERN.search(declarations or ""):
                return
            sp.AppendBuffer(self._hc, d_buffer, LCI_DECLARATION + "\n", None, sp.SYNCHRONOUS, True)  # existing globals kept
            sp.CompileBuffer(self._hc, d_buffer, sp.SYNCHRONOUS, True)
        self.log.info("Declared '%s' in the controller D-Buffer", LCI_DECLARATION)

    def _load_scan_pass(self) -> None:
        """Load and compile the scan pass program; this also creates its global parameter variables."""
        sp = self._sp
        self._declare_lci()
        with self._lock:
            sp.LoadBuffer(self._hc, self._config.scan_buffer, SCAN_PASS_FILE.read_text(encoding="utf-8"), None, sp.SYNCHRONOUS, True)
            sp.CompileBuffer(self._hc, self._config.scan_buffer, sp.SYNCHRONOUS, True)

    def _load_home(self) -> None:
        """Load and compile the home program, then write its parameters once: home position, speed and axes never change."""
        sp = self._sp
        with self._lock:
            sp.LoadBuffer(self._hc, self._config.home_buffer, HOME_FILE.read_text(encoding="utf-8"), None, sp.SYNCHRONOUS, True)
            sp.CompileBuffer(self._hc, self._config.home_buffer, sp.SYNCHRONOUS, True)
        home_x_mm, home_y_mm = self._config.home_mm
        axis_x, axis_y = self._axes
        parameters: dict[str, float | int] = {
            "home_x_mm": home_x_mm,
            "home_y_mm": home_y_mm,
            "move_velocity_mm_s": self._move_velocity_mm_s,  # declared by the scan pass, which is loaded first
            "home_axis_x": axis_x,
            "home_axis_y": axis_y,
        }
        for name, value in parameters.items():
            self._write(name, value)

    def _write(self, name: str, value: float | int) -> None:
        """Write a global variable of the scan pass or home program."""
        write = self._sp.WriteInteger if isinstance(value, int) else self._sp.WriteReal
        with self._lock:
            write(self._hc, NO_INDEX, name, NO_INDEX, NO_INDEX, NO_INDEX, NO_INDEX, value, self._sp.SYNCHRONOUS, True)

    def _read(self, name: str) -> float:
        with self._lock:
            return self._sp.ReadReal(self._hc, NO_INDEX, name, NO_INDEX, NO_INDEX, NO_INDEX, NO_INDEX, self._sp.SYNCHRONOUS, True)

    # -- status -----------------------------------------------------------------------------------------------

    @property
    @describe(label="Position", desc="Feedback position in mm", units="mm", stream=True)
    def position_mm(self) -> XYPosition:
        with self._lock:
            x, y = (self._sp.GetFPosition(self._hc, axis, self._sp.SYNCHRONOUS, True) for axis in self._axes)
        return XYPosition(x=x, y=y)

    @property
    @describe(label="Running", desc="Whether a pass, the home move or any axis motion is in progress", stream=True)
    def is_running(self) -> bool:
        sp = self._sp
        with self._lock:  # short: a few vendor reads, so abort() is never kept waiting
            program_running = any(
                sp.GetProgramState(self._hc, buffer, sp.SYNCHRONOUS, True) & PST_RUN
                for buffer in (self._config.scan_buffer, self._config.home_buffer)
            )
            moving = any(sp.GetMotorState(self._hc, axis, sp.SYNCHRONOUS, True) & MST_MOVE for axis in self._axes)
        return program_running or moving

    @describe(label="Read Status", desc="Per-axis motor state and faults")
    def read_status(self) -> StageStatus:
        """Motor state and faults of the X and Y axes."""
        sp = self._sp
        axes: dict[str, AxisStatus] = {}
        with self._lock:
            for name, axis in zip(("x", "y"), self._axes, strict=True):
                state = sp.GetMotorState(self._hc, axis, sp.SYNCHRONOUS, True)
                axes[name] = AxisStatus(
                    enabled=bool(state & MST_ENABLE),
                    in_position=bool(state & MST_INPOS),
                    moving=bool(state & MST_MOVE),
                    accelerating=bool(state & MST_ACC),
                    fault=sp.GetFault(self._hc, axis, sp.SYNCHRONOUS, True),
                    motor_error=sp.GetMotorError(self._hc, axis, sp.SYNCHRONOUS, True),
                )
        return StageStatus(**axes)

    # -- motion -----------------------------------------------------------------------------------------------

    @describe(label="Move To", desc="Move to an absolute (X, Y) position in mm; returns once the move has started")
    def move_abs(self, x_mm: float, y_mm: float, velocity_mm_s: float | None = None) -> None:
        """Start the move; ``velocity_mm_s`` None keeps the current axis velocity (the positioning speed between passes)."""
        if velocity_mm_s is not None and velocity_mm_s <= 0:
            raise ValueError("velocity_mm_s must be positive")
        self._check_in_limits("x", x_mm)
        self._check_in_limits("y", y_mm)
        axis_x, axis_y = self._axes
        with self._lock:
            if velocity_mm_s is not None:
                for axis in self._axes:
                    self._sp.SetVelocity(self._hc, axis, velocity_mm_s, self._sp.SYNCHRONOUS, True)
            self._sp.ToPointM(self._hc, 0, [axis_x, axis_y, -1], [x_mm, y_mm], self._sp.SYNCHRONOUS, True)

    @describe(label="Move By", desc="Move by a relative (X, Y) step in mm; returns once the move has started")
    def move_rel(self, dx_mm: float, dy_mm: float) -> None:
        # Target from the feedback position, so the limit check sees the real destination.
        position = self.position_mm
        self.move_abs(position.x + dx_mm, position.y + dy_mm)

    @describe(label="Go Home", desc="Start the home buffer to home_mm (not limited by limits_mm); returns once it has started")
    def go_home(self) -> None:
        with self._lock:
            self._sp.RunBuffer(self._hc, self._config.home_buffer, None, self._sp.SYNCHRONOUS, True)

    @describe(label="Abort", desc="Stop the pass and close every gate; safe when idle")
    def abort(self) -> None:
        sp = self._sp
        with self._lock:
            sp.StopBuffer(self._hc, self._config.scan_buffer, sp.SYNCHRONOUS, True)
            sp.StopBuffer(self._hc, self._config.home_buffer, sp.SYNCHRONOUS, True)
            for axis in self._axes:
                sp.Halt(self._hc, axis, sp.SYNCHRONOUS, True)
                # An aborted pass leaves the scan axis at the scan speed; later moves use the current velocity
                sp.SetVelocity(self._hc, axis, self._move_velocity_mm_s, sp.SYNCHRONOUS, True)

    def _check_in_limits(self, axis: Literal["x", "y"], position_mm: float) -> None:
        low, high = self._config.limits_mm[axis]
        if not low <= position_mm <= high:
            raise ValueError(f"{axis} position {position_mm} mm is outside the limits [{low}, {high}]")

    # -- scan pass --------------------------------------------------------------------------------------------

    @describe(label="Configure Scan", desc="Load pass geometry and gating")
    def configure(self, config: ScanPassConfig, derived: DerivedScan) -> None:
        low, high = self._config.limits_mm[derived.scan_axis]
        parameters: dict[str, float | int] = {
            "scan_margin_mm": derived.scan_margin_mm,
            "pixel_size_mm": derived.pixel_size_um / 1000,
            "scan_speed_mm_s": derived.scan_speed_mm_s,
            "line_pulse_width_ms": self._config.line_pulse_width_ms,
            "move_velocity_mm_s": self._move_velocity_mm_s,
            "scan_accel": self._config.scan_accel,
            "scan_decel": self._config.scan_decel,
            "limit_min_mm": low,
            "limit_max_mm": high,
            "scan_axis": self._axis_index(derived.scan_axis),}
        for name, value in parameters.items():
            self._write(name, value)
        self._pass = (config, derived)

    @describe(label="Run Pass", desc="Start one strip pass in the given direction")
    def run(self, direction: ScanDirection) -> None:
        """Start the pass and return; ``is_running`` reports when it ends."""
        if self._pass is None:
            raise RuntimeError("configure() must be called before run()")
        config, _ = self._pass
        start_mm, end_mm = config.scan_start_mm, config.scan_end_mm
        if direction is ScanDirection.REVERSE:
            start_mm, end_mm = end_mm, start_mm
        self._write("scan_start_mm", start_mm)
        self._write("scan_end_mm", end_mm)
        self._write("scan_dir", 1 if end_mm >= start_mm else -1)
        with self._lock:
            self._sp.RunBuffer(self._hc, self._config.scan_buffer, None, self._sp.SYNCHRONOUS, True)

    @property
    @describe(label="Line pulses", desc="Line pulses fired in the last pass")
    def pulse_count(self) -> int:
        return int(self._read("pulse_count"))
