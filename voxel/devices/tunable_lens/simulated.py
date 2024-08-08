from .base import BaseTunableLens


class SimulatedTunableLens(BaseTunableLens):
    def __init__(self, id: str):
        super().__init__(id)

    @property
    def mode(self) -> str:
        return "internal"

    @mode.setter
    def mode(self, mode: str):
        pass

    @property
    def temperature_c(self) -> float:
        return 25.0

    def log_metadata(self):
        return {
            "id": self.id,
            "mode": self.mode,
            "temperature_c": self.temperature_c,
        }

    def close(self):
        pass
