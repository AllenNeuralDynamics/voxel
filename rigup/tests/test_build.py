"""Tests for rigup.build — defaults failure semantics and async build."""

import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Literal

import pytest
import rigup.build as build_module
from rigup.build import BuildConfig, build_objects, build_objects_async

from rigup import Device, Part, RigComponent

if TYPE_CHECKING:
    from decimal import Decimal


class _Filter(Part, frozen=True):
    kind: Literal["filter"] = "filter"
    band: tuple[float, float]


class _Cube(Part, frozen=True):
    kind: Literal["cube"] = "cube"
    excitation: _Filter
    emission: _Filter


class _Wheel(Device, kind="wheel"):
    def __init__(self, uid: str, slots: Mapping[str, RigComponent | str]):
        super().__init__(uid)
        self.slots = dict(slots)


class _Reader(Device, kind="reader"):
    def __init__(self, uid: str, glass: _Filter, spares: Sequence[_Filter] = ()):
        super().__init__(uid)
        self.glass = glass
        self.spares = list(spares)


class _Loose(Device, kind="loose"):
    def __init__(self, uid: str, glass: "Decimal"):  # a hint that cannot be read when the code runs
        super().__init__(uid)
        self.glass = glass


class _GoodDevice:
    def __init__(self, uid: str, value: int = 0):
        self.uid = uid
        self._value = value

    @property
    def value(self) -> int:
        return self._value

    @value.setter
    def value(self, v: int) -> None:
        self._value = v


class _ReadOnlyDevice:
    def __init__(self, uid: str):
        self.uid = uid

    @property
    def locked(self) -> bool:
        return True


class _DependentDevice:
    def __init__(self, uid: str, dependency: object):
        self.uid = uid
        self.dependency = dependency


class TestDefaultsFailure:
    def test_successful_defaults(self):
        configs = {
            "dev": BuildConfig(
                target=f"{__name__}._GoodDevice",
                init={},
                defaults={"value": 42},
            ),
        }
        built, errors = build_objects(configs, _GoodDevice)
        assert "dev" in built
        assert not errors
        assert built["dev"].value == 42

    def test_failing_defaults_produce_build_error(self):
        configs = {
            "dev": BuildConfig(
                target=f"{__name__}._ReadOnlyDevice",
                init={},
                defaults={"locked": False},
            ),
        }
        built, errors = build_objects(configs, _ReadOnlyDevice)
        assert "dev" not in built
        assert "dev" in errors
        assert errors["dev"].code == "build.defaults"

    def test_no_defaults_is_fine(self):
        configs = {
            "dev": BuildConfig(target=f"{__name__}._GoodDevice", init={}),
        }
        built, errors = build_objects(configs, _GoodDevice)
        assert "dev" in built
        assert not errors


class TestAsyncBuild:
    async def test_async_build_creates_objects(self):
        configs = {
            "a": BuildConfig(target=f"{__name__}._GoodDevice", init={"value": 1}),
            "b": BuildConfig(target=f"{__name__}._GoodDevice", init={"value": 2}),
        }
        built, errors = await build_objects_async(configs, _GoodDevice)
        assert len(built) == 2
        assert not errors
        assert built["a"].value == 1
        assert built["b"].value == 2

    async def test_async_build_with_bad_target(self):
        configs = {
            "bad": BuildConfig(target="nonexistent.Module", init={}),
        }
        built, errors = await build_objects_async(configs, _GoodDevice)
        assert not built
        assert "bad" in errors
        assert errors["bad"].code == "build.import"

    async def test_async_defaults_failure(self):
        configs = {
            "dev": BuildConfig(
                target=f"{__name__}._ReadOnlyDevice",
                init={},
                defaults={"locked": False},
            ),
        }
        built, errors = await build_objects_async(configs, _ReadOnlyDevice)
        assert "dev" not in built
        assert errors["dev"].code == "build.defaults"


def _config(cls: str, **init: object) -> BuildConfig:
    return BuildConfig(target=f"{__name__}.{cls}", init=init)


_WHEEL_WITH_PARTS = {
    "wheel": BuildConfig(target=f"{__name__}._Wheel", init={"slots": {"0": "glass", "1": "cube", "2": "empty"}}),
    "cube": BuildConfig(target=f"{__name__}._Cube", init={"excitation": "blue", "emission": "glass"}),
    "glass": BuildConfig(target=f"{__name__}._Filter", init={"band": [500, 550]}),
    "blue": BuildConfig(target=f"{__name__}._Filter", init={"band": [450, 490]}),
}


class TestParts:
    def test_a_part_is_passed_to_a_device_and_to_a_part(self):
        built, errors = build_objects(_WHEEL_WITH_PARTS, (Device, Part))

        assert not errors
        wheel, cube, glass = built["wheel"], built["cube"], built["glass"]
        assert isinstance(wheel, _Wheel)
        assert isinstance(cube, _Cube)
        assert wheel.slots == {"0": glass, "1": cube, "2": "empty"}
        assert cube.emission is glass
        assert {uid: component.kind for uid, component in built.items()} == {
            "wheel": "wheel",
            "cube": "cube",
            "glass": "filter",
            "blue": "filter",
        }

    async def test_async_build_passes_parts(self):
        built, errors = await build_objects_async(_WHEEL_WITH_PARTS, (Device, Part))

        assert not errors
        wheel = built["wheel"]
        assert isinstance(wheel, _Wheel)
        assert wheel.slots["1"] is built["cube"]

    def test_a_class_that_is_not_1_of_the_bases_is_an_import_error(self):
        configs = {"dev": BuildConfig(target=f"{__name__}._GoodDevice", init={})}

        built, errors = build_objects(configs, (Device, Part))

        assert not built
        assert errors["dev"].code == "build.import"
        assert "not a subclass of Device or Part" in errors["dev"].msg

    def test_a_part_with_a_wrong_value_is_not_built(self):
        configs = {"glass": BuildConfig(target=f"{__name__}._Filter", init={"band": "wide"})}

        built, errors = build_objects(configs, Part)

        assert not built
        assert errors["glass"].code == "build.instantiation"

    def test_a_ready_object_is_passed_and_not_built_again(self):
        glass = _Filter(uid="glass", band=(500, 550))
        configs = {
            "wheel": _config("_Wheel", slots={"0": "glass", "1": "empty"}),
            "reader": _config("_Reader", glass="glass"),
        }

        built, errors = build_objects(configs, Device, ready={"glass": glass})

        assert not errors
        assert set(built) == {"wheel", "reader"}
        assert built["wheel"].slots == {"0": glass, "1": "empty"}
        assert built["reader"].glass is glass

    async def test_async_build_checks_a_ready_object_against_the_hint(self):
        cube = _Cube(uid="cube", excitation=_Filter(uid="a", band=(1, 2)), emission=_Filter(uid="b", band=(3, 4)))
        configs = {"reader": _config("_Reader", glass="cube"), "wheel": _config("_Wheel", slots={"0": "cube"})}

        built, errors = await build_objects_async(configs, Device, ready={"cube": cube})

        assert set(built) == {"wheel"}
        assert built["wheel"].slots == {"0": cube}
        assert errors["reader"].msg == "'reader.glass' needs a _Filter, and 'cube' is a _Cube"


class TestPassedTypes:
    def test_a_component_that_fits_the_hint_is_passed(self):
        configs = {**_WHEEL_WITH_PARTS, "reader": _config("_Reader", glass="glass", spares=["blue"])}

        built, errors = build_objects(configs, (Device, Part))

        assert not errors
        reader = built["reader"]
        assert isinstance(reader, _Reader)
        assert reader.glass is built["glass"]
        assert reader.spares == [built["blue"]]

    def test_a_component_of_a_different_class_is_refused(self):
        configs = {**_WHEEL_WITH_PARTS, "reader": _config("_Reader", glass="cube")}

        built, errors = build_objects(configs, (Device, Part))

        assert "reader" not in built
        assert errors["reader"].code == "build.dependency"
        assert errors["reader"].msg == "'reader.glass' needs a _Filter, and 'cube' is a _Cube"

    async def test_each_component_in_a_list_is_checked(self):
        configs = {**_WHEEL_WITH_PARTS, "reader": _config("_Reader", glass="glass", spares=["blue", "wheel"])}

        built, errors = await build_objects_async(configs, (Device, Part))

        assert "reader" not in built
        assert errors["reader"].msg == "'reader.spares' needs a _Filter, and 'wheel' is a _Wheel"

    def test_a_hint_that_cannot_be_read_is_not_checked(self, caplog: pytest.LogCaptureFixture):
        configs = {**_WHEEL_WITH_PARTS, "loose": _config("_Loose", glass="cube")}

        with caplog.at_level(logging.WARNING, logger=build_module.__name__):
            built, errors = build_objects(configs, (Device, Part))

        assert not errors
        assert "loose" in built
        assert "Cannot read the type hints of _Loose" in caplog.text


class TestDependencyFailures:
    async def test_failed_dependency_skips_transitive_dependents(self, monkeypatch):
        configs = {
            "root": BuildConfig(target="nonexistent.Module", init={}),
            "middle": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "root"}),
            "leaf": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "middle"}),
        }
        prewarmed: set[str] = set()

        def record_prewarmed(cfgs):
            prewarmed.update(cfgs)

        monkeypatch.setattr(build_module, "_prewarm_parent_modules", record_prewarmed)

        built, errors = await build_objects_async(configs)

        assert not built
        assert errors["root"].code == "build.import"
        assert errors["middle"].code == "build.dependency"
        assert errors["leaf"].code == "build.dependency"
        assert prewarmed == {"root"}

    async def test_nested_failed_dependency_is_detected(self):
        configs = {
            "root": BuildConfig(target="nonexistent.Module", init={}),
            "dependent": BuildConfig(
                target=f"{__name__}._DependentDevice",
                init={"dependency": {"nested": ["root"]}},
            ),
        }

        built, errors = await build_objects_async(configs)

        assert not built
        assert errors["dependent"].code == "build.dependency"

    def test_sync_cycles_are_reported_explicitly(self):
        configs = {
            "a": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "b"}),
            "b": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "a"}),
            "downstream": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "a"}),
        }

        built, errors = build_objects(configs)

        assert not built
        assert errors["a"].code == "build.circular"
        assert errors["b"].code == "build.circular"
        assert errors["downstream"].code == "build.dependency"

    async def test_async_cycles_are_reported_explicitly(self):
        configs = {
            "a": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "b"}),
            "b": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "a"}),
            "downstream": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "a"}),
        }

        built, errors = await build_objects_async(configs)

        assert not built
        assert errors["a"].code == "build.circular"
        assert errors["b"].code == "build.circular"
        assert errors["downstream"].code == "build.dependency"

    async def test_async_cycles_are_excluded_from_module_prewarming(self, monkeypatch):
        configs = {
            "a": BuildConfig(target="cyclic_a.Device", init={"dependency": "b"}),
            "b": BuildConfig(target="cyclic_b.Device", init={"dependency": "a"}),
            "independent": BuildConfig(target=f"{__name__}._GoodDevice", init={}),
        }
        prewarmed: set[str] = set()

        def record_prewarmed(cfgs):
            prewarmed.update(cfgs)

        monkeypatch.setattr(build_module, "_prewarm_parent_modules", record_prewarmed)

        built, errors = await build_objects_async(configs)

        assert set(built) == {"independent"}
        assert errors["a"].code == "build.circular"
        assert errors["b"].code == "build.circular"
        assert prewarmed == {"independent"}

    async def test_unexpected_group_error_marks_devices_and_dependents(
        self,
        monkeypatch,
    ):
        configs = {
            "root": BuildConfig(target=f"{__name__}._GoodDevice", init={}),
            "dependent": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "root"}),
        }
        original = build_module._build_group_sync

        def fail_root_group(group, cfgs, built, base_cls):
            if "root" in group:
                raise RuntimeError("worker failed")
            return original(group, cfgs, built, base_cls)

        monkeypatch.setattr(build_module, "_build_group_sync", fail_root_group)

        built, errors = await build_objects_async(configs)

        assert not built
        assert errors["root"].code == "build.internal"
        assert errors["dependent"].code == "build.dependency"
