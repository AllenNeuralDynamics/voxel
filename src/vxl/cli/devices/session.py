"""The devices of a rig file, opened on demand, plus stopping and closing."""

import asyncio
from collections.abc import Coroutine, Mapping
from pathlib import Path
from typing import Any

from rigup.config import DeviceConfig, RigConfig
from rigup.device import Device, DeviceController
from vxlib.issues import Problem

from rigup import build_objects
from vxl._utils.files import load_yaml


def load_configs(path: Path) -> dict[str, DeviceConfig]:
    """Read every device of a rig file, such as an instrument's ``rig.yaml``, in its own process or on a node."""
    data = load_yaml(path) or {}
    rig = RigConfig.model_validate({key: data[key] for key in ("devices", "nodes") if key in data})
    configs = rig.all_devices
    if not configs:
        raise ValueError(f"No devices found in {path}")
    return configs


class Session:
    """All configs from one file and the devices opened from them, in dependency order, each with its controller."""

    def __init__(self, configs: dict[str, DeviceConfig]) -> None:
        self.configs = configs
        self.devices: dict[str, Device] = {}
        self.controllers: dict[str, DeviceController[Any]] = {}
        self._runner = asyncio.Runner()

    def run[R](self, call: Coroutine[Any, Any, R]) -> R:
        """Wait for a controller call."""
        return self._runner.run(call)

    def open(self, uid: str) -> tuple[list[str], dict[str, Problem]]:
        """Build a device and its unopened dependencies; open dependencies are passed in as objects."""
        pending = {name: self._inject(config) for name, config in self._pending(uid).items()}
        built, errors = build_objects(pending, Device)
        self.devices.update(built)
        for name, device in built.items():
            self.controllers[name] = device.make_controller()
        return list(built), dict(errors)

    def close(self) -> dict[str, Exception]:
        """Close dependents before their dependencies and return failures by UID."""
        errors: dict[str, Exception] = {}
        for uid, controller in reversed(self.controllers.items()):
            try:
                self.run(controller.close())
            except Exception as error:
                errors[uid] = error
        self._runner.close()
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


async def stop(controller: DeviceController[Any]) -> bool:
    """Run every failsafe operation of a device; return False when it has none."""
    names = [name for name, info in controller.interface.operations.items() if info.intent == "failsafe"]
    errors = [error for name in names if (error := (await controller.execute(name)).error) is not None]
    if errors:
        raise RuntimeError("; ".join(errors))
    return bool(names)


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
