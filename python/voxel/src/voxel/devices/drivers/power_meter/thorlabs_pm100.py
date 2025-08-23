from pyvisa import ResourceManager, VisaIOError
from pyvisa.resources import MessageBasedResource

from voxel.devices import VoxelDeviceConnectionError
from voxel.devices.interfaces.power_meter import VoxelPowerMeter


class ThorlabsPowerMeter(VoxelPowerMeter):
    def __init__(self, name: str, conn: str) -> None:
        super().__init__(name)
        self._conn = conn
        self._inst: MessageBasedResource = self._connect()

    def _connect(self) -> MessageBasedResource:
        """Connect to the power meter."""

        def get_message_based_resource() -> MessageBasedResource:
            instance = ResourceManager().open_resource(self._conn)
            if isinstance(instance, MessageBasedResource):
                return instance
            error_msg = f'Connected resource is not a MessageBasedResource: {type(instance)}'
            raise VoxelDeviceConnectionError(error_msg)

        try:
            return get_message_based_resource()
        except VisaIOError as e:
            self.log.exception('Could not connect to %s', self._conn)
            raise VoxelDeviceConnectionError from e
        except Exception as e:
            raise VoxelDeviceConnectionError from e

    def _check_connection(self) -> None:
        if self._inst is None:
            msg = f'Device {self.uid} is not connected'
            raise VoxelDeviceConnectionError(msg)

    @property
    def power_mw(self) -> float:
        self._check_connection()
        return float(self._inst.query('MEAS:POW?')) * 1e3 if self._inst is not None else -999

    @property
    def wavelength_nm(self) -> float:
        self._check_connection()
        return float(self._inst.query('SENS:CORR:WAV?'))

    @wavelength_nm.setter
    def wavelength_nm(self, wavelength: float) -> None:
        self._check_connection()
        self._inst.write(f'SENS:CORR:WAV {wavelength}')
        self.log.info('%s - Set wavelength to %s nm', self.uid, wavelength)

    def close(self) -> None:
        self._inst.close()
        self.log.info('Disconnected from %s', self._conn)
