import random

from spim_rig.aotf.base import SpimAotf
from spim_rig.laser.base import SpimLaser

from pyrig import describe
from pyrig.props import deliminated_float


class SimulatedLaser(SpimLaser):
    def __init__(self, uid: str, wavelength: int, max_power_mw: float = 1000.0) -> None:
        self._max_power_mw = max_power_mw
        self._power_setpoint_mw = 10.0
        self._is_enabled = False
        self._temperature = 20.0
        super().__init__(uid=uid, wavelength=wavelength)

    def enable(self) -> None:
        self._is_enabled = True

    def disable(self) -> None:
        self._is_enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._is_enabled

    @deliminated_float(min_value=0.0, max_value=lambda self: self._max_power_mw, step=1.0)
    def power_setpoint_mw(self) -> float:
        return random.gauss(self._power_setpoint_mw, 0.1)

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        self._power_setpoint_mw = value
        self.log.info(f"Power setpoint changed to {value} mW")

    @property
    def power_mw(self) -> float:
        if not self._is_enabled:
            return 0.0
        return random.gauss(self._power_setpoint_mw, 0.1)

    @property
    def temperature_c(self) -> float:
        return self._temperature + random.gauss(0, 0.1)


class SimulatedAOTFShutteredLaser(SpimLaser):
    """Laser with internal power control, using AOTF only for fast shuttering.

    The laser has its own power control (simulated here), but uses an AOTF
    channel for fast on/off modulation synchronized with camera/DAQ timing.
    The laser stays "hot" when disabled - only blocked by the AOTF.

    Args:
        uid: Unique identifier for this laser device.
        wavelength: Laser wavelength in nm.
        aotf: Reference to the AOTF device (resolved by pyrig from device ID).
        aotf_channel: Channel number on the AOTF (1-indexed).
        aotf_frequency_mhz: RF frequency for optimal diffraction at this wavelength.
        max_power_mw: Maximum laser power in mW.
    """

    def __init__(
        self,
        uid: str,
        wavelength: int,
        aotf: SpimAotf,
        aotf_channel: int,
        aotf_frequency_mhz: float,
        max_power_mw: float = 1000.0,
    ) -> None:
        self._aotf = aotf
        self._aotf_channel = aotf_channel
        self._aotf_frequency_mhz = aotf_frequency_mhz
        self._max_power_mw = max_power_mw
        self._power_setpoint_mw: float = 10.0
        self._temperature = 25.0

        # Register with the AOTF
        self._aotf.register_channel(uid, aotf_channel)

        # Set the calibrated frequency and max power for passthrough
        self._aotf.set_frequency(aotf_channel, aotf_frequency_mhz)
        self._aotf.set_power_dbm(aotf_channel, self._aotf.max_power_dbm)  # Max transmission

        super().__init__(uid=uid, wavelength=wavelength)

        self.log.info(
            f"Initialized SimulatedAOTFShutteredLaser: wavelength={wavelength}nm, "
            f"aotf={aotf.uid} channel={aotf_channel}"
        )

    def get_aotf(self) -> "SpimAotf":
        return self._aotf

    @property
    def aotf(self) -> "str":
        """Get the AOTF device controlling this laser."""
        return self._aotf.uid

    @property
    def aotf_channel(self) -> int:
        """Get the AOTF channel number."""
        return self._aotf_channel

    def enable(self) -> None:
        """Enable laser output by opening the AOTF shutter."""
        self._aotf.enable_channel(self._aotf_channel)
        self.log.debug("Enabled (AOTF shutter open)")

    def disable(self) -> None:
        """Disable laser output by closing the AOTF shutter."""
        self._aotf.disable_channel(self._aotf_channel)
        self.log.debug("Disabled (AOTF shutter closed)")

    @property
    def is_enabled(self) -> bool:
        """Check if the AOTF shutter is open."""
        return self._aotf.get_channel_state(self._aotf_channel)

    @deliminated_float(min_value=0.0, max_value=lambda self: self._max_power_mw, step=1.0)
    @describe(label="Power Setpoint", units="mW", desc="Target laser power.", stream=True)
    def power_setpoint_mw(self) -> float:
        """Get the power setpoint in mW (controlled by laser, not AOTF)."""
        return self._power_setpoint_mw

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        """Set the power setpoint in mW."""
        self._power_setpoint_mw = value
        self.log.debug(f"Power setpoint changed to {value} mW")

    @property
    def power_mw(self) -> float:
        """Get the current output power in mW."""
        if not self.is_enabled:
            return 0.0
        return random.gauss(self._power_setpoint_mw, 0.1)

    @property
    def temperature_c(self) -> float:
        """Get laser temperature."""
        return self._temperature + random.gauss(0, 0.1)


class SimulatedAOTFModulatedLaser(SpimLaser):
    """Laser with no serial control - AOTF handles all modulation.

    For lasers that are passive sources (always on at constant power) with
    no serial/USB interface. The AOTF provides both on/off control and
    power modulation via its RF power setting.

    Args:
        uid: Unique identifier for this laser device.
        wavelength: Laser wavelength in nm.
        aotf: Reference to the AOTF device (resolved by pyrig from device ID).
        aotf_channel: Channel number on the AOTF (1-indexed).
        aotf_frequency_mhz: RF frequency for optimal diffraction at this wavelength.
    """

    def __init__(
        self,
        uid: str,
        wavelength: int,
        aotf: SpimAotf,
        aotf_channel: int,
        aotf_frequency_mhz: float,
    ) -> None:
        self._aotf = aotf
        self._aotf_channel = aotf_channel
        self._aotf_frequency_mhz = aotf_frequency_mhz
        self._power_setpoint_dbm: float = 0.0

        # Register with the AOTF
        self._aotf.register_channel(uid, aotf_channel)

        # Set the calibrated frequency
        self._aotf.set_frequency(aotf_channel, aotf_frequency_mhz)

        super().__init__(uid=uid, wavelength=wavelength)

        self.log.info(
            f"Initialized SimulatedAOTFModulatedLaser: wavelength={wavelength}nm, "
            f"aotf={aotf.uid} channel={aotf_channel}, "
            f"frequency={aotf_frequency_mhz}MHz"
        )

    def get_aotf(self) -> "SpimAotf":
        return self._aotf

    @property
    def aotf(self) -> "str":
        """Get the AOTF device controlling this laser."""
        return self._aotf.uid

    @property
    def aotf_channel(self) -> int:
        """Get the AOTF channel number."""
        return self._aotf_channel

    @property
    @describe(label="AOTF Frequency", units="MHz", desc="RF frequency for this wavelength.")
    def aotf_frequency_mhz(self) -> float:
        """Get the calibrated AOTF frequency."""
        return self._aotf_frequency_mhz

    def enable(self) -> None:
        """Enable laser output by enabling the AOTF channel."""
        self._aotf.set_power_dbm(self._aotf_channel, self._power_setpoint_dbm)
        self._aotf.enable_channel(self._aotf_channel)
        self.log.debug(f"Enabled (AOTF channel {self._aotf_channel})")

    def disable(self) -> None:
        """Disable laser output by disabling the AOTF channel."""
        self._aotf.disable_channel(self._aotf_channel)
        self.log.debug(f"Disabled (AOTF channel {self._aotf_channel})")

    @property
    def is_enabled(self) -> bool:
        """Check if the AOTF channel is enabled."""
        return self._aotf.get_channel_state(self._aotf_channel)

    @deliminated_float(
        min_value=lambda self: self._aotf.min_power_dbm,
        max_value=lambda self: self._aotf.max_power_dbm,
        step=lambda self: self._aotf.power_step_dbm,
    )
    @describe(label="Power Setpoint", units="dBm", desc="Target AOTF RF power.", stream=True)
    def power_setpoint_mw(self) -> float:
        """Get the power setpoint in dBm.

        Note: For AOTF-modulated lasers, power is RF power in dBm, not optical mW.
        """
        return self._power_setpoint_dbm

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        """Set the power setpoint in dBm."""
        self._power_setpoint_dbm = value
        if self.is_enabled:
            self._aotf.set_power_dbm(self._aotf_channel, value)
        self.log.debug(f"Power setpoint changed to {value} dBm")

    @property
    def power_mw(self) -> float:
        """Get the current AOTF power in dBm."""
        if not self.is_enabled:
            return 0.0
        return self._aotf.get_power_dbm(self._aotf_channel)

    @property
    def temperature_c(self) -> float | None:
        """Temperature not available for AOTF-only controlled lasers."""
        return None

    def set_aotf_frequency(self, frequency_mhz: float) -> None:
        """Update the AOTF frequency for recalibration."""
        self._aotf_frequency_mhz = frequency_mhz
        self._aotf.set_frequency(self._aotf_channel, frequency_mhz)
        self.log.info(f"AOTF frequency updated to {frequency_mhz} MHz")
