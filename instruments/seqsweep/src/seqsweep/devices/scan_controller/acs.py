"""ACS scan controller driver for the BARSeq XY stage.

Talks to the controller through the vendor ``SPiiPlusPython`` library (install the wheel from the SPiiPlus ADK Suite;
it is not redistributable). Connection, status, positioning and abort are implemented. Programming and running a
scan pass (``configure`` / ``run``) is still TODO.

Positions and speeds are in the controller's user units, which are assumed to be mm and mm/s.
"""

import re
import threading
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator
from rigup import describe
from vxlib.schema import FrozenModel

from .base import ScanController

OUTPUT_PATTERN = re.compile(r"OUT\d+\.\d+")
AcsOutput = Annotated[str, StringConstraints(pattern=OUTPUT_PATTERN.pattern)]
"""A digital output bit as ``OUT<port>.<bit>``, e.g. ``OUT0.1``."""

MST_ENABLE = 0x00000001  # Motor state flags (SPiiPlus Python manual, 6.16)
MST_INPOS = 0x00000010
MST_MOVE = 0x00000020
MST_ACC = 0x00000040

MOTION_TIMEOUT_MS = 60_000


class AcsStageConfig(FrozenModel):
    """Connection, wiring and motion settings of the ACS stage (mm, mm/s). Every value comes from the config; no defaults."""

    communication_option: Literal["ethernet_tcp"] = Field(description="How the host talks to the controller")
    address: str = Field(min_length=1, description="Controller network address, IP or host name")
    port: int = Field(gt=0, le=65535, description="Controller TCP port (701 is the SPiiPlus stream port)")
    axis_x: int = Field(ge=0, description="Controller axis index of the scan axis (X)")
    axis_y: int = Field(ge=0, description="Controller axis index of the strip axis (Y)")
    frame_trigger_output: AcsOutput = Field(description="Output driving the frame trigger to the grabber")
    direction_output: AcsOutput = Field(description="Output telling the camera the scan direction")
    line_pulse_width_ms: float = Field(gt=0, description="Width of each line trigger pulse")
    scan_accel: float = Field(gt=0, description="Acceleration of the scan axis")
    scan_decel: float = Field(gt=0, description="Deceleration of the scan axis")
    move_velocity_mm_s: float = Field(gt=0, description="Speed of positioning moves, not scans")
    origin_mm: tuple[float, float] = Field(description="Home position (X, Y)")
    limits_mm: dict[Literal["x", "y"], tuple[float, float]] = Field(description="Reachable range per axis")

    @model_validator(mode="after")
    def _check_ranges(self) -> Self:
        if self.frame_trigger_output == self.direction_output:
            raise ValueError(f"frame_trigger_output and direction_output must differ, both are {self.direction_output}")
        for axis, (low, high) in self.limits_mm.items():
            if low >= high:
                raise ValueError(f"limits_mm.{axis} must be [min, max], got [{low}, {high}]")
        return self


def _split_output(output: str) -> tuple[int, int]:
    """``'OUT0.1'`` -> ``(0, 1)``: the (port, bit) the library expects."""
    port, bit = output.removeprefix("OUT").split(".")
    return int(port), int(bit)


class AcsController(ScanController):
    """The real ACS scan controller; the keyword arguments after ``gate_outputs`` are the ``AcsStageConfig`` fields."""

    def __init__(self, uid: str, *, gate_outputs: dict[str, str], **stage: object) -> None:
        super().__init__(uid, gate_outputs=gate_outputs)
        self._stage = AcsStageConfig.model_validate(stage)
        self._lock = threading.RLock()  # one vendor handle: serialize calls and multi-call sequences
        self._sp = self._import_library()
        self._hc = -1
        self._connect()
        self._enable_axes()

    # -- library and connection -------------------------------------------------------------------------------

    @staticmethod
    def _import_library():  # noqa: ANN205
        try:
            import SPiiPlusPython as sp  # type: ignore[import-not-found]
        except ImportError as e:
            raise ImportError(
                "SPiiPlusPython is not installed. Install the wheel from the SPiiPlus ADK Suite "
                "('SPiiPlus Python Library' folder); the SPiiPlus Runtime Kit is also required."
            ) from e
        return sp

    def _connect(self) -> None:
        """Open the Ethernet TCP channel to the controller."""
        sp = self._sp
        with self._lock:
            self._hc = sp.OpenCommEthernetTCP(self._stage.address, self._stage.port)
            if self._hc == -1:
                error = sp.GetLastError()
                raise ConnectionError(
                    f"Could not connect to the ACS controller at {self._stage.address}:{self._stage.port} "
                    f"(error {error})"
                )
        self.log.info("Connected to ACS controller at %s:%d", self._stage.address, self._stage.port)

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
                self._sp.WaitMotorEnabled(self._hc, axis, 1, MOTION_TIMEOUT_MS, True)
                self._sp.SetVelocity(self._hc, axis, self._stage.move_velocity_mm_s, self._sp.SYNCHRONOUS, True)
                self._sp.SetAcceleration(self._hc, axis, self._stage.scan_accel, self._sp.SYNCHRONOUS, True)
                self._sp.SetDeceleration(self._hc, axis, self._stage.scan_decel, self._sp.SYNCHRONOUS, True)

    @property
    def _axes(self) -> tuple[int, int]:
        return self._stage.axis_x, self._stage.axis_y

    # -- status -----------------------------------------------------------------------------------------------

    @property
    @describe(label="Position", desc="Feedback position (X, Y) in mm", stream=True)
    def position_mm(self) -> tuple[float, float]:
        with self._lock:
            x, y = (self._sp.GetFPosition(self._hc, axis, self._sp.SYNCHRONOUS, True) for axis in self._axes)
        return x, y

    @property
    @describe(label="Running", desc="Whether a pass is in progress", stream=True)
    def is_running(self) -> bool:
        return any(state["moving"] for state in self.read_status().values())

    @describe(label="Read Status", desc="Per-axis position, motor state and faults")
    def read_status(self) -> dict[str, dict[str, float | bool | int]]:
        """Status of the X and Y axes: ``{'x': {...}, 'y': {...}}``."""
        sp = self._sp
        status: dict[str, dict[str, float | bool | int]] = {}
        with self._lock:
            for name, axis in zip(("x", "y"), self._axes, strict=True):
                state = sp.GetMotorState(self._hc, axis, sp.SYNCHRONOUS, True)
                status[name] = {
                    "position_mm": sp.GetFPosition(self._hc, axis, sp.SYNCHRONOUS, True),
                    "enabled": bool(state & MST_ENABLE),
                    "in_position": bool(state & MST_INPOS),
                    "moving": bool(state & MST_MOVE),
                    "accelerating": bool(state & MST_ACC),
                    "fault": sp.GetFault(self._hc, axis, sp.SYNCHRONOUS, True),
                    "motor_error": sp.GetMotorError(self._hc, axis, sp.SYNCHRONOUS, True),
                }
        return status

    @describe(label="Read Output", desc="State of a digital output, e.g. OUT0.1")
    def read_output(self, output: str) -> bool:
        port, bit = _split_output(self._validated_output(output))
        with self._lock:
            return bool(self._sp.GetOutput(self._hc, port, bit, self._sp.SYNCHRONOUS, True))

    @describe(label="Set Output", desc="Set a digital output, e.g. OUT0.1")
    def set_output(self, output: str, value: bool) -> None:
        port, bit = _split_output(self._validated_output(output))
        with self._lock:
            self._sp.SetOutput(self._hc, port, bit, int(value), self._sp.SYNCHRONOUS, True)

    @staticmethod
    def _validated_output(output: str) -> str:
        if not OUTPUT_PATTERN.fullmatch(output):
            raise ValueError(f"Output must look like 'OUT0.1', got {output!r}")
        return output

    # -- motion -----------------------------------------------------------------------------------------------

    @describe(label="Set Motion", desc="Speed (mm/s), acceleration and deceleration for later moves")
    def set_motion(self, velocity_mm_s: float, accel: float, decel: float) -> None:
        if min(velocity_mm_s, accel, decel) <= 0:
            raise ValueError("velocity, accel and decel must be positive")
        with self._lock:
            for axis in self._axes:
                self._sp.SetVelocity(self._hc, axis, velocity_mm_s, self._sp.SYNCHRONOUS, True)
                self._sp.SetAcceleration(self._hc, axis, accel, self._sp.SYNCHRONOUS, True)
                self._sp.SetDeceleration(self._hc, axis, decel, self._sp.SYNCHRONOUS, True)

    @describe(label="Move To", desc="Move to an absolute (X, Y) position in mm; returns once the move has started")
    def move_to(self, x_mm: float, y_mm: float) -> None:
        self._check_in_limits("x", x_mm)
        self._check_in_limits("y", y_mm)
        axis_x, axis_y = self._axes
        with self._lock:
            self._sp.ToPointM(self._hc, 0, [axis_x, axis_y, -1], [x_mm, y_mm], self._sp.SYNCHRONOUS, True)

    @describe(label="Move By", desc="Move by a relative (X, Y) step in mm; returns once the move has started")
    def move_by(self, dx_mm: float, dy_mm: float) -> None:
        # Target from the feedback position, so the limit check sees the real destination.
        x_mm, y_mm = self.position_mm
        self.move_to(x_mm + dx_mm, y_mm + dy_mm)

    @describe(label="Go Home", desc="Move to the configured origin")
    def go_home(self) -> None:
        self.move_to(*self._stage.origin_mm)

    @describe(label="Wait Motion End", desc="Block until both axes have settled")
    def wait_motion_end(self, timeout_ms: int = MOTION_TIMEOUT_MS) -> None:
        with self._lock:
            for axis in self._axes:
                self._sp.WaitMotionEnd(self._hc, axis, timeout_ms, True)

    @describe(label="Abort", desc="Stop the pass and close every gate; safe when idle")
    def abort(self) -> None:
        sp = self._sp
        with self._lock:
            for axis in self._axes:
                sp.Halt(self._hc, axis, sp.SYNCHRONOUS, True)
            for output in (*self._gate_outputs.values(), self._stage.frame_trigger_output):
                self._clear_output(output)

    def _clear_output(self, output: str) -> None:
        """Drive an output low: a single bit (``OUT0.1``) or a whole port (``OUT0``)."""
        sp = self._sp
        if "." in output:
            port, bit = _split_output(output)
            sp.SetOutput(self._hc, port, bit, 0, sp.SYNCHRONOUS, True)
        else:
            sp.SetOutputPort(self._hc, int(output.removeprefix("OUT")), 0, sp.SYNCHRONOUS, True)

    def _check_in_limits(self, axis: Literal["x", "y"], position_mm: float) -> None:
        low, high = self._stage.limits_mm[axis]
        if not low <= position_mm <= high:
            raise ValueError(f"{axis} position {position_mm} mm is outside the limits [{low}, {high}]")

    # TODO: configure(config, derived) and run(direction): program the scan pass (constant-velocity move with line
    # triggers on frame_trigger_output via PEG, direction on direction_output, laser gates on gate_outputs).
