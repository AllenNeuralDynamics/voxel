from pathlib import Path

from ruamel.yaml import YAML
from voxel.utils.log import VoxelLogging
from voxel_classic.instruments.instrument import Instrument

DIRECTORY = Path(__file__).parent.resolve()


class ExASPIM(Instrument):
    """
    Class for handling ExASPIM instrument configuration and verification.
    """

    def __init__(self, config_filename: str | Path, yaml_handler: YAML, log_level: str = "INFO") -> None:
        """
        Initialize the ExASPIM object.

        :param config_filename: Configuration filename
        :type config_filename: str
        :param yaml_handler: YAML handler
        :type yaml_handler: YAML
        :param log_level: Logging level, defaults to "INFO"
        :type log_level: str, optional
        """
        self.log = VoxelLogging.get_logger(object=self)
        self.log.setLevel(log_level)

        # current working directory
        super().__init__(DIRECTORY / Path(config_filename), yaml_handler, log_level)

        # verify exaspim microscope
        self._verify_instrument()

    def _verify_instrument(self) -> None:
        """
        Verify the ExASPIM instrument configuration.

        :raises ValueError: If the number of scanning stages is not 1
        :raises ValueError: If the number of cameras is not 1
        :raises ValueError: If the number of DAQs is not 1
        :raises ValueError: If there are no lasers
        :raises ValueError: If the x tiling stage is not defined
        :raises ValueError: If the y tiling stage is not defined
        """
        # assert that only one scanning stage is allowed
        self.log.info("verifying instrument configuration")
        num_scanning_stages = len(self.scanning_stages)
        if len(self.scanning_stages) != 1:
            raise ValueError(f"one scanning stage must be defined but {num_scanning_stages} detected")
        num_cameras = len(self.cameras)
        if len(self.cameras) != 1:
            raise ValueError(f"one camera must be defined but {num_cameras} detected")
        num_daqs = len(self.daqs)
        if len(self.daqs) != 1:
            raise ValueError(f"one daq must be defined but {num_daqs} detected")
        num_lasers = len(self.lasers)
        if num_lasers < 1:
            raise ValueError(f"at least one laser is required but {num_lasers} detected")
        if not self.tiling_stages["x"]:
            raise ValueError("x tiling stage is required")
        if not self.tiling_stages["y"]:
            raise ValueError("y tiling stage is required")
