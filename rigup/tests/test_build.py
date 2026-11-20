import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Literal

import pytest
import rigup.build as build_module
from rigup.build import BuildConfig, build_objects, build_objects_async
from rigup.device import Device

from rigup import Part, RigComponent

if TYPE_CHECKING:
    from decimal import Decimal


class Filter(Part, frozen=True):
    kind: Literal["filter"] = "filter"
    band: tuple[float, float]


class Cube(Part, frozen=True):
    kind: Literal["cube"] = "cube"
    excitation: Filter
    emission: Filter


class Wheel(Device, kind="wheel"):
    def __init__(self, device_id: str, slots: Mapping[str, RigComponent | str]):
        super().__init__(device_id)
        self.slots = dict(slots)


class Reader(Device, kind="reader"):
    def __init__(self, device_id: str, glass: Filter, spares: Sequence[Filter] = ()):
        super().__init__(device_id)
        self.glass = glass
        self.spares = list(spares)


class Loose(Device, kind="loose"):
    def __init__(self, device_id: str, glass: "Decimal"):
        super().__init__(device_id)
        self.glass = glass


class Plain:
    def __init__(self, device_id: str, value: int = 0):
        self.id = device_id
        self.value = value


class ReadOnly:
    def __init__(self, device_id: str):
        self.id = device_id

    @property
    def locked(self) -> bool:
        return True


class Dependent:
    def __init__(self, device_id: str, dependency: object):
        self.id = device_id
        self.dependency = dependency


def config(cls: str, **init: object) -> BuildConfig:
    return BuildConfig(target=f"{__name__}.{cls}", init=init)


WHEEL_WITH_PARTS = {
    "wheel": config("Wheel", slots={"0": "glass", "1": "cube", "2": "empty"}),
    "cube": config("Cube", excitation="blue", emission="glass"),
    "glass": config("Filter", band=[500, 550]),
    "blue": config("Filter", band=[450, 490]),
}
CYCLE = {
    "a": config("Dependent", dependency="b"),
    "b": config("Dependent", dependency="a"),
    "downstream": config("Dependent", dependency="a"),
}


def test_build_makes_each_object_from_its_init() -> None:
    configs = {"a": config("Plain", value=1), "b": config("Plain", value=2)}

    built, errors = build_objects(configs, Plain)

    assert errors == {}
    assert {device_id: obj.value for device_id, obj in built.items()} == {"a": 1, "b": 2}


async def test_async_build_makes_each_object_from_its_init() -> None:
    configs = {"a": config("Plain", value=1), "b": config("Plain", value=2)}

    built, errors = await build_objects_async(configs, Plain)

    assert errors == {}
    assert {device_id: obj.value for device_id, obj in built.items()} == {"a": 1, "b": 2}


def test_defaults_are_set_after_the_object_is_made() -> None:
    configs = {"dev": BuildConfig(target=f"{__name__}.Plain", init={}, defaults={"value": 42})}

    built, errors = build_objects(configs, Plain)

    assert errors == {}
    assert built["dev"].value == 42


async def test_a_default_that_cannot_be_set_is_a_build_error() -> None:
    configs = {"dev": BuildConfig(target=f"{__name__}.ReadOnly", init={}, defaults={"locked": False})}

    built, errors = await build_objects_async(configs, ReadOnly)

    assert built == {}
    assert errors["dev"].code == "build.defaults"


async def test_a_target_that_cannot_be_imported_is_a_build_error() -> None:
    configs = {"bad": BuildConfig(target="nonexistent.Module", init={})}

    built, errors = await build_objects_async(configs, Plain)

    assert built == {}
    assert errors["bad"].code == "build.import"


def test_a_class_that_is_not_1_of_the_bases_is_an_import_error() -> None:
    configs = {"dev": config("Plain")}

    built, errors = build_objects(configs, (Device, Part))

    assert built == {}
    assert errors["dev"].code == "build.import"
    assert "not a subclass of Device or Part" in errors["dev"].msg


def test_a_part_is_passed_to_a_device_and_to_a_part() -> None:
    built, errors = build_objects(WHEEL_WITH_PARTS, (Device, Part))

    assert errors == {}
    wheel, cube, glass = built["wheel"], built["cube"], built["glass"]
    assert isinstance(wheel, Wheel)
    assert isinstance(cube, Cube)
    assert wheel.slots == {"0": glass, "1": cube, "2": "empty"}
    assert cube.emission is glass
    assert {device_id: component.kind for device_id, component in built.items()} == {
        "wheel": "wheel",
        "cube": "cube",
        "glass": "filter",
        "blue": "filter",
    }


async def test_async_build_passes_parts() -> None:
    built, errors = await build_objects_async(WHEEL_WITH_PARTS, (Device, Part))

    assert errors == {}
    wheel = built["wheel"]
    assert isinstance(wheel, Wheel)
    assert wheel.slots["1"] is built["cube"]


def test_a_part_with_a_wrong_value_is_not_built() -> None:
    configs = {"glass": config("Filter", band="wide")}

    built, errors = build_objects(configs, Part)

    assert built == {}
    assert errors["glass"].code == "build.instantiation"


def test_a_ready_object_is_passed_and_not_built_again() -> None:
    glass = Filter(id="glass", band=(500, 550))
    configs = {"wheel": config("Wheel", slots={"0": "glass", "1": "empty"}), "reader": config("Reader", glass="glass")}

    built, errors = build_objects(configs, Device, ready={"glass": glass})

    assert errors == {}
    assert set(built) == {"wheel", "reader"}
    assert built["wheel"].slots == {"0": glass, "1": "empty"}
    assert built["reader"].glass is glass


async def test_a_ready_object_is_checked_against_the_hint() -> None:
    cube = Cube(id="cube", excitation=Filter(id="a", band=(1, 2)), emission=Filter(id="b", band=(3, 4)))
    configs = {"reader": config("Reader", glass="cube"), "wheel": config("Wheel", slots={"0": "cube"})}

    built, errors = await build_objects_async(configs, Device, ready={"cube": cube})

    assert set(built) == {"wheel"}
    assert built["wheel"].slots == {"0": cube}
    assert errors["reader"].msg == "'reader.glass' needs a Filter, and 'cube' is a Cube"


def test_a_component_that_fits_the_hint_is_passed() -> None:
    configs = {**WHEEL_WITH_PARTS, "reader": config("Reader", glass="glass", spares=["blue"])}

    built, errors = build_objects(configs, (Device, Part))

    assert errors == {}
    reader = built["reader"]
    assert isinstance(reader, Reader)
    assert reader.glass is built["glass"]
    assert reader.spares == [built["blue"]]


def test_a_component_of_a_different_class_is_refused() -> None:
    configs = {**WHEEL_WITH_PARTS, "reader": config("Reader", glass="cube")}

    built, errors = build_objects(configs, (Device, Part))

    assert "reader" not in built
    assert errors["reader"].code == "build.dependency"
    assert errors["reader"].msg == "'reader.glass' needs a Filter, and 'cube' is a Cube"


async def test_each_component_in_a_list_is_checked() -> None:
    configs = {**WHEEL_WITH_PARTS, "reader": config("Reader", glass="glass", spares=["blue", "wheel"])}

    built, errors = await build_objects_async(configs, (Device, Part))

    assert "reader" not in built
    assert errors["reader"].msg == "'reader.spares' needs a Filter, and 'wheel' is a Wheel"


def test_a_hint_that_cannot_be_read_is_not_checked(caplog: pytest.LogCaptureFixture) -> None:
    configs = {**WHEEL_WITH_PARTS, "loose": config("Loose", glass="cube")}

    with caplog.at_level(logging.WARNING, logger=build_module.__name__):
        built, errors = build_objects(configs, (Device, Part))

    assert errors == {}
    assert "loose" in built
    assert "Cannot read the type hints of Loose" in caplog.text


async def test_a_failed_dependency_fails_every_dependent() -> None:
    configs = {
        "root": BuildConfig(target="nonexistent.Module", init={}),
        "middle": config("Dependent", dependency="root"),
        "leaf": config("Dependent", dependency="middle"),
        "nested": config("Dependent", dependency={"nested": ["root"]}),
    }

    built, errors = await build_objects_async(configs)

    assert built == {}
    assert {device_id: error.code for device_id, error in errors.items()} == {
        "root": "build.import",
        "middle": "build.dependency",
        "leaf": "build.dependency",
        "nested": "build.dependency",
    }


def test_a_cycle_is_reported_as_circular() -> None:
    built, errors = build_objects(CYCLE)

    assert built == {}
    assert {device_id: error.code for device_id, error in errors.items()} == {
        "a": "build.circular",
        "b": "build.circular",
        "downstream": "build.dependency",
    }


async def test_async_build_reports_a_cycle_and_builds_the_rest() -> None:
    configs = {**CYCLE, "independent": config("Plain")}

    built, errors = await build_objects_async(configs)

    assert set(built) == {"independent"}
    assert {device_id: error.code for device_id, error in errors.items()} == {
        "a": "build.circular",
        "b": "build.circular",
        "downstream": "build.dependency",
    }
