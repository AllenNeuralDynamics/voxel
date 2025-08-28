import importlib
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field


class BuildSpec(BaseModel):
    """Specification for building an object.
    :raises: ValidationError: If the schema is invalid. e.g., missing required fields or type mismatches.
    """

    target: str = Field(..., description="Dotted path to the class (e.g., 'devices.camera.Camera')")
    args: list[Any] = Field(default_factory=list, description='List of positional arguments')
    kwargs: dict[str, Any] = Field(default_factory=dict, description='Dictionary of keyword arguments')

    def get_class(self) -> type:
        """Load and return the target class.

        Returns:
            The loaded class object

        Raises:
            ImportError: If the module cannot be imported
            AttributeError: If the class doesn't exist in the module

        """
        return _get_class_cached(self.target)


@lru_cache(maxsize=128)
def _get_class_cached(target: str) -> type:
    """Load and return a class from a target module path with caching.

    Args:
        target: Dotted path to the class (e.g., 'devices.camera.Camera')

    Returns:
        The loaded class object

    Raises:
        ImportError: If the module cannot be imported
        AttributeError: If the class doesn't exist in the module

    """
    module_path, cls_name = target.rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, cls_name)


type BuildSpecs = dict[str, BuildSpec]
