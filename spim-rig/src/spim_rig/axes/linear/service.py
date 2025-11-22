from enum import StrEnum

import zmq.asyncio
from spim_rig.axes.linear.base import LinearAxis, TTLStepperConfig

from pyrig import DeviceAddress, DeviceService, describe


class ScanMode(StrEnum):
    """Operating modes for scanning operations."""

    IDLE = "IDLE"
    TTL_STEPPING = "TTL_STEPPING"


class LinearAxisService(DeviceService[LinearAxis]):
    """Service for managing linear axis operations and scan modes.

    Provides async RPC interface for motion control and TTL stepping capabilities.
    Manages exclusive access to scan modes and state tracking.
    """

    def __init__(self, device: LinearAxis, conn: DeviceAddress, zctx: zmq.asyncio.Context):
        # Initialize state BEFORE super().__init__() which calls _collect_commands()
        self._scan_mode = ScanMode.IDLE
        self._ttl_stepper = device.get_ttl_stepper()

        # Call super after initializing state
        super().__init__(device, conn, zctx)

    # State properties ___________________________________________________________________________________________

    @property
    @describe(label="Scan Mode", desc="Current scan operating mode")
    def scan_mode(self) -> ScanMode:
        """Current scan operating mode."""
        return self._scan_mode

    @property
    @describe(label="TTL Stepping Available", desc="Whether this axis supports TTL stepping")
    def ttl_stepping_available(self) -> bool:
        """Whether this axis supports TTL-triggered stepping."""
        return self._ttl_stepper is not None

    # TTL Stepping capability (flattened from device capability) ________________________________________________

    @describe(label="Configure TTL Stepper", desc="Configure TTL-triggered stepping operation")
    async def configure_ttl_stepper(self, cfg: TTLStepperConfig) -> None:
        """Configure the hardware for a TTL-triggered step-and-shoot operation.

        Args:
            cfg: TTL stepper configuration parameters.

        Raises:
            NotImplementedError: If this axis does not support TTL stepping.
            RuntimeError: If already in a different scan mode.
        """
        if not self._ttl_stepper:
            raise NotImplementedError(f"Axis {self.device.uid} does not support TTL stepping")

        if self._scan_mode != ScanMode.IDLE:
            raise RuntimeError(f"Cannot configure TTL stepper while in {self._scan_mode} mode")

        await self._exec(self._ttl_stepper.configure, cfg)
        self._scan_mode = ScanMode.TTL_STEPPING
        self.log.info("TTL stepper configured")

    @describe(label="Queue Absolute Move", desc="Queue an absolute move to the TTL buffer")
    async def queue_absolute_move(self, position_mm: float) -> None:
        """Queue an absolute move to the TTL ring buffer.

        Args:
            position_mm: Target absolute position in mm.

        Raises:
            NotImplementedError: If this axis does not support TTL stepping.
            RuntimeError: If TTL stepper is not configured.
        """
        if not self._ttl_stepper:
            raise NotImplementedError(f"Axis {self.device.uid} does not support TTL stepping")

        if self._scan_mode != ScanMode.TTL_STEPPING:
            raise RuntimeError("TTL stepper not configured. Call configure_ttl_stepper first.")

        await self._exec(self._ttl_stepper.queue_absolute_move, position_mm)

    @describe(label="Queue Relative Move", desc="Queue a relative move to the TTL buffer")
    async def queue_relative_move(self, delta_mm: float) -> None:
        """Queue a relative move to the TTL ring buffer.

        Args:
            delta_mm: Relative distance to move in mm.

        Raises:
            NotImplementedError: If this axis does not support TTL stepping.
            RuntimeError: If TTL stepper is not configured.
        """
        if not self._ttl_stepper:
            raise NotImplementedError(f"Axis {self.device.uid} does not support TTL stepping")

        if self._scan_mode != ScanMode.TTL_STEPPING:
            raise RuntimeError("TTL stepper not configured. Call configure_ttl_stepper first.")

        await self._exec(self._ttl_stepper.queue_relative_move, delta_mm)

    @describe(label="Reset TTL Stepper", desc="Reset TTL stepper and clear the buffer")
    async def reset_ttl_stepper(self) -> None:
        """Reset the TTL stepper configuration and clear the buffer.

        Raises:
            NotImplementedError: If this axis does not support TTL stepping.
        """
        if not self._ttl_stepper:
            raise NotImplementedError(f"Axis {self.device.uid} does not support TTL stepping")

        await self._exec(self._ttl_stepper.reset)
        self._scan_mode = ScanMode.IDLE
        self.log.info("TTL stepper reset")
