"""Tests for rigur.build — defaults failure semantics and async build."""

from rigur.build import BuildConfig, build_objects, build_objects_async


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


class TestDefaultsFailure:
    def test_successful_defaults(self):
        configs = {
            "dev": BuildConfig(
                target=f"{__name__}._GoodDevice",
                init={},
                defaults={"value": 42},
            ),
        }
        built, errors = build_objects(configs)
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
        built, errors = build_objects(configs)
        assert "dev" not in built
        assert "dev" in errors
        assert errors["dev"].error_type == "defaults"

    def test_no_defaults_is_fine(self):
        configs = {
            "dev": BuildConfig(target=f"{__name__}._GoodDevice", init={}),
        }
        built, errors = build_objects(configs)
        assert "dev" in built
        assert not errors


class TestAsyncBuild:
    async def test_async_build_creates_objects(self):
        configs = {
            "a": BuildConfig(target=f"{__name__}._GoodDevice", init={"value": 1}),
            "b": BuildConfig(target=f"{__name__}._GoodDevice", init={"value": 2}),
        }
        built, errors = await build_objects_async(configs)
        assert len(built) == 2
        assert not errors
        assert built["a"].value == 1
        assert built["b"].value == 2

    async def test_async_build_with_bad_target(self):
        configs = {
            "bad": BuildConfig(target="nonexistent.Module", init={}),
        }
        built, errors = await build_objects_async(configs)
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
        built, errors = await build_objects_async(configs)
        assert "dev" not in built
        assert errors["dev"].error_type == "defaults"
