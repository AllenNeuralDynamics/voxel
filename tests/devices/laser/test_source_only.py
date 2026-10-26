import pytest
from rigup.device.props import PropertyModel

from rigup import DeviceConfig, Rig, RigConfig, describe, numeric
from vxl.devices.laser.source import LaserSource, ModulationMode
from vxl.devices.laser.source_only import SourceOnlyLaser


class RecordingSource(LaserSource):
    def __init__(self, uid="source"):
        super().__init__(uid)
        self.enabled = True
        self.power = 300.0
        self.mode = ModulationMode.SOFTWARE
        self.events = []
        self.fail_enable = False
        self.fail_disable = False

    @property
    def wavelength(self) -> float:
        return 561.0

    def source_enable(self, *, wait=False):
        self.events.append(("enable", wait))
        self.enabled = True
        if self.fail_enable:
            raise TimeoutError("startup timed out")

    def source_disable(self):
        self.events.append(("disable",))
        if self.fail_disable:
            raise RuntimeError("inhibition failed")
        self.enabled = False

    @property
    def is_source_enabled(self):
        return self.enabled

    @property
    @describe(label="Head Type")
    def head_type(self) -> str:
        return "test head"

    @numeric(minimum=200.0, maximum=1000.0, step=0.5)
    def source_power_setpoint_mw(self) -> float:
        return self.power

    @source_power_setpoint_mw.setter
    def source_power_setpoint_mw(self, value: float) -> None:
        self.power = value

    def _get_modulation_modes(self):
        return tuple(ModulationMode)

    def _read_modulation_mode(self):
        return self.mode

    def _configure_modulation_mode(self, mode):
        assert not self.enabled
        self.events.append(("mode", mode))
        self.mode = mode

    def close(self):
        self.source_disable()
        self.events.append(("close",))


def test_scaled_output_defers_startup_and_preserves_operating_settings():
    source = RecordingSource()
    laser = SourceOnlyLaser("laser", source)
    assert not source.enabled
    laser.source_enable(wait=True)
    assert laser.is_source_enabled
    assert source.events == [("disable",)]
    laser.source_power_setpoint_mw = 400
    laser.output_level_percent = 50
    assert source.power == 200
    assert laser.source_power_setpoint_mw == 400
    level_model = PropertyModel.from_value(laser.output_level_percent)
    assert level_model.minimum == 50
    assert level_model.maximum == 100
    assert level_model.step == 0.125
    laser.output_enable(wait=True)
    assert source.events[-1] == ("enable", True)
    laser.source_power_setpoint_mw = 800
    assert source.power == 400
    assert laser.output_level_percent == 50
    assert PropertyModel.from_value(laser.output_level_percent).minimum == 25
    with pytest.raises(ValueError, match="output level"):
        laser.output_level_percent = 0
    with pytest.raises(ValueError, match="output level"):
        laser.source_power_setpoint_mw = 300
    assert laser.source_power_setpoint_mw == 800
    assert source.power == 400
    laser.output_disable()
    assert laser.is_source_enabled
    assert not laser.is_output_enabled
    assert not source.enabled
    assert laser.output_level_percent == 50


def test_native_modulation_and_saved_operating_level():
    source = RecordingSource()
    laser = SourceOnlyLaser("laser", source)
    laser.source_power_setpoint_mw = 800
    laser.source_enable()
    laser.set_modulation_mode("digital")  # Logical source permission does not prevent reconfiguration.
    laser.output_level_percent = 50
    laser.output_enable(wait=True)
    assert source.power == 400
    with pytest.raises(RuntimeError, match="Disable output"):
        laser.set_modulation_mode("analog")

    laser.output_disable()
    laser.set_modulation_mode("analog")
    laser.output_enable(wait=True)
    assert source.power == 800  # Analog uses the reference, not the saved software level.
    events = list(source.events)
    laser.output_level_percent = 25
    assert source.events == events
    assert source.power == 800
    laser.output_disable()
    laser.set_modulation_mode("software")
    laser.output_enable()
    assert source.power == 200  # Returning to software restores the saved fraction.


def test_enable_failure_inhibits_source_and_disable_failure_does_not_claim_success():
    source = RecordingSource()
    laser = SourceOnlyLaser("laser", source)
    laser.source_enable()
    source.fail_enable = True
    with pytest.raises(TimeoutError, match="startup"):
        laser.output_enable(wait=True)
    assert not source.enabled
    assert not laser.is_output_enabled
    assert laser.is_source_enabled
    source.fail_enable = False
    laser.output_enable()
    source.fail_disable = True
    with pytest.raises(RuntimeError, match="inhibition"):
        laser.source_disable()
    assert laser.is_output_enabled
    assert laser.is_source_enabled
    source.fail_disable = False
    laser.source_disable()
    assert not source.enabled


def test_enable_and_rollback_failures_are_both_reported():
    source = RecordingSource()
    laser = SourceOnlyLaser("laser", source)
    laser.source_enable()
    source.fail_enable = source.fail_disable = True
    with pytest.raises(ExceptionGroup) as caught:
        laser.output_enable()
    assert [type(error) for error in caught.value.exceptions] == [TimeoutError, RuntimeError]
    assert not laser.is_output_enabled  # Permission revoked; hardware inhibition is unconfirmed.


def test_close_retries_failed_inhibition_and_leaves_source_with_owner():
    source = RecordingSource()
    laser = SourceOnlyLaser("laser", source)
    laser.source_enable()
    laser.output_enable()
    source.fail_disable = True
    with pytest.raises(RuntimeError, match="inhibition"):
        laser.close()
    assert laser.is_output_enabled
    assert ("close",) not in source.events

    source.fail_disable = False
    laser.close()
    assert not source.enabled
    assert not laser.is_output_enabled
    assert ("close",) not in source.events
    with pytest.raises(RuntimeError, match="closed"):
        laser.source_enable()
    source.source_power_setpoint_mw = 500
    assert source.power == 500  # The source remains usable by its owner.


async def test_rig_registers_source_and_adapter_with_separate_discovery():
    rig = Rig(
        RigConfig(
            devices={
                "source": DeviceConfig(target=f"{__name__}.RecordingSource"),
                "laser": DeviceConfig(
                    target="vxl.devices.laser.source_only.SourceOnlyLaser", init={"source": "source"}
                ),
            }
        )
    )
    await rig.open()
    try:
        assert not rig.build_errors
        assert set(rig.devices) == {"source", "laser"}
        source = rig.devices["source"]
        laser = rig.devices["laser"]
        source_interface = await source.interface()
        laser_interface = await laser.interface()
        assert "head_type" in source_interface.properties
        assert "head_type" not in laser_interface.properties
        assert source_interface.properties["modulation_mode"].access == "ro"
        assert laser_interface.properties["modulation_mode"].access == "ro"
        (await laser.run_command("set_modulation_mode", "digital")).unwrap()
        mode = (await laser.props.get("modulation_mode"))["modulation_mode"].unwrap()
        assert mode.value == "digital"
        assert mode.options == [mode.value for mode in ModulationMode]
        await rig.nodes["local"].close_device("laser")
        assert set(rig.devices) == {"source"}
        assert (await source.props.get("head_type"))["head_type"].unwrap().value == "test head"
    finally:
        await rig.close()
