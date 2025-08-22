from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from voxel.presets import ChannelDefinition, ProfileDefinition, Repository
from voxel.utils.log import VoxelLogging

from .base import InstrumentConfigLoader, InstrumentDiscovery

_yaml = YAML(typ='safe')


class YAMLRepository[T: ChannelDefinition | ProfileDefinition](Repository[T]):
    def __init__(self, root_path: Path, model: type[T]):
        self._root = root_path
        if not self._root.exists():
            msg = f'Directory does not exist: {self._root}'
            raise FileNotFoundError(msg)

        yaml_files = list(self._root.glob('*.yaml'))
        if not yaml_files:
            msg = f'Directory must contain at least one YAML file: {self._root}'
            raise FileNotFoundError(msg)
        self._model = model

    def list(self) -> list[T]:
        items: list[T] = []
        for path in self._root.glob('*.yaml'):
            with path.open('r') as f:
                data = _yaml.load(f)

            # Auto-inject uid based on filename (without .yaml extension)
            uid_from_filename = path.stem
            if 'uid' not in data:
                data['uid'] = uid_from_filename

            # assume the YAML matches the BaseModel fields
            items.append(self._model.model_validate(data))
        return items

    def save(self, obj: T) -> None:
        path = self._root / f'{obj.uid}.yaml'
        with path.open('w') as f:
            # dump the dict representation
            _yaml.dump(obj.model_dump(), f)

    def delete(self, uid: str) -> None:
        path = self._root / f'{uid}.yaml'
        if path.exists():
            path.unlink()
        else:
            msg = f'No such file to delete: {path}'
            raise FileNotFoundError(msg)


class YAMLInstrumentLoader(InstrumentConfigLoader):
    """Loads instrument configurations from YAML files."""

    def __init__(self, root_path: Path) -> None:
        """Initialize the YAML instrument loader with a root path."""
        self.validate_path(root_path)
        self._root_path = root_path
        self._log = VoxelLogging.get_logger(f'{self.__class__.__name__}')
        self._channels_repository = YAMLRepository[ChannelDefinition](self._root_path / 'channels', ChannelDefinition)
        self._profiles_repository = YAMLRepository[ProfileDefinition](self._root_path / 'profiles', ProfileDefinition)
        self._system_config: dict[str, Any] = self._load_raw_system_config(self._root_path)

    @property
    def instrument_id(self) -> str:
        """Get the unique identifier for the instrument."""
        return self._root_path.stem

    def get_system_config(self) -> dict[str, Any]:
        """Get the loaded system configuration."""
        return self._system_config

    def get_channel_repository(self) -> Repository[ChannelDefinition]:
        """Get the channel repository."""
        return self._channels_repository

    def get_profile_repository(self) -> Repository[ProfileDefinition]:
        """Get the profile repository."""
        return self._profiles_repository

    @staticmethod
    def _load_raw_system_config(path: Path) -> dict[str, Any]:
        """Load the raw system definition from the YAML file."""
        system_file_path = path / 'system.yaml'
        with open(system_file_path) as file:
            return _yaml.load(file)

    @staticmethod
    def validate_path(path: Path) -> None:
        """Check for missing configuration files/directories and raise error if any are missing."""
        missing = []
        if not path.is_dir():
            msg = f'Configuration directory not found at: {path.resolve()}'
            raise FileNotFoundError(msg)
        required_files = ['system.yaml']
        required_dirs = ['channels', 'profiles']
        for file in required_files:
            if not (path / file).is_file():
                missing.append(f'Missing file: {path / file}')
        for directory in required_dirs:
            dir_path = path / directory
            if not dir_path.is_dir():
                missing.append(f'Missing directory: {dir_path}')
            else:
                yaml_files = list(dir_path.glob('*.yaml'))
                if not yaml_files:
                    missing.append(f'At least one YAML file expected in: {dir_path}')
        if missing:
            raise FileNotFoundError('Configuration incomplete:\n' + '\n'.join(missing))


class YAMLInstrumentDiscovery(InstrumentDiscovery):
    """Discovers and parses all instrument configurations from a root directory.

    This class scans a root directory for instrument subdirectories and creates
    InstrumentLauncher objects for each valid instrument configuration.
    """

    def __init__(self, instruments_root_dir: str = '.voxel/instruments') -> None:
        """Initialize the discovery system.

        Args:
            instruments_root_dir: Path to the directory containing instrument configurations

        Raises:
            FileNotFoundError: If the instruments root directory doesn't exist

        """
        self.root_path = Path(instruments_root_dir)
        self.logger = VoxelLogging.get_logger('launcher')
        if not self.root_path.is_dir():
            msg = f"Instruments root directory not found at: '{self.root_path.resolve()}'"
            raise FileNotFoundError(msg)
        self._loaders: dict[str, YAMLInstrumentLoader] = {}

    def run_discovery(self) -> Mapping[str, 'YAMLInstrumentLoader']:
        """Scan the root directory for instrument subdirectories and load each one.

        Returns:
            Dictionary where keys are instrument names and values are their InstrumentLauncher objects

        """
        self.logger.info(f"🔍 Discovering instruments in '{self.root_path}'")
        self._loaders.clear()
        instrument_paths = [
            p
            for p in self.root_path.iterdir()
            if p.is_dir() and (not p.stem.startswith('.')) and (p / 'system.yaml').exists()
        ]

        self.logger.info(f'✔ Found {len(instrument_paths)} potential instrument configuration directories')
        if instrument_paths:
            for instrument_path in instrument_paths:
                try:
                    self._loaders[instrument_path.name] = YAMLInstrumentLoader(instrument_path)
                except FileNotFoundError as e:
                    self.logger.error(f"✗ Skipped invalid instrument configuration in '{instrument_path}': {e}")

        success_count = len(self._loaders)
        total_count = len(instrument_paths)
        self.logger.info(
            f'🎯 Instrument discovery completed: {success_count}/{total_count} instruments loaded successfully',
        )
        return self._loaders
