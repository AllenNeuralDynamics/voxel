from dataclasses import dataclass
from enum import Enum

from voxel_drivers.tigerhub.model import BoxInfo, Reply
from voxel_drivers.tigerhub.protocol.errors import ASIDecodeError
from voxel_drivers.tigerhub.protocol.linefmt import _fmt_kv, _line

# --- Dataclasses ---


@dataclass(frozen=True)
class ScanRConfig:
    """
    Fast-axis (horizontal line) setup.

    Exactly one of stop_mm or num_pixels must be provided.

    Encodings:
      X = start position [mm]
      Y = stop position [mm]                (if using distance mode)
      Z = encoder ticks between pulses      (derived from pulse_interval_um)
      F = number of pixels                  (if using pixel-count mode)
      R = retrace speed [%]                 (optional)
    """

    start_mm: float
    pulse_interval_um: float
    stop_mm: float | None = None
    num_pixels: int | None = None
    retrace_speed_percent: int | None = 67

    def validate(self) -> None:
        if (self.stop_mm is None) == (self.num_pixels is None):
            raise ValueError("Exactly one of stop_mm or num_pixels must be set.")
        if self.pulse_interval_um <= 0:
            raise ValueError("pulse_interval_um must be > 0.")
        if self.num_pixels is not None and self.num_pixels <= 0:
            raise ValueError("num_pixels must be > 0.")
        if self.retrace_speed_percent is not None and not (0 <= int(self.retrace_speed_percent) <= 100):
            raise ValueError("retrace_speed_percent must be in [0, 100].")

    def to_kv(self, info: BoxInfo, fast_axis_uid: str) -> tuple[dict[str, object], float]:
        """
        Returns (kv, actual_interval_um).
        Uses BoxInfo.axes[fast_axis_uid].enc_cnts_per_mm to compute Z (ticks/pulse).
        """
        self.validate()
        ax = info.axes.get(fast_axis_uid.upper())
        if ax is None or ax.enc_cnts_per_mm is None:
            err = f"Missing enc_cnts_per_mm for axis {fast_axis_uid!r}."
            raise RuntimeError(err)

        ticks_per_mm = ax.enc_cnts_per_mm
        ticks_per_um = ticks_per_mm * 1e-3
        enc_divide_f = ticks_per_um * self.pulse_interval_um
        enc_divide = max(1, round(enc_divide_f))
        actual_interval_um = enc_divide / ticks_per_um  # what the hardware will do

        kv: dict[str, object] = {
            "X": round(self.start_mm, 4),
            "Z": enc_divide,
        }
        if self.stop_mm is not None:
            kv["Y"] = round(self.stop_mm, 4)
        if self.num_pixels is not None:
            kv["F"] = int(self.num_pixels)
        if self.retrace_speed_percent is not None:
            kv["R"] = int(self.retrace_speed_percent)
        return kv, float(actual_interval_um)


@dataclass(frozen=True)
class ScanVConfig:
    """
    Slow-axis (vertical stepping) setup.

    Encodings:
      X = start position [mm]
      Y = stop position [mm]
      Z = number of lines
      F = extra settle time (ms)            (optional)
      T = overshoot factor (distance scale) (optional)
    """

    start_mm: float
    stop_mm: float
    line_count: int
    overshoot_time_ms: int | None = None
    overshoot_factor: float | None = None

    def validate(self) -> None:
        if self.line_count <= 0:
            raise ValueError("line_count must be > 0.")
        if self.overshoot_time_ms is not None and self.overshoot_time_ms < 0:
            raise ValueError("overshoot_time_ms must be >= 0.")
        if self.overshoot_factor is not None and self.overshoot_factor < 0:
            raise ValueError("overshoot_factor must be >= 0.")

    def to_kv(self) -> dict[str, object]:
        self.validate()
        kv: dict[str, object] = {
            "X": round(self.start_mm, 4),
            "Y": round(self.stop_mm, 4),
            "Z": int(self.line_count),
        }
        if self.overshoot_time_ms is not None:
            kv["F"] = int(self.overshoot_time_ms)
        if self.overshoot_factor is not None:
            kv["T"] = round(self.overshoot_factor, 4)
        return kv


class ScanPattern(Enum):
    RASTER = 0
    SERPENTINE = 1


# --- Ops ---


class ScanBindAxesOp:
    """
    SCAN axis binding/config:
      X? (unused here)
      Y = fast_axis_id
      Z = slow_axis_id
      F = pattern (0=raster, 1=serpentine)
    """

    @staticmethod
    def encode(
        card_hex: int, *, fast_axis_id: int | None, slow_axis_id: int | None, pattern: ScanPattern | None
    ) -> bytes:
        kv = {}
        if fast_axis_id is not None:
            kv["Y"] = int(fast_axis_id)
        if slow_axis_id is not None:
            kv["Z"] = int(slow_axis_id)
        if pattern is not None:
            kv["F"] = int(pattern.value)
        payload = _fmt_kv(kv) if kv else None
        return _line("SCAN", payload, card_hex)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("SCAN (bind axes)", r)


class ScanROp:
    @staticmethod
    def encode(card_hex: int, kv: dict[str, object]) -> bytes:
        return _line("SCANR", _fmt_kv(kv), card_hex)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("SCANR", r)


class ScanVOp:
    @staticmethod
    def encode(card_hex: int, kv: dict[str, object]) -> bytes:
        return _line("SCANV", _fmt_kv(kv), card_hex)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("SCANV", r)


class ScanRunOp:
    @staticmethod
    def encode(card_hex: int, action: str) -> bytes:
        # action: 'S' (start) or 'P' (stop)
        return _line("SCAN", action, card_hex)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("SCAN run/stop", r)


# --- Array Scan ---
@dataclass(frozen=True)
class ArrayScanConfig:
    x_points: int = 0
    delta_x_mm: float = 0.0
    y_points: int = 0
    delta_y_mm: float = 0.0
    theta_deg: float = 0.0

    pattern: ScanPattern = ScanPattern.RASTER

    def to_kv(self) -> dict[str, object]:
        # AR expects: X=x_points, Y=y_points, Z=Δx, F=Δy, T=θ
        return {
            "X": int(self.x_points),
            "Y": int(self.y_points),
            "Z": round(self.delta_x_mm, 4),
            "F": round(self.delta_y_mm, 4),
            "T": round(self.theta_deg, 3),
        }


class ArrayOp:  # "AR" (ARRAY)
    """Array / table-style configuration on a card."""

    @staticmethod
    def encode(addr: int, cfg: ArrayScanConfig | None) -> bytes:
        payload = _fmt_kv(cfg.to_kv()) if cfg is not None else "S"  # 'S' to start
        return _line(verb="AR", payload=payload, addr=addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("AR", r)


@dataclass(frozen=True)
class AutoHomeConfig:
    x_start_mm: float | None = None
    y_start_mm: float | None = None

    def to_kv(self) -> dict[str, object]:
        kv: dict[str, object] = {}
        if self.x_start_mm is not None:
            kv["X"] = round(self.x_start_mm, 4)
        if self.y_start_mm is not None:
            kv["Y"] = round(self.y_start_mm, 4)
        return kv


class AutoHomeOp:  # "AH" (AHOME)
    """Per-card auto-home helpers (different from axis '!' HOME)."""

    @staticmethod
    def encode(addr: int, cfg: AutoHomeConfig) -> bytes:
        return _line("AH", _fmt_kv(cfg.to_kv()), addr)

    @staticmethod
    def decode(r: Reply) -> None:
        if r.kind == "ERR":
            raise ASIDecodeError("AH", r)
