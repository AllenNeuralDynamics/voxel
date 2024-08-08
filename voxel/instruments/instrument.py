import logging
from pathlib import Path
import inspect
import importlib
from serial import Serial
from ruamel.yaml import YAML
import inflection
from threading import Lock, RLock
from functools import wraps
from voxel.descriptors.deliminated_property import _DeliminatedProperty
import copy

class Instrument:

    def __init__(self, config_path: str, yaml_handler: YAML = None, log_level='INFO'):
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.log.setLevel(log_level)

        # create yaml object to use when loading and dumping config
        self.yaml = yaml_handler if yaml_handler is not None else YAML()

        self.config_path = Path(config_path)
        self.config = self.yaml.load(self.config_path)

        # store a dict of {device name: device type} for convenience
        self.channels = {}
        self.stage_axes = []

        # construct microscope
        self._construct()

    def _construct(self):
        """Construct device based on configuration yaml"""
        self.log.info(f'constructing instrument from {self.config_path}')
        # grab instrument id
        try:
            self.id = self.config['instrument']['id']
        except:
            raise ValueError('no instrument id defined. check yaml file.')
        # construct devices
        for device_name, device_specs in self.config['instrument']['devices'].items():
            self._construct_device(device_name, device_specs)

        # TODO: need somecheck to make sure if multiple filters, they don't come from the same wheel
        # construct and verify channels
        for channel in self.config['instrument']['channels'].values():
            for laser_name in channel.get('lasers', []):
                if laser_name not in self.lasers.keys():
                    raise ValueError(f'laser {laser_name} not in {self.lasers.keys()}')
            for filter in channel.get('filters', []):
                if filter not in self.filters.keys():
                    raise ValueError(f'filter wheel {filter} not in {self.filters.keys()}')
                if filter not in sum([list(v.filters.keys()) for v in self.filter_wheels.values()], []):
                    raise ValueError(f'filter {filter} not associated with any filter wheel: {self.filter_wheels}')
        self.channels = self.config['instrument']['channels']

    def _construct_device(self, device_name, device_specs, lock: Lock = None):
        """Load, setup, and add any sub-devices or tasks of a device. Also wrap class methods and properties with
        thread safe locking function

        :param device_name: name of device
        :param device_specs: dictionary dictating how device should be set up
        :param lock: lock to be used for device and sub-devices
        """

        self.log.info(f'constructing {device_name}')
        lock = RLock() if lock is None else lock
        device_type = inflection.pluralize(device_specs['type'])
        driver = device_specs['driver']
        module = device_specs['module']
        init = device_specs.get('init', {})
        device_object = self._load_device(driver, module, init, lock)
        properties = device_specs.get('properties', {})
        self._setup_device(device_object, properties)

        # create device dictionary if it doesn't already exist and add device to dictionary
        if not hasattr(self, device_type):
            setattr(self, device_type, {})
        getattr(self, device_type)[device_name] = device_object

        # added logic for stages to store and check stage axes
        if device_type == 'tiling_stages' or device_type == 'scanning_stages':
            instrument_axis = device_specs['init']['instrument_axis']
            if instrument_axis in self.stage_axes:
                raise ValueError(f'{instrument_axis} is duplicated and already exists!')
            else:
                self.stage_axes.append(instrument_axis)

        # Add subdevices under device and fill in any needed keywords to init
        for subdevice_name, subdevice_specs in device_specs.get('subdevices', {}).items():
            # copy so config is not altered by adding in parent devices
            self._construct_subdevice(device_object, subdevice_name, copy.deepcopy(subdevice_specs), lock)

    def _construct_subdevice(self, device_object, subdevice_name, subdevice_specs, lock):
        """Handle the case where devices share serial ports or device objects
        :param device_object: parent device setup before sub-device
        :param subdevice_name: name of sub-device
        :param subdevice_specs: dictionary dictating how sub-device should be set up
        :param lock: lock to be used for device and sub-devices"""

        # Import subdevice class in order to access keyword argument required in the init of the device
        subdevice_class = getattr(importlib.import_module(subdevice_specs['driver']), subdevice_specs['module'])
        subdevice_needs = inspect.signature(subdevice_class.__init__).parameters
        kwds = {}
        for name, parameter in subdevice_needs.items():
            # If subdevice init needs a serial port, add device's serial port to init arguments
            if parameter.annotation == Serial and Serial in [type(v) for v in device_object.__dict__.values()]:
                # assuming only one relevant serial port in parent
                subdevice_specs['init'][name] = [v for v in device_object.__dict__.values() if type(v) == Serial][0]
            # If subdevice init needs parent object type, add device object to init arguments
            elif parameter.annotation == type(device_object):
                subdevice_specs['init'][name] = device_object
        self._construct_device(subdevice_name, subdevice_specs, lock)

    def _load_device(self, driver: str, module: str, kwds, lock: Lock):
        """Load device based on driver, module, and kwds specified. Also wrap class methods and properties with
        thread safe locking function

        :param driver: driver of device
        :param module: specific class of device within driver
        :param kwds: keyword argument required in the init of the device,
        :param lock: lock to be used for device and sub-devices """

        self.log.info(f'loading {driver}.{module}')
        device_class = getattr(importlib.import_module(driver), module)
        thread_safe_device_class = for_all_methods(lock, device_class)
        return thread_safe_device_class(**kwds)


    def _setup_device(self, device: object, properties: dict):
        """Setup device based on property dictionary
        :param device: device to be setup
        :param properties: dictionary of attributes, values to set according to config"""

        self.log.info(f'setting up {device}')
        # successively iterate through properties keys and if there is setter, set
        for key, value in properties.items():
            try:
                setattr(device, key, value)
            except (TypeError, AttributeError):
                self.log.info(f'{device} property {key} has no setter')

    def update_current_state_config(self):
        """Capture current state of instrument in config form"""

        for device_name, device_specs in self.config['instrument']['devices'].items():
            device = getattr(self, inflection.pluralize(device_specs['type']))[device_name]
            properties = {}
            for attr_name in dir(device):
                attr = getattr(type(device), attr_name, None)
                if isinstance(attr, property) or isinstance(inspect.unwrap(attr), property):
                    properties[attr_name] = getattr(device, attr_name)
            device_specs['properties'] = properties

    def save_config(self, path: Path):
        """Save current config to path provided
        :param path: path to save config to"""
        with path.open("w") as f:
            self.yaml.dump(self.config, f)

    def close(self):
        """Close functionality"""
        pass


def for_all_methods(lock, cls):
    """Function that iterates through callable methods and properties in a class and wraps with lock_methods"""
    for attr_name in cls.__dict__:
        if attr_name == '__init__':
            continue
        attr = getattr(cls, attr_name)
        if type(attr) == _DeliminatedProperty:
            attr._fset = lock_methods(attr._fset, lock)
            attr._fget = lock_methods(attr._fget, lock)
        elif isinstance(attr, property):
            wrapped_getter = lock_methods(getattr(attr, 'fget'), lock)
            wrapped_setter = lock_methods(getattr(attr, 'fset'), lock)
            setattr(cls, attr_name, property(wrapped_getter, wrapped_setter))
        elif callable(attr) and not isinstance(inspect.getattr_static(cls, attr_name), staticmethod):
            setattr(cls, attr_name, lock_methods(attr, lock))
    return cls

def lock_methods(fn, lock):
    """Wrapper that locks lock shared by all methods and properties so class is thread safe"""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        with lock:
            return fn(*args, **kwargs)
    return wrapper