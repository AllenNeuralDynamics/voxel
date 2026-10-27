"""Device configs from a rig or instrument file, opened on demand, plus stopping and closing."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from rigup import BuildError, Device, DeviceConfig, RigConfig, build_objects
from vxl.devices.axes.continuous.base import ContinuousAxis
from vxl.devices.axes.discrete.base import DiscreteAxis
from vxl.devices.camera.base import Camera
from vxl.devices.laser.source import CurrentControlledLaserSource, LaserSource


def load_configs(path: Path) -> dict[str, DeviceConfig]:
    """Read every device of a rig file, or of an instrument file's hal section."""
    data = yaml.safe_load(path.read_text()) or {}
    section = data.get("hal", data)
    rig = RigConfig.model_validate({key: section[key] for key in ("devices", "nodes") if key in section})
    configs = dict(rig.devices)
    for node in rig.nodes.values():
        configs.update(node.devices)
    if not configs:
        raise ValueError(f"No devices found in {path}")
    return configs


class Session:
    """All configs from one file and the devices opened from them, in dependency order."""

    def __init__(self, configs: dict[str, DeviceConfig]) -> None:
        self.configs = configs
        self.devices: dict[str, Device] = {}

    def open(self, uid: str) -> tuple[list[str], dict[str, BuildError]]:
        """Build a device and its unopened dependencies; open dependencies are passed in as objects."""
        pending = {name: self._inject(config) for name, config in self._pending(uid).items()}
        built, errors = build_objects(pending, Device)
        self.devices.update(built)
        return list(built), dict(errors)

    def close(self) -> dict[str, Exception]:
        """Close dependents before their dependencies and return failures by UID."""
        errors: dict[str, Exception] = {}
        for uid, device in reversed(self.devices.items()):
            try:
                device.close()
            except Exception as error:
                errors[uid] = error
        return errors

    def _pending(self, uid: str) -> dict[str, DeviceConfig]:
        pending: dict[str, DeviceConfig] = {}

        def visit(name: str) -> None:
            if name in pending or name in self.devices:
                return
            if name not in self.configs:
                raise ValueError(f"Unknown device {name!r}")
            pending[name] = self.configs[name]
            for dependency in _references(self.configs[name].init, self.configs):
                visit(dependency)

        visit(uid)
        return pending

    def _inject(self, config: DeviceConfig) -> DeviceConfig:
        return config.model_copy(update={"init": _resolve(config.init, self.devices)})


def stop(device: Device) -> bool:
    """Put a device in its safe state; return False when its type has none."""
    match device:
        case LaserSource() | CurrentControlledLaserSource():
            device.source_disable()
        case ContinuousAxis() | DiscreteAxis():
            device.halt()
        case Camera():
            device.stop()
        case _:
            return False
    return True


def _references(value: Any, configs: Mapping[str, DeviceConfig]) -> set[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = value.values()
    else:
        return {value} if isinstance(value, str) and value in configs else set()
    return {uid for item in items for uid in _references(item, configs)}


def _resolve(value: Any, devices: Mapping[str, Device]) -> Any:
    if isinstance(value, str):
        return devices.get(value, value)
    if isinstance(value, list):
        return [_resolve(item, devices) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item, devices) for key, item in value.items()}
    return value
