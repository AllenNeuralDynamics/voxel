from aaopto_aotf.aotf import MPDS
from aaopto_aotf.device_codes import BlankingMode, InputMode
from voxel.devices.interfaces.aotf import VoxelAOTF
from voxel.utils.singleton import thread_safe_singleton

BLANKING_MODES = {
    'external': BlankingMode.EXTERNAL,
    'internal': BlankingMode.INTERNAL,
}

INPUT_MODES = {
    'external': InputMode.EXTERNAL,
    'internal': InputMode.INTERNAL,
}


@thread_safe_singleton
def get_mpds_singleton(com_port) -> MPDS:
    return MPDS(com_port)


class AAOptoAOTF(VoxelAOTF):
    def __init__(self, port: str, name: str = '', channel: int = 0):
        super().__init__(name)
        self._aotf = get_mpds_singleton(com_port=port)
        # make sure the channel is valid
        if channel >= self._aotf.num_channels:
            msg = f'Channel {channel} is invalid. Must be less than {self._aotf.num_channels}'
            raise ValueError(msg)
        self._channel = channel
        self.product_id = self._aotf.get_product_id()

    def enable(self):
        self._aotf.enable_channel(self._channel)

    def disable(self):
        self._aotf.disable_channel(self._channel)

    @property
    def frequency_hz(self):
        return self._aotf.get_frequency(self._channel)

    @frequency_hz.setter
    def frequency_hz(self, frequency_hz: int):
        self._aotf.set_frequency(self._channel, frequency_hz)
        self._aotf.save_profile()

    @property
    def power_dbm(self):
        return self._aotf.get_power_dbm(self._channel)

    @power_dbm.setter
    def power_dbm(self, power_dbm: float):
        self._aotf.set_power_dbm(self._channel, power_dbm)
        self._aotf.save_profile()

    @property
    def blanking_mode(self):
        mode = self._aotf.get_blanking_mode()
        return next(key for key, enum in BLANKING_MODES.items() if enum.value == mode)

    @blanking_mode.setter
    def blanking_mode(self, mode: str):
        valid = list(BLANKING_MODES.keys())
        if mode not in valid:
            msg = f'blanking mode must be one of {valid!r}.'
            raise ValueError(msg)
        self._aotf.set_blanking_mode(BLANKING_MODES[mode])

    @property
    def input_mode(self) -> str:
        mode = self._aotf.get_channel_input_mode(self._channel)
        return next(key for key, enum in INPUT_MODES.items() if enum.value == mode)

    @input_mode.setter
    def input_mode(self, mode: str):
        valid = list(INPUT_MODES.keys())
        if mode not in valid:
            msg = f'input mode must be one of {valid!r}.'
            raise ValueError(msg)
        self._aotf.set_channel_input_mode(self._channel, INPUT_MODES[mode])
