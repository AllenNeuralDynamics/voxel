from importlib import metadata

from voxel.utils.log import VoxelLogging

from .transfers.base import VoxelFileTransfer
from .writers.base import VoxelWriter


class BaseRegistry[T]:
    """A generic registry for discovering and managing plugins."""

    def __init__(self, group: str, base_class: type[T]):
        self.log = VoxelLogging.get_logger(f'{self.__class__.__name__}')
        self._plugins: dict[str, type[T]] = {}
        self._group = group
        self._base_class = base_class

        self._discover_plugins()
        self.log.debug('%s discovery found: %s', self._group, list(self.available))

    @property
    def available(self) -> set[str]:
        """Returns the names of all available plugins."""
        return set(self._plugins.keys())

    def get_instance(self, name: str) -> T:
        """Gets an instance of a plugin by name."""
        if name not in self._plugins:
            msg = f"Plugin '{name}' is not available in group '{self._group}'."
            raise ValueError(msg)
        plugin_class = self._plugins[name]
        return plugin_class()

    def register(self, name: str, plugin_class: type[T]):
        """Manually registers a plugin class."""
        if not issubclass(plugin_class, self._base_class):
            msg = f'Provided class is not a valid subclass of {self._base_class.__name__}.'
            raise TypeError(msg)
        if name in self._plugins:
            self.log.warning("Overwriting registration for '%s' in group '%s'.", name, self._group)

        self._plugins[name] = plugin_class

    def _discover_plugins(self):
        entry_points = metadata.entry_points(group=self._group)
        for ep in entry_points:
            try:
                plugin_class = ep.load()
                if issubclass(plugin_class, self._base_class):
                    self._plugins[ep.name] = plugin_class
            except Exception:
                self.log.exception("Failed to load plugin '%s' from group '%s'", ep.name, self._group)


class WriterRegistry(BaseRegistry[VoxelWriter]):
    """Manages all VoxelWriter plugins."""

    def __init__(self):
        super().__init__(group='voxel.writers', base_class=VoxelWriter)


class TransferRegistry(BaseRegistry[VoxelFileTransfer]):
    """Manages all VoxelTransfer plugins."""

    def __init__(self):
        super().__init__(group='voxel.transfers', base_class=VoxelFileTransfer)
