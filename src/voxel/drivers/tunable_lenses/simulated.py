from voxel.devices.tunable_lens import VoxelTunableLens, ETLControlMode


class SimulatedTunableLens(VoxelTunableLens):
    def __init__(self, name: str):
        super().__init__(name)

    @property
    def mode(self) -> ETLControlMode:
        return ETLControlMode.INTERNAL

    @mode.setter
    def mode(self, mode: ETLControlMode):
        pass

    @property
    def temperature_c(self) -> float:
        return 25.0

    def log_metadata(self):
        return {
            "name": self.name,
            "mode": self.mode,
            "temperature_c": self.temperature_c,
        }

    def close(self):
        pass
