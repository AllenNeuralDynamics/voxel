"""SeqSweep hardware runtime: opens the rig and checks the built devices against the topology."""

import asyncio
import logging
from collections.abc import Mapping

from vxl.hal.errors import HALStartupError, Violation

from rigup import DeviceHandle, DeviceInterface, Rig
from seqsweep.devices.base import SeqSweepDeviceType

from .topology import SeqSweepHardwareTopology

logger = logging.getLogger(__name__)


class HAL:
    """Runtime hardware abstraction: opens the rig and exposes devices by type."""

    def __init__(self, topology: SeqSweepHardwareTopology, name: str = "SeqSweepHAL") -> None:
        self._topology = topology
        self._rig = Rig(topology, name)

        self.scan_controllers: dict[str, DeviceHandle] = {}  # TODO Add ACS Handle
        self._device_interfaces: dict[str, DeviceInterface] = {}

    @property
    def topology(self) -> SeqSweepHardwareTopology:
        return self._topology

    @property
    def rig(self) -> Rig:
        return self._rig

    @property
    def devices(self) -> dict[str, DeviceHandle]:
        return self.rig.devices

    @property
    def device_interfaces(self) -> Mapping[str, DeviceInterface]:
        """Interfaces retained from the successful startup inspection."""
        return dict(self._device_interfaces)

    @property
    def scan_controller(self) -> DeviceHandle:
        if (handle := self.scan_controllers.get(self._topology.scan_controller)) is None:
            raise RuntimeError("HAL is not open — scan controller is unavailable")
        return handle

    async def open(self) -> None:
        violations: list[Violation] = []
        try:
            await self._rig.open()
            violations.extend(self._build_violations())
            interface_violations, interface_unavailable = await self._inspect_and_classify_devices()
            violations.extend(interface_violations)
            unavailable = set(self.rig.build_errors) | interface_unavailable
            violations.extend(self._compatibility_violations(unavailable))
        except BaseException:
            await self.close()
            raise
        if violations:
            await self.close()
            raise HALStartupError(violations)

    async def close(self) -> None:
        self._device_interfaces = {}
        self.scan_controllers.clear()
        await self._rig.close()

    def _build_violations(self) -> list[Violation]:
        return [
            Violation(
                code=f"build.{error.error_type}",
                msg=f"Device '{uid}' failed to build: {error.message}",
                loc=("hal", "devices", uid),
            )
            for uid, error in self.rig.build_errors.items()
        ]

    async def _inspect_and_classify_devices(self) -> tuple[list[Violation], set[str]]:
        """Inspect and classify every built device, collecting independent interface failures."""
        devices = list(self.rig.devices.items())
        interfaces = await asyncio.gather(
            *(handle.interface() for _, handle in devices),
            return_exceptions=True,
        )
        violations = []
        unavailable = set()
        for (uid, handle), interface in zip(devices, interfaces, strict=True):
            if isinstance(interface, BaseException):
                if not isinstance(interface, Exception):
                    raise interface
                unavailable.add(uid)
                violations.append(
                    Violation(
                        code="hal.device.interface",
                        msg=f"Unable to inspect device '{uid}': {interface}",
                        loc=("hal", "devices", uid),
                    )
                )
                continue

            self._device_interfaces[uid] = interface

            match interface.type:
                case SeqSweepDeviceType.SCAN_CONTROLLER:
                    self.scan_controllers[uid] = handle
                case _:
                    logger.debug("Uncategorized device '%s' of type '%s'", uid, interface.type)
        return violations, unavailable

    def _compatibility_violations(self, unavailable: set[str]) -> list[Violation]:
        """Return all role conflicts detectable from the built device inventory."""
        return [*self._scan_controller_violations(unavailable)]

    def _scan_controller_violations(self, unavailable: set[str]) -> list[Violation]:
        uid = self._topology.scan_controller
        if uid not in self.scan_controllers and uid not in unavailable:
            return [
                Violation(
                    code="hal.scan_controller.not_scan_controller",
                    msg=f"Scan controller '{uid}' is not a scan_controller device.",
                    loc=("hal", "scan_controller"),
                )
            ]
        return []
