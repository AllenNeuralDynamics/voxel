import time
from collections.abc import Mapping

from vxlib.quantity import Frequency, NormalizedRange, Time, Voltage, VoltageRange

from vxl.analog_out import AnalogOutput, AOSignals, InternalClock
from vxl.analog_out.wave import PulseWaveform

from .base import DiscreteAxis

_PULSE_VOLTS = 5.0
_SAMPLE_RATE_HZ = 10_000
_PERIOD_MS = 100
_DUTY = 0.5


class AnalogOutDiscreteAxis(DiscreteAxis):
    """Discrete axis driven by one analog-output line per slot.

    The generator declares one port per slot, keyed by slot index
    (``{"0": ao6, "1": ao7}``). Moving to a slot emits a single voltage pulse on
    that slot's line, which the wheel controller reads as a position select.
    Open-loop: position reflects the last commanded slot, not sensed feedback.

    Homes to slot 0 at construction so the position is commanded, never assumed.
    """

    def __init__(
        self,
        uid: str,
        *,
        ao_generator: AnalogOutput,
        slots: Mapping[int | str, str | None],
        slot_count: int | None = None,
    ) -> None:
        """Initialize an analog-output-driven discrete axis.

        Args:
            uid: Unique identifier for this device.
            ao_generator: Function generator with one port per slot, keyed by slot index.
            slots: Slot index to label, e.g. ``{0: "GFP", 1: "RFP"}``.
            slot_count: Total slots; inferred from ``slots`` when None.

        Raises:
            ValueError: If ``ao_generator`` lacks a port for any slot index.
        """
        super().__init__(uid=uid, slots=slots, slot_count=slot_count)
        self._generator = ao_generator

        available = set(ao_generator.ports)
        missing = [i for i in range(self.slot_count) if str(i) not in available]
        if missing:
            raise ValueError(f"{ao_generator.uid} has no port for slot(s) {missing}; ports: {sorted(available)}")

        self._position = 0
        self._is_moving = False
        self.move(0)

    @property
    def position(self) -> int:
        return self._position

    @property
    def is_moving(self) -> bool:
        return self._is_moving

    def move(self, slot: int, *, wait: bool = False, timeout: float | None = None) -> None:
        del wait
        if not (0 <= slot < self.slot_count):
            raise ValueError(f"Invalid slot {slot}; valid range is 0..{self.slot_count - 1}")

        signals = self._pulse_signals(str(slot))
        self._is_moving = True
        try:
            self._generator.emit(signals, timeout_s=timeout)
            self._position = slot
        finally:
            self._is_moving = False

    def home(self, *, wait: bool = False, timeout: float | None = None) -> None:
        self.move(0, wait=wait, timeout=timeout)

    def halt(self) -> None:
        self._generator.stop()
        self._is_moving = False

    def await_movement(self, timeout: float | None = None) -> None:
        start = time.time()
        while self._is_moving:
            if timeout is not None and (time.time() - start) > timeout:
                raise TimeoutError("Movement did not complete within timeout")
            time.sleep(0.01)

    def _pulse_signals(self, port: str) -> AOSignals:
        return AOSignals(
            sample_rate=Frequency(_SAMPLE_RATE_HZ),
            duration=Time(_PERIOD_MS / 1000),
            clock_src=InternalClock(),
            waveforms={
                port: PulseWaveform(
                    type="pulse",
                    voltage=VoltageRange(min=0.0, max=_PULSE_VOLTS),
                    window=NormalizedRange(min=0.0, max=_DUTY),
                    rest_voltage=Voltage(0.0),
                )
            },
        )
