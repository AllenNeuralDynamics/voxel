from .common import PropertyModel as PropertyModel
from .deliminated import deliminated_float, deliminated_int
from .enumarated import enumerated_int, enumerated_string

__all__ = [
    "PropertyModel",
    "deliminated_int",
    "deliminated_float",
    "enumerated_int",
    "enumerated_string",
]

if __name__ == "__main__":
    import logging

    from pyrig.utils import configure_logging

    logger = logging.getLogger(__name__)

    class MixerChannel:
        def __init__(self) -> None:
            self._volume = 0.5
            self._gain = 0
            self._mode = "sine"
            self._preset = 1

        @deliminated_float(min_value=0.0, max_value=1.0, step=0.1)
        def volume(self) -> float:
            return self._volume

        @volume.setter
        def volume(self, value: float) -> None:
            self._volume = value

        @deliminated_int(min_value=-10, max_value=10, step=2)
        def gain(self) -> int:
            return self._gain

        @gain.setter
        def gain(self, value: int) -> None:
            self._gain = value

        @enumerated_string(options=["sine", "square", "saw"])
        def mode(self) -> str:
            return self._mode

        @mode.setter
        def mode(self, value: str) -> None:
            self._mode = value

        @enumerated_int(options=[1, 2, 3])
        def preset(self) -> int:
            return self._preset

        @preset.setter
        def preset(self, value: int) -> None:
            self._preset = value

    configure_logging(logging.DEBUG)

    channel = MixerChannel()
    logger.info(channel.volume)  # 0.5 (min=0.0, max=1.0, step=0.1)
    channel.volume = 1.3  # will be clamped/logged to 1.0 internally
    logger.info(channel.volume)

    logger.info(channel.gain)  # 0 (min=-10, max=10, step=2)
    channel.gain = 5  # snaps to 6 because of step constraint
    logger.info(channel.gain)

    logger.info(channel.mode)  # "sine"
    channel.mode = "triangle"  # ignored, not in options
    logger.info(channel.mode)

    logger.info(channel.preset)  # 1
    channel.preset = 4  # ignored, not in options
    logger.info(channel.preset)
