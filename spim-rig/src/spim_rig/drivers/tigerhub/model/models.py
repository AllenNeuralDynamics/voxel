from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import TypedDict


class ASIMode(Enum):
    TIGER = "tiger"
    MS2000 = "ms2000"


@dataclass
class Reply:
    kind: str  # "ACK" | "DATA" | "ERR"
    kv: dict[str, str] | None = None
    text: str | None = None
    err: str | None = None


class ASIDeviceType(StrEnum):
    XY_MOTOR = "x"  # XY xtage
    Z_MOTOR = "z"  # Z focus motor Drive. LS50s, Z scopes etc
    PIEZO = "p"  # Piezo Focus. ASIs ADEPT, Piezo DAC etc
    TURRET = "o"  # 	Objective Turret
    SLIDER = "f"  # Slider
    THETA = "t"  # Theta Stage
    MOTOR = "l"  # Generic linear motorized stage. TIRF, SISKIYOU etc
    PIEZO_LINEAR = "a"  # Generic linear piezo stage
    ZOOM = "m"  # Zoom magnification motor axis
    MICRO_MIRROR = "u"  # 	Micro Mirror, Scanner 75 etc
    FILTER_WHEEL = "w"  # Filter Wheel
    SHUTTER = "s"  # Shutter
    LOGIC = "g"  # Programmable Logic card
    MULTI_LED = "i"  # Multi LED Driver card
    LENS = "b"  # Tunable Lens
    DAC = "d"  # Digital to Analog converter(DAC)
    UNKNOWN = "u"  # Unknown device


class ASIAxisInfoDict(TypedDict):
    label: str
    device_type: str
    card_hex: int | None
    card_index: int | None
    props: int | None
    is_motor: bool
    axis_id: int | None
    enc_cnts_per_mm: float | None


@dataclass(frozen=True)
class ASIAxisInfo:
    label: str  # e.g. 'X'
    device_type: ASIDeviceType
    card_hex: int | None = None  # e.g. 31, 32, ...
    card_index: int | None = None  # 1-based “Axis Addr” from BU X
    props: int | None = None  # property bits from BU X
    axis_id: int | None = None  # Z2B
    enc_cnts_per_mm: float | None = None  # CNTS

    @property
    def is_motor(self) -> bool:
        return self.device_type in {
            ASIDeviceType.MOTOR,
            ASIDeviceType.XY_MOTOR,
            ASIDeviceType.Z_MOTOR,
        }

    def to_dict(self) -> ASIAxisInfoDict:
        return ASIAxisInfoDict(
            label=self.label,
            device_type=f"{self.device_type.name}({self.device_type.value})",
            card_hex=self.card_hex,
            card_index=self.card_index,
            props=self.props,
            is_motor=self.is_motor,
            axis_id=self.axis_id,
            enc_cnts_per_mm=self.enc_cnts_per_mm,
        )
