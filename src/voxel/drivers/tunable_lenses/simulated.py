from voxel.instrument.devices.tunable_lens import VoxelTunableLens, TunableLensControlMode


class SimulatedTunableLens(VoxelTunableLens):
    def __init__(self, name: str):
        super().__init__(name)

    @property
    def mode(self) -> TunableLensControlMode:
        return TunableLensControlMode.INTERNAL

    @mode.setter
    def mode(self, mode: TunableLensControlMode):
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
