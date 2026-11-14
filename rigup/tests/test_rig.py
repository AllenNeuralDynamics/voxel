from collections.abc import AsyncIterator, Callable

import pytest
from rigup.node import LOCAL
from rigup.rig import Rig

from rigup import DeviceConfig, RigConfig


def mock(initial_value: float = 0.0) -> DeviceConfig:
    return DeviceConfig(target="rigup_fakes.MockDevice", init={"initial_value": initial_value})


@pytest.fixture
async def open_rig() -> AsyncIterator[Callable[[RigConfig], Rig]]:
    rigs: list[Rig] = []

    def make(config: RigConfig) -> Rig:
        rig = Rig(config, name="test-rig")
        rigs.append(rig)
        return rig

    yield make
    for rig in rigs:
        await rig.close()


async def test_open_builds_every_device(open_rig: Callable[[RigConfig], Rig]) -> None:
    rig = open_rig(RigConfig.model_validate({"devices": {"dev_a": mock(1.0), "dev_b": mock(2.0)}}))

    await rig.open()

    assert set(rig.devices) == {"dev_a", "dev_b"}
    assert set(rig.nodes) == {LOCAL}


async def test_a_device_call_returns_its_result(open_rig: Callable[[RigConfig], Rig]) -> None:
    rig = open_rig(RigConfig.model_validate({"devices": {"dev": mock()}}))
    await rig.open()

    result = await rig.devices["dev"].call("set_value", v=42.0)

    assert result == 42.0


async def test_close_drops_devices_and_nodes() -> None:
    rig = Rig(RigConfig.model_validate({"devices": {"dev": mock()}}), name="test-rig")
    await rig.open()

    await rig.close()

    assert rig.devices == {}
    assert rig.nodes == {}


async def test_a_device_that_fails_to_build_is_a_build_error(open_rig: Callable[[RigConfig], Rig]) -> None:
    config = RigConfig.model_validate(
        {"devices": {"good": mock(), "bad": DeviceConfig(target="nonexistent.Module", init={})}}
    )
    rig = open_rig(config)

    await rig.open()

    assert set(rig.devices) == {"good"}
    assert set(rig.build_errors) == {"bad"}


async def test_a_part_is_passed_to_a_device_and_kept_out_of_devices(open_rig: Callable[[RigConfig], Rig]) -> None:
    config = RigConfig.model_validate(
        {
            "parts": {"glass": {"target": "rigup_fakes.MockPart", "value": 1.5}},
            "devices": {"holder": DeviceConfig(target="rigup_fakes.MockHolder", init={"held": "glass"})},
        }
    )
    rig = open_rig(config)

    await rig.open()

    assert rig.build_errors == {}
    assert set(rig.devices) == {"holder"}
    assert rig.parts == config.parts


async def test_an_empty_rig_opens_with_no_devices(open_rig: Callable[[RigConfig], Rig]) -> None:
    rig = open_rig(RigConfig())

    await rig.open()

    assert rig.devices == {}
    assert rig.nodes == {}
