import inspect
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import inflection
from exaspim_control.instrument.exaspim_instrument import ExASPIM
from exaspim_control.metadata.aind_metadata_class import AINDMetadataClass
from ruamel.yaml import YAML
from voxel.utils.log import VoxelLogging

if TYPE_CHECKING:
    from exaspim_control.voxel_classic.file_transfers.base import BaseFileTransfer
    from exaspim_control.voxel_classic.writers.base import BaseWriter


class Acquisition:
    """Handles the acquisition process for the instrument."""

    def __init__(
        self,
        instrument: ExASPIM,
        config_filename: str | Path,
        yaml_handler: YAML | None = None,
        log_level: str = 'INFO',
    ) -> None:
        """Initializes the Acquisition class.

        :param instrument: The instrument to be used for acquisition.
        :type instrument: Instrument
        :param config_filename: The path to the configuration file.
        :type config_filename: str
        :param yaml_handler: YAML handler for loading and dumping config, defaults to None.
        :type yaml_handler: YAML, optional
        :param log_level: Logging level, defaults to "INFO".
        :type log_level: str, optional
        """
        self.log = VoxelLogging.get_logger(obj=self)
        self.log.setLevel(log_level)

        # create yaml object to use when loading and dumping config
        self.yaml = yaml_handler if yaml_handler is not None else YAML(typ='safe')

        self.config_path = Path(config_filename)
        self.config = self.yaml.load(Path(self.config_path))

        self.instrument = instrument
        self.file_transfers: dict[str, dict[str, BaseFileTransfer]] = {}  # initialize file_transfers attribute
        self.writers: dict[str, dict[str, BaseWriter]] = {}  # initialize writers attribute
        self.processes: dict[str, dict[str, Any]] = {}  # initialize processes attribute
        self.routines: dict[str, dict[str, Any]] = {}  # initialize routines attribute

        # initialize metadata attribute. NOT a dictionary since only one metadata class can exist in acquisition
        # TODO: Validation of config should check that metadata exists and only one
        self.metadata: AINDMetadataClass | None = None
        metadata = self._construct_class(self.config['acquisition']['metadata'])
        if metadata and isinstance(metadata, AINDMetadataClass):
            self.metadata = metadata
        else:
            raise ValueError('Invalid metadata configuration')
        # initialize acquisition_name that will be populated at start of acquisition
        self.acquisition_name: str | None = None

        # initialize operations
        for operation_type, operation_dict in self.config['acquisition']['operations'].items():
            setattr(self, operation_type, {})
            self._construct_operations(operation_type, operation_dict)

    def _load_class(self, driver: str, module: str, kwds: dict | None = None) -> object:
        """Loads a class dynamically.

        :param driver: The driver module name.
        :type driver: str
        :param module: The class name within the module.
        :type module: str
        :param kwds: Additional keyword arguments for class initialization, defaults to {}.
        :type kwds: dict, optional
        :return: The initialized class object.
        :rtype: object
        """
        self.log.info('loading %s.%s', driver, module)
        if kwds is None:
            kwds = {}
        __import__(driver)
        device_class = getattr(sys.modules[driver], module)
        return device_class(**kwds)

    def _setup_class(self, device: Any, properties: dict[str, Any]) -> None:
        """Sets up a class with given properties.

        :param device: The device object to set up.
        :type device: VoxelDevice
        :param properties: dictionary of properties to set on the device.
        :type properties: dict
        """
        self.log.info('setting up %s', device)
        # successively iterate through properties keys and if there is setter, set
        for key, value in properties.items():
            if hasattr(device, key):
                setattr(device, key, value)
            else:
                msg = f'{device} property {key} has no setter'
                raise ValueError(msg)

    def _construct_operations(self, device_name: str, operation_dictionary: dict) -> None:
        """Constructs operations for a given device.

        :param device_name: The name of the device.
        :type device_name: str
        :param operation_dictionary: dictionary of operations to construct.
        :type operation_dictionary: dict
        """
        for operation_name, operation_specs in operation_dictionary.items():
            operation_type = inflection.pluralize(operation_specs['type'])
            operation_object = self._construct_class(operation_specs)

            # create operation dictionary if it doesn't already exist and add operation to dictionary
            if not hasattr(self, operation_type):
                setattr(self, operation_type, {device_name: {}})
            elif not getattr(self, operation_type).get(device_name, False):
                getattr(self, operation_type)[device_name] = {}
            getattr(self, operation_type)[device_name][operation_name] = operation_object

    def _construct_class(self, class_specs: dict) -> object:
        """Constructs a class from specifications.

        :param class_specs: dictionary containing class specifications.
        :type class_specs: dict
        :return: The constructed class object.
        :rtype: object
        """
        driver = class_specs['driver']
        module = class_specs['module']
        init = class_specs.get('init', {})
        class_object = self._load_class(driver, module, init)
        properties = class_specs.get('properties', {})
        self.log.info('constructing %s', driver)
        self._setup_class(class_object, properties)
        return class_object

    @staticmethod
    def _collect_properties(obj: object) -> dict:
        """Collect properties of an object.

        :param obj: Object to collect properties from.
        :type obj: object
        :return: dictionary of properties.
        :rtype: dict
        """
        properties = {}
        for attr_name in dir(obj):
            attr = getattr(type(obj), attr_name, None)
            if attr is not None and (isinstance(attr, property) or isinstance(inspect.unwrap(attr), property)):
                properties[attr_name] = getattr(obj, attr_name)
        return properties

    def run(self) -> None:
        """Runs the acquisition process."""

    def update_current_state_config(self) -> None:
        """Update the current state configuration."""
        # update properties of operations
        for device_name, op_dict in self.config['acquisition']['operations'].items():
            for op_name, op_specs in op_dict.items():
                op = getattr(self, inflection.pluralize(op_specs['type']))[device_name][op_name]
                op_specs['properties'] = self._collect_properties(op)
        # update properties of metadata
        self.config['acquisition']['metadata']['properties'] = self._collect_properties(self.metadata)

    def save_config(self, path: Path) -> None:
        """Save the configuration to a file.

        :param path: Path to the configuration file.
        :type path: Path
        """
        with path.open('w') as f:
            self.yaml.dump(self.config, f)

    def stop_acquisition(self) -> None:
        """Stop the acquisition.

        :raises RuntimeError: Always raises a RuntimeError.
        """
        raise RuntimeError

    def close(self) -> None:
        """Close the acquisition."""
