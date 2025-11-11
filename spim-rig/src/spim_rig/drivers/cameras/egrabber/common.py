import logging
from dataclasses import dataclass, field
from typing import Any

from egrabber import (
    EGenTL,
    EGrabber,
    EGrabberDiscovery,
    RemoteModule,
    StreamModule,
)
from pyrig.utils import thread_safe_singleton


@thread_safe_singleton
def get_egentl_singleton() -> EGenTL:
    return EGenTL()


@dataclass
class EgrabberDevice:
    grabber: EGrabber
    remote: RemoteModule
    stream: StreamModule
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("EgrabberDevice"))

    def fetch_remote[T](self, feature: str, dtype: type[T]) -> T:
        value = self.remote.get(feature=feature, dtype=dtype)
        if value is None:
            err = f"Failed to get remote property: {feature}"
            raise RuntimeError(err)
        return value

    def set_remote(self, feature: str, value: Any) -> None:
        if not self.remote:
            self.logger.error("Unable to set %s. Remote component is not available.", feature)
            return
        self.remote.set(feature=feature, value=value)


def fetch_devices() -> dict[str, "EgrabberDevice"]:
    devices: dict[str, EgrabberDevice] = {}

    gentl = get_egentl_singleton()
    discovery = EGrabberDiscovery(gentl=gentl)
    discovery.discover()
    for cam in discovery.cameras:
        grabber = EGrabber(data=cam)
        remote = grabber.remote
        stream = grabber.stream
        if remote and stream and (ser := remote.get("DeviceSerialNumber", dtype=str)):
            devices[ser] = EgrabberDevice(grabber=grabber, remote=remote, stream=stream)
    return devices


def get_dev_by_serial(serial_number: str) -> "EgrabberDevice":
    devices = fetch_devices()
    if serial_number not in devices:
        err = f"Serial number {serial_number} not found. Available devices: {list(devices.keys())}"
        raise RuntimeError(err)
    return devices[serial_number]


@dataclass
class Binning:
    raw: str = "X1"
    raw_options: list[str] = field(default_factory=lambda: ["X1"])

    @property
    def value(self) -> int:
        return self.parse_str(self.raw)

    @property
    def options(self) -> list[int]:
        sorted_options = sorted([self.parse_str(b) for b in set(self.raw_options)])
        return list(sorted_options)

    @staticmethod
    def parse_str(binning_str: str) -> int:
        try:
            return int(binning_str[1:])
        except (ValueError, IndexError) as e:
            err_msg = f"Invalid binning string: {binning_str}"
            raise ValueError(err_msg) from e


@dataclass
class MinMaxIncProp:
    val: float
    min: float
    max: float
    inc: float = 1.0


@dataclass
class MinMaxProp:
    val: float
    min: float
    max: float


@dataclass
class ExposureTime(MinMaxIncProp):
    pass
