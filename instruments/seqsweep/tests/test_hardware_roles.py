import asyncio

import pytest
from vxl.hal.errors import HALStartupError

from seqsweep.devices.acs.handle import ScanControllerHandle
from seqsweep.devices.acs.simulated_acs import SimulatedAcsController
from seqsweep.hal import HAL, SeqSweepHardwareTopology
from seqsweep.seqsweep import SeqSweep
from seqsweep.seqsweep_config_model import SeqSweepInstrumentConfig

ACS_TARGET = "seqsweep.devices.acs.simulated_acs.SimulatedAcsController"
ACS_INIT = {"gate_outputs": {"laser_532": "OUT0"}}


def _topology(scan_controller: str = "acs") -> SeqSweepHardwareTopology:
    return SeqSweepHardwareTopology(
        devices={"acs": {"target": ACS_TARGET, "init": ACS_INIT}},
        scan_controller=scan_controller,
    )


def _config(topology: SeqSweepHardwareTopology) -> SeqSweepInstrumentConfig:
    return SeqSweepInstrumentConfig(
        hal=topology,
        default={"scan": {"start_um": 0, "end_um": 10, "velocity_um_s": 10, "line_pitch_um": 1}},
    )


def test_unknown_role_device_is_rejected_at_load():
    with pytest.raises(ValueError, match="scan_controller 'missing' is not a device in the rig"):
        _topology(scan_controller="missing")


def test_hal_open_classifies_the_scan_controller():
    async def run() -> None:
        hal = HAL(_topology())
        await hal.open()
        try:
            assert list(hal.scan_controllers) == ["acs"]
            assert isinstance(hal.scan_controller, ScanControllerHandle)
            assert hal.scan_controller is hal.scan_controllers["acs"]
            assert await hal.scan_controller.is_running.get() is False
            await hal.scan_controller.abort()
        finally:
            await hal.close()

    asyncio.run(run())


def test_hal_scan_controller_requires_open():
    with pytest.raises(RuntimeError, match="not open"):
        _ = HAL(_topology()).scan_controller


def test_hal_open_fails_when_role_points_at_wrong_type(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(SimulatedAcsController, "__DEVICE_TYPE__", "camera")
    with pytest.raises(HALStartupError, match="hal.scan_controller.not_scan_controller") as exc_info:
        asyncio.run(HAL(_topology()).open())
    (violation,) = exc_info.value.violations
    assert violation.loc == ("hal", "scan_controller")


def test_hal_open_skips_role_check_for_unavailable_device():
    hal = HAL(_topology())
    assert hal._compatibility_violations({"acs"}) == []  # noqa: SLF001


def test_seqsweep_open_succeeds_with_simulated_acs():
    with SeqSweep(_config(_topology())) as seqsweep:
        assert seqsweep.check_job_status() == {"status": "idle"}


def test_seqsweep_open_fails_when_role_points_at_wrong_type(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(SimulatedAcsController, "__DEVICE_TYPE__", "camera")
    with pytest.raises(HALStartupError, match="hal.scan_controller.not_scan_controller"):
        SeqSweep(_config(_topology())).open()
