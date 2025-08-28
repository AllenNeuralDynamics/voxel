from voxel.devices.etl import ETLControlMode, ETLMetadata, VoxelTunableLens


class SimulatedTunableLens(VoxelTunableLens):
    def __init__(self, name: str) -> None:
        super().__init__(name)

    @property
    def mode(self) -> ETLControlMode:
        return ETLControlMode.INTERNAL

    @mode.setter
    def mode(self, mode: ETLControlMode) -> None:
        pass

    @property
    def temperature_c(self) -> float:
        return 25.0

    def log_metadata(self) -> ETLMetadata:
        return {
            'name': self.uid,
            'mode': self.mode,
            'temperature_c': self.temperature_c,
        }

    def close(self) -> None:
        pass
