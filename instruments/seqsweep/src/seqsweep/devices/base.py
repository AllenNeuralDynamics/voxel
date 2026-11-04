from enum import StrEnum


class SeqSweepDeviceType(StrEnum):
    """Device types for SeqSweep-only contracts. Contracts that extend a ``vxl`` base keep its ``DeviceType``."""

    SCAN_CONTROLLER = "scan_controller"
    TDI_CAMERA = "tdi_camera"
    Z_RAMP_AXIS = "z_ramp_axis"
    TUNABLE_LENS = "tunable_lens"
