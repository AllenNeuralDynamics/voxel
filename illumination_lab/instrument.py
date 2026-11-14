"""The SPIM microscope with laser heads and modulators, as the real app would hold them. It runs on the lab's copy
of the HAL, and overrides the preview, since the core preview keeps a list of lasers that it no longer needs. It holds
channel powers in memory, since the core profile has no place for them yet."""

from collections.abc import AsyncGenerator, Collection, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

from vxlib.asyncio import gather_all
from vxlib.reactivity import Cell, Readable

from vxl.core.errors import RejectedError
from vxl.core.instrument.base import Instrument
from vxl.core.instrument.config import DeviceUid
from vxl.core.instrument.gate import Activity, Hold
from vxl.core.instrument.signals import Timeline
from vxl.instruments.spim.config import ProfileId
from vxl.instruments.spim.instrument import Microscope
from vxl.instruments.spim.state import SPIMState

from .config import LabConfig
from .hal import HAL

if TYPE_CHECKING:
    from vxl.core.instrument import hal as core_hal

type PreviewLight = Literal["full", "dim"]

_EPS = 1e-9


@dataclass(frozen=True)
class _Preview:
    """A running preview: its hold in the gate, and the cameras and generators it started."""

    hold: Hold
    cameras: tuple[DeviceUid, ...]
    generators: tuple[DeviceUid, ...]


class LabMicroscope(Microscope, Instrument[LabConfig, SPIMState]):
    """A microscope whose light comes from laser heads and modulators. Each channel of a profile has a power and
    maybe a dim power; a preview shows the full or the dim power. The powers live in memory here."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._lab_hal = HAL(self._config)
        self._hal = cast("core_hal.HAL", self._lab_hal)
        self._powers: dict[tuple[ProfileId, DeviceUid], tuple[float, float | None]] = {}
        self._light_level = Cell[PreviewLight]("dim")
        self._running: _Preview | None = None

    @property
    def preview_light(self) -> Readable[PreviewLight]:
        """Whether a preview shows each channel's full or dim power."""
        return self._light_level

    def channel_powers(self) -> dict[DeviceUid, tuple[float, float | None]]:
        """Each channel of the active profile, by camera: its power and its dim power, in mW."""
        profile_id = self._active_profile.value
        channels = self._store.value.profiles[profile_id].channels
        return {camera: self._powers.get((profile_id, camera), (1.0, None)) for camera in channels}

    async def set_channel_power(self, camera: DeviceUid, power_mw: float) -> None:
        """Set a channel's power. A preview showing it changes at once."""
        await self._set_powers(camera, power_mw, self.channel_powers()[camera][1])

    async def set_channel_dim_power(self, camera: DeviceUid, power_mw: float | None) -> None:
        """Set a channel's dim power, or remove it with ``None`` so that dim shows the full power."""
        await self._set_powers(camera, self.channel_powers()[camera][0], power_mw)

    async def set_preview_light(self, level: PreviewLight) -> None:
        """Show each channel's full or dim power in a preview. A running preview changes at once."""
        async with self._gate.command("set the preview light", touches=()):
            before = self._light_level.value
            await self._light_level.set(level)
            try:
                await self._relight()
            except RejectedError:
                await self._light_level.set(before)
                raise

    async def start_preview(self) -> None:
        async with self._gate.command("start a preview", touches=()):
            if self._running is None:
                await self._begin_preview()

    async def set_preview_channels(self, channels: Collection[DeviceUid]) -> None:
        async with self._gate.command("set the preview channels", touches=()):
            profile_id = self._active_profile.value
            known = self._store.value.profiles[profile_id].channels
            if not channels:
                raise RejectedError("A preview needs at least 1 channel")
            if unknown := sorted(set(channels) - set(known)):
                raise RejectedError(f"Profile '{profile_id}' has no channel {', '.join(unknown)}")
            self._preview_choices[profile_id] = frozenset(channels)
            if self._preview_choice(profile_id) == self._preview_channels.value:
                return
            running = self._running is not None
            await self._end_preview()
            await self._preview_channels.set(self._preview_choice(profile_id))
            if running:
                await self._begin_preview()

    async def _set_powers(self, camera: DeviceUid, power_mw: float, dim_mw: float | None) -> None:
        async with self._gate.command("set a channel power", touches=()):
            profile_id = self._active_profile.value
            if camera not in self._store.value.profiles[profile_id].channels:
                raise RejectedError(f"Profile '{profile_id}' has no channel {camera}")
            before = self.channel_powers()[camera]
            self._powers[(profile_id, camera)] = (power_mw, dim_mw)
            try:
                await self._relight()
            except RejectedError:
                self._powers[(profile_id, camera)] = before
                raise

    async def _relight(self) -> None:
        """Light the preview's channels again, as their powers and the preview light now say."""
        if self._running is not None:
            await self._lab_hal.illuminate(self._preview_powers())

    def _preview_powers(self) -> dict[DeviceUid, float]:
        """The power each light source of the previewed channels gets. Raise :class:`RejectedError` when 2 channels
        share a source but ask for different powers."""
        channels = self._store.value.profiles[self._active_profile.value].channels
        powers: dict[DeviceUid, float] = {}
        for camera in self._preview_channels.value:
            full, dim = self.channel_powers()[camera]
            power = dim if self._light_level.value == "dim" and dim is not None else full
            source = channels[camera].illumination
            if abs(powers.setdefault(source, power) - power) > _EPS:
                raise RejectedError(f"{source} is asked for {powers[source]:g} and {power:g} mW by 2 channels")
        return powers

    async def _apply_profile(self, profile_id: ProfileId) -> None:
        await self._lab_hal.illuminate({})
        await super()._apply_profile(profile_id)
        await self._lab_hal.follow_wires(self._playing())

    async def set_generator_timeline(self, generator: DeviceUid, timeline: Timeline) -> None:
        touches = {generator, self._store, self._active_profile}
        async with self._gate.command("set a generator timeline", touches=touches):
            await super().set_generator_timeline(generator, timeline)
            await self._lab_hal.follow_wires(self._playing())

    def _playing(self) -> set[tuple[DeviceUid, str]]:
        """The wires the active profile's generators play: each wire with a signal in its timeline."""
        timelines = self._store.value.profiles[self._active_profile.value].timelines
        return {(generator, wire) for generator, timeline in timelines.items() for wire in timeline.signals}

    async def _begin_preview(self) -> None:
        """Disarm the scan axis, light the chosen channels, start their cameras and every generator of the profile,
        then hold the active profile and every device used. A refused light changes nothing; any other failure turns
        every light off and stops what started."""
        hal = self._hal
        profile = self._store.value.profiles[self._active_profile.value]
        cameras = self._preview_channels.value
        generators = tuple(profile.timelines)
        axis = hal.stage[self._config.scan.axis]
        if await axis.scan_state.get() != "idle":
            await axis.halt()
        try:
            used = await self._lab_hal.illuminate(self._preview_powers())
            await gather_all(*(hal.cameras[c].start_preview() for c in cameras), message="cameras")
            await gather_all(*(hal.signal_generators[g].start() for g in generators), message="generators")
        except RejectedError:
            raise
        except BaseException:
            try:
                await self._lab_hal.lights_off()
            finally:
                await super()._stop_preview_devices(cameras, (), generators)
            raise
        holds = {self._active_profile, *cameras, *generators, *used}
        hold = await self._gate.begin(Activity(kind="preview"), holds, restart=self._restart_preview)
        self._running = _Preview(hold, cameras, generators)

    async def _end_preview(self) -> None:
        if (preview := self._running) is None:
            return
        self._running = None
        try:
            await self._stop_preview_devices(preview.cameras, (), preview.generators)
        finally:
            await self._gate.end(preview.hold)

    async def _stop_preview_devices(
        self, cameras: Sequence[DeviceUid], lasers: Sequence[DeviceUid], generators: Sequence[DeviceUid]
    ) -> None:
        try:
            await self._lab_hal.illuminate({})
        finally:
            await super()._stop_preview_devices(cameras, lasers, generators)

    @asynccontextmanager
    async def _restart_preview(self) -> AsyncGenerator[None]:
        await self._end_preview()
        yield
        await self._begin_preview()


__all__ = ["LabMicroscope", "PreviewLight"]
