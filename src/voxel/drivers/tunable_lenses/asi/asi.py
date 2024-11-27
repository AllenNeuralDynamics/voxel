from tigerasi.device_codes import *
from tigerasi.tiger_controller import TigerController

from voxel.instrument.hubs.tigerbox import ASITigerBox
from voxel.instrument.drivers.tunable_lenses.base import VoxelTunableLens, TunableLensControlMode


class ASITunableLens(VoxelTunableLens):

    def __init__(
        self,
        name: str,
        hardware_axis: str,
        tigerbox: ASITigerBox,
    ):
        """Connect to ASI tunable lens.
        :param name: unique voxel name for this device.
        :param tigerbox: TigerController instance.
        :param hardware_axis: stage hardware axis.
        :type name: st
        :type tigerbox: TigerController
        :type hardware_axis: str
        :raises DeviceConnectionError: if the hardware axis is not found or is already registered.
        """
        super().__init__(name)
        self._tigerbox = tigerbox
        self._hardware_axis = hardware_axis.upper()
        self._tigerbox.register_device(self.name, self._hardware_axis)

    @property
    def temperature_c(self):
        """Get the temperature in deg C."""
        return self._tigerbox.get_etl_temp(self.name)

    @property
    def mode(self):
        """Get the tiger axis control mode."""
        mode = self._tigerbox.get_axis_control_mode(self.name)
        match mode:
            case TunableLensControlMode.EXTERNAL_INPUT_NO_TEMP_COMPENSATION:
                return TunableLensControlMode.EXTERNAL
            case TunableLensControlMode.TG1000_INPUT_NO_TEMP_COMPENSATION:
                return TunableLensControlMode.INTERNAL
            case _:
                raise ValueError("mode must be one of %r." % TunableLensControlMode)

    @mode.setter
    def mode(self, mode: TunableLensControlMode):
        """Set the tiger axis control mode."""
        match mode:
            case TunableLensControlMode.EXTERNAL:
                self._tigerbox.set_axis_control_mode(
                    self.name, TunableLensControlMode.EXTERNAL_INPUT_NO_TEMP_COMPENSATION
                )
            case TunableLensControlMode.INTERNAL:
                self._tigerbox.set_axis_control_mode(
                    self.name, TunableLensControlMode.TG1000_INPUT_NO_TEMP_COMPENSATION
                )
            case _:
                raise ValueError("mode must be one of %r." % TunableLensControlMode)

    def log_metadata(self):
        self.log.info("tiger hardware axis parameters")
        build_config = self._tigerbox.build_config
        self.log.debug(f"{build_config}")
        axis_settings = self._tigerbox.get_axis_info(self.name)
        self.log.info(f"{self.name} axis settings")
        for setting in axis_settings:
            self.log.info(f"{self.name} axis, {setting}, {axis_settings[setting]}")

    def close(self):
        self._tigerbox.deregister_device(self.name)
