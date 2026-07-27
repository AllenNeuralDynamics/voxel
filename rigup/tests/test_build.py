"""Tests for rigup.build — defaults failure semantics and async build."""

import rigup.build as build_module
from rigup.build import BuildConfig, build_objects, build_objects_async


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
        assert errors["dev"].error_type == "defaults"

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
        assert errors["bad"].error_type == "import"

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
        assert errors["dev"].error_type == "defaults"


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
        assert errors["root"].error_type == "import"
        assert errors["middle"].error_type == "dependency"
        assert errors["leaf"].error_type == "dependency"
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
        assert errors["dependent"].error_type == "dependency"

    def test_sync_cycles_are_reported_explicitly(self):
        configs = {
            "a": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "b"}),
            "b": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "a"}),
            "downstream": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "a"}),
        }

        built, errors = build_objects(configs)

        assert not built
        assert errors["a"].error_type == "circular"
        assert errors["b"].error_type == "circular"
        assert errors["downstream"].error_type == "dependency"

    async def test_async_cycles_are_reported_explicitly(self):
        configs = {
            "a": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "b"}),
            "b": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "a"}),
            "downstream": BuildConfig(target=f"{__name__}._DependentDevice", init={"dependency": "a"}),
        }

        built, errors = await build_objects_async(configs)

        assert not built
        assert errors["a"].error_type == "circular"
        assert errors["b"].error_type == "circular"
        assert errors["downstream"].error_type == "dependency"

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
        assert errors["a"].error_type == "circular"
        assert errors["b"].error_type == "circular"
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
        assert errors["root"].error_type == "internal"
        assert errors["dependent"].error_type == "dependency"
