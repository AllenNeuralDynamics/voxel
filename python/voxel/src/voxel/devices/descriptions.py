import inspect
from collections.abc import Callable
from typing import ClassVar

from pydantic import BaseModel

# Attribute attached to fget by @describe
DESCR_ATTR_NAME = '__voxel_description__'


class AttrDescription(BaseModel):
    label: str | None = None
    unit: str | None = None
    description: str | None = None
    read_only: bool = True
    # Filled by collector: "property" or "method"
    member_kind: str | None = None


def generate_ui_label(name: str) -> str:
    """Convert a snake_case attribute name into a Title Case UI label."""
    return name.replace('_', ' ').strip().title()


def describe[**P, R](
    label: str | None = None,
    unit: str | None = None,
    description: str | None = None,
    read_only: bool | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(fget: Callable[P, R]) -> Callable[P, R]:
        desc = AttrDescription(
            label=label if label is not None else generate_ui_label(fget.__name__),
            description=description if description is not None else fget.__doc__,
            unit=unit,
            read_only=True if read_only is None else read_only,
        )
        setattr(fget, DESCR_ATTR_NAME, desc)
        return fget

    return decorator


class WithDescriptions:
    """Mixin that collects property descriptions at class creation.

    Populates class attribute VOXEL_DESCRIPTIONS as a mapping:
        {property_name: VoxelPropertyDescription}

    Inheritance merge policy (robust, full MRO):
      - Merge farthest ancestors → nearest ancestors (so nearer wins),
      - Then overlay the subclass's own properties last (subclass wins).
    """

    VOXEL_DESCRIPTIONS: ClassVar[dict[str, AttrDescription]]

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        # Collect descriptions defined directly on this class
        own: dict[str, AttrDescription] = {}
        for name, attr in cls.__dict__.items():
            fget = None
            kind = None
            if isinstance(attr, property) and attr.fget is not None:
                fget = attr.fget
                kind = 'property'
            elif isinstance(attr, (staticmethod, classmethod)):
                fget = attr.__func__
                kind = 'method'
            elif inspect.isfunction(attr):
                fget = attr
                kind = 'method'

            if fget is not None:
                desc = getattr(fget, DESCR_ATTR_NAME, None)
                if isinstance(desc, AttrDescription):
                    own[name] = desc.model_copy(deep=True, update={'member_kind': kind})

        # Merge across full MRO (excluding cls itself)
        merged: dict[str, AttrDescription] = {}
        for base in reversed(cls.mro()[1:]):
            parent_map = getattr(base, 'VOXEL_DESCRIPTIONS', None)
            if isinstance(parent_map, dict):
                for k, v in parent_map.items():
                    merged[k] = v.model_copy(deep=True)

        # Overlay subclass's own items last
        merged.update(own)
        cls.VOXEL_DESCRIPTIONS = merged


if __name__ == '__main__':
    from rich import print

    class BaseClass(WithDescriptions):
        @property
        @describe(label='Example Property', description='Returns the number 42.')
        def example_property(self) -> int:
            """Returns the number 42."""
            return 42

        @describe(label='Calibrate', description='Run base calibration.')
        def calibrate(self, *, fast: bool = False) -> None:
            pass

        @staticmethod
        @describe(label='Utils', description='Static helper')
        def helper() -> str:
            return 'ok'

        @classmethod
        @describe(label='Factory', description='Construct from config')
        def from_config(cls, cfg: dict) -> 'BaseClass':
            print(cfg)
            return cls()

    class ExampleClass(BaseClass):
        @property
        @describe(unit='nm', description='Laser wavelength')
        def laser_wavelength(self) -> int:
            return 488

        @property
        @describe(label='Mode', description='Operating mode.')
        def mode(self) -> str:
            return 'continuous'

        @describe(label='Calibrate', description='Override calibration')
        def calibrate(self, *, fast: bool = True) -> None:
            pass

    ex = ExampleClass()
    print(f'Example Property: {ex.example_property}')
    print('Descriptions (merged across inheritance, properties + methods):')
    for k, v in ExampleClass.VOXEL_DESCRIPTIONS.items():
        print(f'  {k}: {v.model_dump()}')

    # Sanity checks
    assert 'example_property' in ExampleClass.VOXEL_DESCRIPTIONS
    assert ExampleClass.VOXEL_DESCRIPTIONS['calibrate'].member_kind == 'method'
    assert ExampleClass.VOXEL_DESCRIPTIONS['laser_wavelength'].member_kind == 'property'
    # classmethod/staticmethod captured as methods
    assert ExampleClass.VOXEL_DESCRIPTIONS['helper'].member_kind == 'method'
    assert ExampleClass.VOXEL_DESCRIPTIONS['from_config'].member_kind == 'method'
