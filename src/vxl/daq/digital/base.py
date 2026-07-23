"""Vendor-neutral on-demand digital-output API."""

import time
from abc import abstractmethod
from collections.abc import Mapping
from typing import ClassVar

from rigup import Device, DeviceController, DeviceHandle, describe
from vxl.device import DeviceType


class OnDemandDOController(DeviceController["OnDemandDO"]):
    """Thin async orchestration for software-timed digital output."""

    @describe(label="Set State", desc="Set one digital output line high or low")
    async def set_state(self, line: str, state: bool) -> None:
        await self._run_sync(self.device.set_state, line, state)

    @describe(label="Set States", desc="Set one or more digital output lines")
    async def set_states(self, states: Mapping[str, bool]) -> None:
        await self._run_sync(self.device.set_states, states)

    @describe(label="Pulse", desc="Drive a digital line briefly, then return it to rest")
    async def pulse(
        self,
        line: str,
        duration_s: float,
        active: bool = True,
        rest: bool = False,
    ) -> None:
        await self._run_sync(self.device.pulse, line, duration_s, active=active, rest=rest)

    @describe(label="Reset", desc="Release all digital outputs")
    async def reset(self) -> None:
        await self._run_sync(self.device.reset)


class OnDemandDO(Device):
    """Abstract software-timed digital output.

    ``lines`` maps stable logical names to vendor-specific physical terminals.
    Boolean values represent electrical logic levels: ``True`` is high and
    ``False`` is low. A mapping update may include any subset of the declared lines;
    omitted lines retain their current state.
    """

    __DEVICE_TYPE__: ClassVar[str] = DeviceType.DAQ_ON_DEMAND_DO
    __CONTROLLER_TYPE__: ClassVar[type] = OnDemandDOController

    def __init__(self, uid: str, *, lines: Mapping[str, str]) -> None:
        super().__init__(uid=uid)
        self._lines: dict[str, str] = dict(lines)

    @property
    @describe(label="Lines", desc="Logical name -> physical digital output line")
    def lines(self) -> dict[str, str]:
        return dict(self._lines)

    def _validate(self, states: Mapping[str, bool]) -> None:
        for line, state in states.items():
            if line not in self._lines:
                raise ValueError(f"Unknown line '{line}' on {self.uid}: {sorted(self._lines)}")
            if not isinstance(state, bool):
                raise TypeError(f"State for line '{line}' must be bool, got {type(state).__name__}")

    @abstractmethod
    def set_states(self, states: Mapping[str, bool]) -> None:
        """Set a subset of declared lines; omitted lines retain their current state."""

    @abstractmethod
    def reset(self) -> None:
        """Release the output task and its physical lines."""

    def close(self) -> None:
        """Framework shutdown hook."""
        self.reset()

    def set_state(self, line: str, state: bool) -> None:
        """Set one declared line high or low."""
        self.set_states({line: state})

    def pulse(
        self,
        line: str,
        duration_s: float,
        *,
        active: bool = True,
        rest: bool = False,
    ) -> None:
        """Drive one line to ``active`` for ``duration_s``, then restore ``rest``."""
        if duration_s <= 0:
            raise ValueError(f"duration_s must be > 0, got {duration_s}")
        self._validate({line: active})
        if not isinstance(rest, bool):
            raise TypeError(f"Rest state for line '{line}' must be bool, got {type(rest).__name__}")

        self.set_state(line, active)
        try:
            time.sleep(duration_s)
        finally:
            self.set_state(line, rest)


class OnDemandDOHandle(DeviceHandle["OnDemandDO"]):
    """Typed async handle for on-demand digital output."""

    async def set_state(self, line: str, state: bool) -> None:
        await self.call("set_state", line, state)

    async def set_states(self, states: Mapping[str, bool]) -> None:
        await self.call("set_states", states)

    async def pulse(
        self,
        line: str,
        duration_s: float,
        *,
        active: bool = True,
        rest: bool = False,
    ) -> None:
        await self.call("pulse", line, duration_s, active, rest)

    async def reset(self) -> None:
        await self.call("reset")


__all__ = [
    "OnDemandDO",
    "OnDemandDOController",
    "OnDemandDOHandle",
]
