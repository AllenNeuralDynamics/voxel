import random

from pyrig.device import Device, DeviceClient, describe
from pyrig.props import PropertyModel, deliminated_float, enumerated_string


class Laser(Device):
    """A mock laser device for testing property and command interfaces."""

    __DEVICE_TYPE__ = "laser"
    __COMMANDS__ = {"turn_on", "turn_off"}

    def __init__(self, uid: str, wavelength: float):
        super().__init__(uid=uid)
        self._wavelength = wavelength
        self._power_setpoint: float = 0.0
        self._mode = "cw"
        self._is_on: bool = False

    @property
    @describe(label="Wavelength", units="nm")
    def wavelength(self) -> float:
        """Get the laser wavelength."""
        return self._wavelength

    @property
    def is_on(self) -> bool:
        """Get whether the laser is currently on."""
        return self._is_on

    @property
    def power(self) -> float:
        """Get the current laser power output."""
        if not self._is_on:
            return 0.0
        # Mock some power variation when on
        return random.uniform(self._power_setpoint - 0.1, self._power_setpoint + 0.1)

    @deliminated_float(min_value=0.0, max_value=100.0, step=0.5)
    @describe(label="Power Setpoint", units="%")
    def power_setpoint(self) -> float:
        """Get the laser power setpoint."""
        return self._power_setpoint

    @power_setpoint.setter
    def power_setpoint(self, value: float) -> None:
        """Set the laser power setpoint."""
        if value != self._power_setpoint:
            self.log.info("power_setpoint updated: %.1f -> %.1f", self._power_setpoint, value)
        self._power_setpoint = value

    @enumerated_string(options=["cw", "pulsed", "burst"])
    @describe(label="Emission Mode")
    def mode(self) -> str:
        """Current emission mode."""
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        self.log.info("mode updated: %s -> %s", self._mode, value)
        self._mode = value

    def turn_on(self) -> bool:
        """Turn on the laser."""
        if self._power_setpoint <= 0:
            raise ValueError("Cannot turn on laser with zero power setpoint")
        self._is_on = True
        self.log.info("laser turned on at %.1f power", self._power_setpoint)
        return True

    def turn_off(self) -> bool:
        """Turn off the laser."""
        self._is_on = False
        self.log.info("laser turned off")
        return True

    @describe(label="Set Power", desc="Set laser power and turn on")
    def set_power_and_on(self, power: float) -> str:
        """Set power setpoint and turn on the laser in one command."""
        self.power_setpoint = power
        self.turn_on()
        self.log.info("set_power_and_on executed at %.1f power", power)
        return f"Laser on at {power} power"

    @describe(label="Emergency Stop", desc="Emergency stop - turn off immediately")
    def emergency_stop(self) -> str:
        """Emergency stop the laser."""
        self._is_on = False
        self._power_setpoint = 0.0
        self.log.warning("emergency_stop triggered; power reset to 0")
        return "Emergency stop executed"


class LaserClient(DeviceClient):
    async def turn_on(self) -> bool:
        """Turn on the laser."""
        self.log.info("Requesting laser turn_on")
        return await self.call("turn_on")

    async def turn_off(self) -> bool:
        """Turn off the laser."""
        self.log.info("Requesting laser turn_off")
        return await self.call("turn_off")

    async def set_power_and_on(self, power: float) -> str:
        """Set laser power and turn on in one command."""
        self.log.info("Requesting set_power_and_on: %.1f", power)
        return await self.call("set_power_and_on", power)

    async def emergency_stop(self) -> str:
        """Emergency stop the laser."""
        self.log.warning("Requesting emergency_stop")
        return await self.call("emergency_stop")

    async def get_power_setpoint(self) -> float:
        """Get the laser power setpoint."""
        return await self.get_prop_value("power_setpoint")

    async def set_power_setpoint(self, value: float) -> None:
        """Set the laser power setpoint."""
        self.log.info("Setting power_setpoint to %.1f", value)
        await self.set_prop("power_setpoint", value)

    async def get_is_on(self) -> PropertyModel[bool]:
        """Check if laser is on."""
        return await self.get_prop_value("is_on")

    async def get_mode(self) -> PropertyModel[str]:
        """Get emission mode."""
        return await self.get_prop("mode")

    async def set_mode(self, value: str) -> None:
        """Set emission mode."""
        await self.set_prop("mode", value)
