import copy
import importlib
import inspect
import logging
from functools import wraps
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Dict, Optional, Type

import inflection
from ruamel.yaml import YAML
from serial import Serial

from voxel_classic.descriptors.deliminated_property import _DeliminatedProperty


class Instrument:
    """Represents an instrument with various devices and configurations."""

    def __init__(self, config_path: str, yaml_handler: Optional[YAML] = None, log_level: str = "INFO"):
        """
        Initialize the Instrument class.

        :param config_path: Path to the configuration file.
        :type config_path: str
        :param yaml_handler: YAML handler for loading and dumping config, defaults to None.
        :type yaml_handler: YAML, optional
        :param log_level: Logging level, defaults to "INFO".
        :type log_level: str, optional
        """
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.log.setLevel(log_level)

        # create yaml object to use when loading and dumping config
        self.yaml = yaml_handler if yaml_handler is not None else YAML(typ="safe")

        self.config_path = Path(config_path)
        self.config = self.yaml.load(self.config_path)

        # store a dict of {device name: device type} for convenience
        self.channels: Dict[str, Any] = {}
        self.stage_axes: list = []

        # construct microscope
        self._construct()

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
                if laser_name not in self.lasers.keys():
                    raise ValueError(f"laser {laser_name} not in {self.lasers.keys()}")
            for filter in channel.get("filters", []):
                if filter not in self.filters.keys():
                    raise ValueError(f"filter wheel {filter} not in {self.filters.keys()}")
                if filter not in sum([list(v.filters.keys()) for v in self.filter_wheels.values()], []):
                    raise ValueError(f"filter {filter} not associated with any filter wheel: {self.filter_wheels}")
        self.channels = self.config["instrument"]["channels"]

    def _construct_device(self, device_name: str, device_specs: Dict[str, Any], lock: Optional[Lock] = None) -> None:
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
        device_object = self._load_device(driver, module, init, lock)
        properties = device_specs.get("properties", {})
        self._setup_device(device_object, properties)

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

        # Add subdevices under device and fill in any needed keywords to init
        for subdevice_name, subdevice_specs in device_specs.get("subdevices", {}).items():
            # copy so config is not altered by adding in parent devices
            self._construct_subdevice(device_object, subdevice_name, copy.deepcopy(subdevice_specs), lock)

    def _construct_subdevice(
        self, device_object: Any, subdevice_name: str, subdevice_specs: Dict[str, Any], lock: Lock
    ) -> None:
        """
        Construct a subdevice based on its specifications.

        :param device_object: Parent device object.
        :type device_object: object
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
            if parameter.annotation == Serial and Serial in [type(v) for v in device_object.__dict__.values()]:
                # assuming only one relevant serial port in parent
                subdevice_specs["init"][name] = [v for v in device_object.__dict__.values() if type(v) == Serial][0]
            # If subdevice init needs parent object type, add device object to init arguments
            elif parameter.annotation == type(device_object):
                subdevice_specs["init"][name] = device_object
        self._construct_device(subdevice_name, subdevice_specs, lock)

    def _load_device(self, driver: str, module: str, kwds: Dict[str, Any], lock: Lock) -> Any:
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
        return thread_safe_device_class(**kwds)

    def _setup_device(self, device: Any, properties: Dict[str, Any]) -> None:
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
                    isinstance(attr, property) or isinstance(inspect.unwrap(attr), property)
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


def for_all_methods(lock: Lock, cls: Type) -> Type:
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
        if type(attr) == _DeliminatedProperty:
            attr._fset = lock_methods(attr._fset, lock)
            attr._fget = lock_methods(attr._fget, lock)
        elif isinstance(attr, property):
            wrapped_getter = lock_methods(getattr(attr, "fget"), lock)
            # don't wrap setters if none
            wrapped_setter = lock_methods(getattr(attr, "fset"), lock) if getattr(attr, "fset") is not None else None
            setattr(cls, attr_name, property(wrapped_getter, wrapped_setter))
        elif callable(attr) and not isinstance(inspect.getattr_static(cls, attr_name), staticmethod):
            setattr(cls, attr_name, lock_methods(attr, lock))
    return cls


def lock_methods(fn: callable, lock: Lock) -> callable:
    """
    Apply a lock to a method to make it thread-safe.

    :param fn: Function to apply the lock to.
    :type fn: function
    :param lock: Lock for thread safety.
    :type lock: Lock
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
