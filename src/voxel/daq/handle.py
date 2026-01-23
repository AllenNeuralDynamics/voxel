"""DAQ device handle with typed task operations."""

from pyrig.device import DeviceHandle

from .base import AcqSampleMode, PinInfo, TaskInfo, VoxelDaq


class DaqHandle(DeviceHandle[VoxelDaq]):
    """DAQ handle with typed methods for task operations."""

    # ==================== Pin Management ====================

    async def assign_pin(self, task_name: str, pin: str) -> PinInfo:
        """Assign a pin to a task."""
        result = await self.call("assign_pin", task_name, pin)
        return PinInfo.model_validate(result)

    async def release_pin(self, pin: PinInfo) -> bool:
        """Release a pin from its task."""
        return await self.call("release_pin", pin)

    async def release_pins_for_task(self, task_name: str) -> None:
        """Release all pins for a task."""
        await self.call("release_pins_for_task", task_name)

    async def get_pfi_path(self, pin: str) -> str:
        """Get PFI path for a pin."""
        return await self.call("get_pfi_path", pin)

    # ==================== Task Factory ====================

    async def create_ao_task(self, task_name: str, pins: list[str]) -> TaskInfo:
        """Create an analog output task."""
        result = await self.call("create_ao_task", task_name, pins)
        return TaskInfo.model_validate(result)

    async def create_co_task(
        self,
        task_name: str,
        counter: str,
        frequency_hz: float,
        duty_cycle: float = 0.5,
        pulses: int | None = None,
        output_pin: str | None = None,
    ) -> TaskInfo:
        """Create a counter output task."""
        result = await self.call(
            "create_co_task",
            task_name,
            counter,
            frequency_hz,
            duty_cycle,
            pulses,
            output_pin,
        )
        return TaskInfo.model_validate(result)

    async def close_task(self, task_name: str) -> None:
        """Close a task and release its pins."""
        await self.call("close_task", task_name)

    # ==================== Task Operations ====================

    async def start_task(self, task_name: str) -> None:
        """Start a task by name."""
        await self.call("start_task", task_name)

    async def stop_task(self, task_name: str) -> None:
        """Stop a task by name."""
        await self.call("stop_task", task_name)

    async def write_ao_task(self, task_name: str, data: list[float] | list[list[float]]) -> int:
        """Write data to an analog output task."""
        return await self.call("write_ao_task", task_name, data)

    async def configure_ao_timing(
        self,
        task_name: str,
        rate: float,
        sample_mode: AcqSampleMode,
        samps_per_chan: int,
    ) -> None:
        """Configure sample clock timing for AO task."""
        await self.call("configure_ao_timing", task_name, rate, sample_mode, samps_per_chan)

    async def configure_ao_trigger(
        self,
        task_name: str,
        trigger_source: str,
        retriggerable: bool = False,
    ) -> None:
        """Configure digital edge start trigger for AO task."""
        await self.call("configure_ao_trigger", task_name, trigger_source, retriggerable)

    async def configure_co_trigger(
        self,
        task_name: str,
        trigger_source: str,
        retriggerable: bool = False,
    ) -> None:
        """Configure digital edge start trigger for CO task."""
        await self.call("configure_co_trigger", task_name, trigger_source, retriggerable)

    async def wait_for_task(self, task_name: str, timeout_s: float) -> None:
        """Wait for a task to complete."""
        await self.call("wait_for_task", task_name, timeout_s)

    # ==================== Lifecycle ====================

    async def stop_all_tasks(self) -> None:
        """Stop all active tasks."""
        await self.call("stop_all_tasks")

    async def close_all_tasks(self) -> None:
        """Close all tasks and release all pins."""
        await self.call("close_all_tasks")

    # ==================== Convenience Methods ====================

    async def pulse(
        self,
        pin: str,
        duration_s: float,
        voltage_v: float,
        sample_rate_hz: int = 10000,
    ) -> None:
        """Generate a simple finite pulse on a single analog output pin.

        This is a convenience method that:
        1. Creates a temporary AO task
        2. Writes a pulse waveform at the specified voltage
        3. Waits for completion
        4. Returns the pin to rest voltage (0V)
        5. Cleans up the task

        Args:
            pin: Pin name to pulse (e.g., "ao0", "ao5").
            duration_s: Pulse duration in seconds.
            voltage_v: Pulse voltage level in volts.
            sample_rate_hz: Sample rate for the waveform (default: 10000 Hz).

        Example:
            # Generate a 100ms pulse at 5V on pin ao5
            await daq_handle.pulse(pin="ao5", duration_s=0.1, voltage_v=5.0)
        """
        task_name = f"pulse_{pin}_{self.uid}"
        num_samples = int(duration_s * sample_rate_hz)

        if num_samples <= 0:
            raise ValueError(f"Invalid duration: {duration_s}s results in {num_samples} samples")

        try:
            # Create task with single channel
            await self.create_ao_task(task_name, [pin])

            # Configure finite timing
            await self.configure_ao_timing(
                task_name,
                rate=sample_rate_hz,
                sample_mode=AcqSampleMode.FINITE,
                samps_per_chan=num_samples,
            )

            # Write and execute pulse (high voltage)
            pulse_data = [voltage_v] * num_samples
            await self.write_ao_task(task_name, pulse_data)
            await self.start_task(task_name)
            await self.wait_for_task(task_name, timeout_s=duration_s + 1.0)
            await self.stop_task(task_name)

            # Return to rest (0V)
            rest_data = [0.0] * num_samples
            await self.write_ao_task(task_name, rest_data)
            await self.start_task(task_name)
            await self.wait_for_task(task_name, timeout_s=duration_s + 1.0)

        finally:
            # Always clean up the task
            await self.close_task(task_name)
