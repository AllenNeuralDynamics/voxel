import copy
import importlib
import inspect
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any, TypedDict

import inflection
from ruamel.yaml import YAML
from serial import Serial
from voxel.utils.log import VoxelLogging
from voxel_classic.descriptors.deliminated_property import _DeliminatedProperty

if TYPE_CHECKING:
    from voxel_classic.devices.camera.base import BaseCamera
    from voxel_classic.devices.daq.ni import NIDAQ
    from voxel_classic.devices.filter.base import BaseFilter
    from voxel_classic.devices.filterwheel.base import BaseFilterWheel
    from voxel_classic.devices.flip_mount.base import BaseFlipMount
    from voxel_classic.devices.indicator_light.base import BaseIndicatorLight
    from voxel_classic.devices.laser.base import BaseLaser
    from voxel_classic.devices.stage.asi.tiger import TigerStage


class ChannelInfo(TypedDict):
    """TypedDict for channel information."""

    lasers: list[str]
    cameras: list[str]
    focusing_stages: list[str]
    filters: list[str]


class Instrument:
    """Represents an instrument with various devices and configurations."""

    def __init__(self, config_path: str | Path, yaml_handler: YAML | None = None, log_level: str = "INFO"):
        """
        Initialize the Instrument class.

        :param config_path: Path to the configuration file.
        :type config_path: str
        :param yaml_handler: YAML handler for loading and dumping config, defaults to None.
        :type yaml_handler: YAML, optional
        :param log_level: Logging level, defaults to "INFO".
        :type log_level: str, optional
        """
        self.log = VoxelLogging.get_logger(object=self)
        self.log.setLevel(log_level)

        # create yaml object to use when loading and dumping config
        self.yaml = yaml_handler if yaml_handler is not None else YAML(typ="safe")

        self.config_path = Path(config_path)
        self.config = self.yaml.load(self.config_path)

        # store a dict of {device name: device type} for convenience
        self.channels: dict[str, Any] = {}
        self.stage_axes: list = []

        self.cameras: dict[str, BaseCamera] = {}
        self.lasers: dict[str, BaseLaser] = {}
        self.filters: dict[str, BaseFilter] = {}
        self.filter_wheels: dict[str, BaseFilterWheel] = {}
        self.daqs: dict[str, NIDAQ] = {}
        self.scanning_stages: dict[str, TigerStage] = {}
        self.tiling_stages: dict[str, TigerStage] = {}
        self.flip_mounts: dict[str, BaseFlipMount] = {}
        self.focusing_stages: dict[str, TigerStage] = {}
        self.controllers: dict[str, Any] = {}
        self.indicator_lights: dict[str, BaseIndicatorLight] = {}

        # construct microscope
        self._construct()

    @property
    def channel_infos(self) -> dict[str, ChannelInfo]:
        """
        Get channel information for the instrument.

        :return: A dictionary containing channel information.
        :rtype: dict[str, ChannelInfo]
        """
        return {
            channel_name: ChannelInfo(
                lasers=channel.get("lasers", []),
                cameras=channel.get("cameras", []),
                focusing_stages=channel.get("focusing_stages", []),
                filters=channel.get("filters", []),
            )
            for channel_name, channel in self.channels.items()
        }

    def _construct(self) -> None:
        """
        Construct the instrument from the configuration file.

        :raises ValueError: If the instrument ID or device configurations are invalid.
        """
        self.log.info(f"constructing instrument from {self.config_path}")
        # grab instrument id
        try:
            self.id = self.config["instrument"]["id"]
        except KeyError:
            raise ValueError("no instrument id defined. check yaml file.")
        # construct devices
        for device_name, device_specs in self.config["instrument"]["devices"].items():
            self._construct_device(device_name, device_specs)

        # TODO: need somecheck to make sure if multiple filters, they don't come from the same wheel
        # construct and verify channels
        for channel in self.config["instrument"]["channels"].values():
            for laser_name in channel.get("lasers", []):
                if laser_name not in self.lasers:
                    raise ValueError(f"laser {laser_name} not in {self.lasers.keys()}")
            for filter in channel.get("filters", []):
                if filter not in self.filters:
                    raise ValueError(f"filter wheel {filter} not in {self.filters.keys()}")
                if filter not in sum([list(v.filters.keys()) for v in self.filter_wheels.values()], []):
                    raise ValueError(f"filter {filter} not associated with any filter wheel: {self.filter_wheels}")
        self.channels = self.config["instrument"]["channels"]

    def _construct_device(self, device_name: str, device_specs: dict[str, Any], lock: "RLock | None" = None) -> None:
        """
        Construct a device based on its specifications.

        :param device_name: Name of the device.
        :type device_name: str
        :param device_specs: Specifications of the device.
        :type device_specs: dict
        :param lock: Lock for thread safety, defaults to None.
        :type lock: Lock, optional
        :raises ValueError: If the device configuration is invalid.
        """
        self.log.info(f"constructing {device_name}")
        lock = RLock() if lock is None else lock
        device_type = inflection.pluralize(device_specs["type"])
        driver = device_specs["driver"]
        module = device_specs["module"]
        init = device_specs.get("init", {})

        device_class = getattr(importlib.import_module(driver), module)
        thread_safe_device_class = for_all_methods(lock, device_class)
        self.log.debug(f"Imported thread-safe device class for {driver}.{module}")
        device_object = thread_safe_device_class(**init)
        self.log.debug(f"Constructed thread-safe device instance for {driver}.{module}")

        properties = device_specs.get("properties", {})
        self._setup_device(device_object, properties)
        self.log.debug(f"Setup properties for device '{device_name}': {properties}")

        # Add subdevices under device and fill in any needed keywords to init
        for subdevice_name, subdevice_specs in device_specs.get("subdevices", {}).items():
            # copy so config is not altered by adding in parent devices
            self.log.debug(f"Constructing subdevice '{subdevice_name}' for parent '{device_name}'")
            self._construct_subdevice(device_object, subdevice_name, copy.deepcopy(subdevice_specs), lock)

        # create device dictionary if it doesn't already exist and add device to dictionary
        if not hasattr(self, device_type):
            setattr(self, device_type, {})
        getattr(self, device_type)[device_name] = device_object

        # added logic for stages to store and check stage axes
        if device_type == "tiling_stages" or device_type == "scanning_stages":
            instrument_axis = device_specs["init"]["instrument_axis"]
            if instrument_axis in self.stage_axes:
                raise ValueError(f"{instrument_axis} is duplicated and already exists!")
            else:
                self.stage_axes.append(instrument_axis)

    def _construct_subdevice(
        self, parent_object: Any, subdevice_name: str, subdevice_specs: dict[str, Any], lock: RLock
    ) -> None:
        """
        Construct a subdevice based on its specifications.

        :param parent_object: Parent device object.
        :type parent_object: Any
        :param subdevice_name: Name of the subdevice.
        :type subdevice_name: str
        :param subdevice_specs: Specifications of the subdevice.
        :type subdevice_specs: dict
        :param lock: Lock for thread safety.
        :type lock: Lock
        """
        # Import subdevice class in order to access keyword argument required in the init of the device
        subdevice_class = getattr(importlib.import_module(subdevice_specs["driver"]), subdevice_specs["module"])
        subdevice_needs = inspect.signature(subdevice_class.__init__).parameters
        for name, parameter in subdevice_needs.items():
            # If subdevice init needs a serial port, add device's serial port to init arguments
            if parameter.annotation == Serial and Serial in [type(v) for v in parent_object.__dict__.values()]:
                # assuming only one relevant serial port in parent
                subdevice_specs["init"][name] = [v for v in parent_object.__dict__.values() if isinstance(v, Serial)][0]
            # If subdevice init needs parent object type, add device object to init arguments
            # Check by annotation type, parameter name, or if parent is instance of expected type
            elif (
                parameter.annotation is type(parent_object)
                or name in ["tigerbox", "parent", "controller", "daq"]
                or (
                    hasattr(parameter.annotation, "__name__")
                    and parameter.annotation.__name__ in type(parent_object).__name__
                )
            ):
                subdevice_specs["init"][name] = parent_object
            else:
                # Safely check isinstance, handling parameterized generics
                try:
                    if hasattr(parameter.annotation, "__origin__"):
                        # Skip parameterized generics like List[str], Dict[str, Any], etc.
                        is_parent_instance = False
                    else:
                        is_parent_instance = isinstance(parent_object, parameter.annotation)

                    if is_parent_instance:
                        subdevice_specs["init"][name] = parent_object
                except (TypeError, AttributeError):
                    # Handle cases where isinstance fails (e.g., parameterized generics)
                    pass
        self.log.debug(f"Constructing subdevice '{subdevice_name}' with specs: {subdevice_specs}")
        self._construct_device(subdevice_name, subdevice_specs, lock)

    def _load_device(self, driver: str, module: str, kwds: dict[str, Any], lock: RLock) -> Any:
        """
        Load a device class and make it thread-safe.

        :param driver: Driver module of the device.
        :type driver: str
        :param module: Module name of the device.
        :type module: str
        :param kwds: Initialization keywords for the device.
        :type kwds: dict
        :param lock: Lock for thread safety.
        :type lock: Lock
        :return: Thread-safe device object.
        :rtype: object
        """
        self.log.info(f"loading {driver}.{module}")
        device_class = getattr(importlib.import_module(driver), module)
        thread_safe_device_class = for_all_methods(lock, device_class)
        self.log.debug(f"Constructed thread-safe device class for {driver}.{module}")
        return thread_safe_device_class(**kwds)

    def _setup_device(self, device: Any, properties: dict[str, Any]) -> None:
        """
        Set up a device with its properties.

        :param device: Device object.
        :type device: object
        :param properties: Properties to set on the device.
        :type properties: dict
        """
        self.log.info(f"setting up {device}")
        # successively iterate through properties keys and if there is setter, set
        for key, value in properties.items():
            if hasattr(device, key):
                setattr(device, key, value)
            else:
                raise ValueError(f"{device} property {key} has no setter")

    def update_current_state_config(self) -> None:
        """
        Update the current state configuration of the instrument.
        """
        for device_name, device_specs in self.config["instrument"]["devices"].items():
            device = getattr(self, inflection.pluralize(device_specs["type"]))[device_name]
            properties = {}
            for attr_name in dir(device):
                attr = getattr(type(device), attr_name, None)
                if (
                    attr is not None and (isinstance(attr, property) or isinstance(inspect.unwrap(attr), property))
                ) and attr_name != "latest_frame":
                    properties[attr_name] = getattr(device, attr_name)
            device_specs["properties"] = properties

    def save_config(self, path: Path) -> None:
        """
        Save the current configuration to a file.

        :param path: Path to save the configuration file.
        :type path: Path
        """
        with path.open("w") as f:
            self.yaml.dump(self.config, f)

    def close(self) -> None:
        """
        Close the instrument and release any resources.
        """
        pass


def for_all_methods(lock: RLock, cls: type) -> type:
    """
    Apply a lock to all methods of a class to make them thread-safe.

    :param lock: Lock for thread safety.
    :type lock: Lock
    :param cls: Class to apply the lock to.
    :type cls: type
    :return: Class with thread-safe methods.
    :rtype: type
    """
    for attr_name in cls.__dict__:
        if attr_name == "__init__":
            continue
        attr = getattr(cls, attr_name)
        if isinstance(attr, _DeliminatedProperty):
            attr._fset = lock_methods(attr._fset, lock) if attr._fset is not None else None
            attr._fget = lock_methods(attr._fget, lock)
        elif isinstance(attr, property):
            wrapped_getter = lock_methods(getattr(attr, "fget"), lock)
            # don't wrap setters if none
            wrapped_setter = lock_methods(getattr(attr, "fset"), lock) if getattr(attr, "fset") is not None else None
            setattr(cls, attr_name, property(wrapped_getter, wrapped_setter))
        elif callable(attr) and not isinstance(inspect.getattr_static(cls, attr_name), staticmethod):
            setattr(cls, attr_name, lock_methods(attr, lock))
    return cls


def lock_methods(fn: Callable, lock: RLock) -> Callable:
    """
    Apply a lock to a method to make it thread-safe.

    :param fn: Function to apply the lock to.
    :type fn: function
    :param lock: Lock for thread safety.
    :type lock: RLock
    :return: Thread-safe function.
    :rtype: function
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """
        Wrapper function to apply the lock.

        :return: Result of the original function.
        :rtype: Any
        """
        with lock:
            return fn(*args, **kwargs)

    return wrapper
