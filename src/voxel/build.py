from collections.abc import Mapping
from typing import Any
from pydantic import BaseModel


class BuildSpec(BaseModel):
    driver: str
    kwds: dict[str, Any] = {}


class DeviceBuildSpec(BuildSpec):
    acq_pin: str | None = None


def parse_driver(driver: str) -> type:
    """Parse a driver string into a module and class name.
    :param driver: The driver string.
    :type driver: str
    :return: A tuple of the module and class name.
    :rtype: tuple[str, str]
    """
    module_name, class_name = driver.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    driver_class = getattr(module, class_name)
    if not isinstance(driver_class, type):
        raise TypeError(f"Attribute {class_name} in {module_name} is not a class.")
    return driver_class


def build_object(spec: "BuildSpec") -> Any:
    """Build an object from a build spec.
    :param spec: The build spec.
    :type spec: BuildSpec
    :return: The built object.
    :rtype: Any
    :raises TypeError: If the driver is not a class.
    """
    return parse_driver(spec.driver)(**spec.kwds)


def build_object_group(specs: Mapping[str, "BuildSpec"]) -> dict[str, Any]:
    """Build a group of objects from a group of build specs.
    :param specs: The build specs.
    :type specs: dict[str, BuildSpec]
    :return: A dictionary of the built objects.
    :rtype: dict[str, Any]
    """
    built_objects = {}

    def build_single_object(name: str) -> None:
        if name in built_objects:
            return
        if spec := specs.get(name):
            kwds = spec.kwds.copy()
            for key, value in kwds.items():
                if isinstance(value, str) and value in specs:
                    build_single_object(value)
                    kwds[key] = built_objects[value]
            driver = parse_driver(spec.driver)
            if "name" in driver.__init__.__code__.co_varnames:
                kwds["name"] = name  # check if driver takes name as kwarg or arg
            built_objects[name] = driver(**kwds)

    for name in specs:
        build_single_object(name)
    return built_objects
