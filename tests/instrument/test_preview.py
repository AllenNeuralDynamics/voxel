from types import SimpleNamespace

import numpy as np
import pytest

from vxl.instrument import AcquisitionMode, Instrument
from vxl.preview import PreviewFrame, PreviewLayer, PreviewSourceEmission, PreviewViewport
from vxl.preview.protocol import StagePosition


@pytest.fixture
def preview_operations(opened_instrument: Instrument, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Keep real laser commands; record camera/DAQ boundaries without starting frame workers."""
    events = []

    def record(label):
        async def run():
            events.append(label)

        return run

    def record_laser(laser):
        original = laser.call

        async def call(command, *args, **kwargs):
            events.append(f"{laser.uid}.{command}")
            if command in {"source_enable", "output_enable"}:
                assert kwargs["wait"] is True
            return await original(command, *args, **kwargs)

        monkeypatch.setattr(laser, "call", call)

    for laser in opened_instrument._hal.lasers.values():
        record_laser(laser)
    camera = opened_instrument._hal.cameras["camera_1"]
    daq = opened_instrument._hal.signal_generators["daq"]
    for handle, name, label in (
        (camera, "start_preview", "camera.start"),
        (camera, "stop_preview", "camera.stop"),
        (daq, "start", "daq.start"),
        (daq, "stop", "daq.stop"),
    ):
        monkeypatch.setattr(handle, name, record(label))
    return events


async def test_preview_orders_output_and_preserves_selection_on_reconfiguration(
    opened_instrument: Instrument, preview_operations: list[str]
) -> None:
    instrument, events = opened_instrument, preview_operations
    laser = instrument._hal.lasers["laser_488"]
    assert (await laser.props.get("is_source_enabled")).ok["is_source_enabled"].value
    await instrument.select_route("excitation_side", "left")
    await instrument.start_preview(["gfp"])
    assert events.index("laser_488.set_modulation_mode") < events.index("camera.start")
    assert events.index("camera.start") < events.index("laser_488.output_enable") < events.index("daq.start")
    assert (await laser.props.get("modulation_mode")).ok["modulation_mode"].value == "digital"

    events.clear()
    await instrument.select_route("excitation_side", "right")
    assert events.index("laser_488.output_disable") < events.index("daq.stop") < events.index("camera.stop")
    assert events.index("camera.stop") < events.index("camera.start")
    assert [ch.uid for ch in instrument._preview_channels] == ["gfp"]
    await instrument.apply_settings()
    assert [ch.uid for ch in instrument._preview_channels] == ["gfp"]
    await instrument.set_active_profile("single_rfp")
    assert [ch.uid for ch in instrument._preview_channels] == ["rfp"]
    await instrument.stop_preview()
    for laser in instrument._hal.lasers.values():
        props = (await laser.props.get("is_source_enabled", "is_output_enabled")).ok
        assert props["is_source_enabled"].value
        assert not props["is_output_enabled"].value
    await instrument.close()
    assert "laser_488.source_disable" in events
    assert "laser_561.source_disable" in events


@pytest.mark.parametrize("transition", ["profile", "route"])
async def test_failed_reconfiguration_leaves_preview_stopped(
    opened_instrument: Instrument, preview_operations: list[str], monkeypatch: pytest.MonkeyPatch, transition: str
) -> None:
    instrument, events = opened_instrument, preview_operations
    await instrument.select_route("excitation_side", "left")
    await instrument.start_preview()
    events.clear()

    async def fail(*_args):
        raise RuntimeError("configuration failed")

    if transition == "profile":
        monkeypatch.setattr(instrument, "_apply_settings", fail)
        with pytest.raises(RuntimeError, match="configuration failed"):
            await instrument.set_active_profile("single_rfp")
    else:
        monkeypatch.setattr(type(instrument._hal.routing["excitation_side"]), "select", fail)
        with pytest.raises(ExceptionGroup):
            await instrument.select_route("excitation_side", "right")
    assert instrument.mode.value is AcquisitionMode.IDLE
    assert "camera.stop" in events
    assert "camera.start" not in events
    for laser in instrument._hal.lasers.values():
        assert not (await laser.props.get("is_output_enabled")).ok["is_output_enabled"].value


async def test_failed_daq_start_inhibits_output_and_stops_camera(
    opened_instrument: Instrument, preview_operations: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    instrument, events = opened_instrument, preview_operations
    await instrument.select_route("excitation_side", "left")

    async def fail():
        events.append("daq.fail")
        raise RuntimeError("DAQ failed")

    monkeypatch.setattr(instrument._hal.signal_generators["daq"], "start", fail)
    with pytest.raises(ExceptionGroup):
        await instrument.start_preview()
    assert events[-3:] == ["laser_488.output_disable", "daq.stop", "camera.stop"]
    assert instrument.mode.value is AcquisitionMode.IDLE
    assert not instrument._preview_channels


async def test_output_inhibition_failure_does_not_skip_daq_and_camera_stop(
    opened_instrument: Instrument, preview_operations: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    instrument, events = opened_instrument, preview_operations
    await instrument.select_route("excitation_side", "left")
    await instrument.start_preview()
    laser = instrument._hal.lasers["laser_488"]
    original = laser.call

    async def fail(command, *args, **kwargs):
        if command == "output_disable":
            raise RuntimeError("inhibition failed")
        return await original(command, *args, **kwargs)

    monkeypatch.setattr(laser, "call", fail)
    with pytest.raises(ExceptionGroup):
        await instrument.stop_preview()
    assert events[-2:] == ["daq.stop", "camera.stop"]
    assert instrument.mode.value is AcquisitionMode.IDLE


async def test_preview_rejects_stale_source_generation(opened_instrument: Instrument) -> None:
    instrument = opened_instrument
    source_frames: list[PreviewSourceEmission] = []
    unsub = instrument.preview.subscribe(source_frames.append)
    try:
        source_packet = PreviewFrame.from_source(
            np.zeros((8, 8), dtype=np.uint16),
            camera_id="camera_1",
            source_stream_id=instrument._preview_source_ids["camera_1"],
            layer=PreviewLayer.OVERVIEW,
            frame_idx=0,
            viewport=PreviewViewport(),
            target_width=8,
            valid_bits=16,
        ).pack()
        await instrument._emit_preview_frame("camera_1", PreviewLayer.OVERVIEW, source_packet)
        assert source_frames[-1] == ("gfp", PreviewLayer.OVERVIEW, source_packet, None)

        preview_revision = instrument.preview_revision.value
        await instrument.set_active_profile("single_rfp")
        assert instrument.preview_revision.value == preview_revision + 1
        await instrument._emit_preview_frame("camera_1", PreviewLayer.OVERVIEW, source_packet)
        assert len(source_frames) == 1
        source_packet = PreviewFrame.from_source(
            np.zeros((8, 8), dtype=np.uint16),
            camera_id="camera_1",
            source_stream_id=instrument._preview_source_ids["camera_1"],
            layer=PreviewLayer.OVERVIEW,
            frame_idx=0,
            viewport=PreviewViewport(),
            target_width=8,
            valid_bits=16,
        ).pack()
        await instrument._emit_preview_frame("camera_1", PreviewLayer.OVERVIEW, source_packet)
        assert source_frames[-1] == ("rfp", PreviewLayer.OVERVIEW, source_packet, None)
    finally:
        unsub()


async def test_preview_position_survives_stop_but_not_stream_reset(
    opened_instrument: Instrument, monkeypatch: pytest.MonkeyPatch
) -> None:
    instrument = opened_instrument
    stage = instrument._hal.stage
    samples = [SimpleNamespace(value=value) for value in (10.0, 20.0, 30.0)]
    for axis, sample in zip((stage.x, stage.y, stage.z), samples, strict=True):
        monkeypatch.setattr(axis, "position", sample)
    delivered: list[PreviewSourceEmission] = []
    unsub = instrument.preview.subscribe(delivered.append)

    async def emit(frame_idx: int, layer: PreviewLayer = PreviewLayer.VIEWPORT) -> None:
        packet = PreviewFrame.from_source(
            np.zeros((8, 8), dtype=np.uint16),
            camera_id="camera_1",
            source_stream_id=instrument._preview_source_ids["camera_1"],
            layer=layer,
            frame_idx=frame_idx,
            viewport=PreviewViewport(),
            target_width=8,
            valid_bits=16,
        ).pack()
        await instrument._emit_preview_frame("camera_1", layer, packet)

    try:
        await instrument._mode.set(AcquisitionMode.PREVIEW)
        instrument._preview_channels = list(instrument.active_channels.values())
        await emit(3, PreviewLayer.OVERVIEW)
        assert delivered[-1][3] == StagePosition(x=10, y=20, z=30)
        await instrument.stop_preview()
        samples[0].value = 99.0
        await emit(3)
        assert delivered[-1][3] == StagePosition(x=10, y=20, z=30)
        await emit(4)
        assert delivered[-1][3] is None  # An unseen cached frame must not acquire a post-stop position.

        await instrument._mode.set(AcquisitionMode.PREVIEW)
        for frame_idx in range(5, 22):
            await emit(frame_idx)
        assert len(instrument._preview_positions["camera_1"]) == 16
        await emit(3)
        assert delivered[-1][3] is None  # Evicted captures must not be re-anchored either.

        await instrument._reset_preview()
        assert not instrument._preview_positions
        await emit(3)
        assert delivered[-1][3] == StagePosition(x=99, y=20, z=30)
        samples[1].value = None
        await emit(4)
        assert delivered[-1][3] is None
        await instrument.close()
        assert not instrument._preview_positions
    finally:
        unsub()
