"""The SPIM microscope with the new light devices, as the real app would hold them. It runs on the lab's copy of the
HAL. A profile gives the power of each laser and modulator, and its timelines say what drives each of them."""

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from rigup.activity import ActivityInfo
from vxlib.asyncio import gather_all
from vxlib.reactivity import Cell, Readable
from vxlib.units import Quantity

from vxl.core.errors import RejectedError
from vxl.core.instrument.config import DeviceUid
from vxl.core.instrument.signals import Timeline
from vxl.core.instrument.state import ProfileId
from vxl.devices.signals.generator.base import OwnClock
from vxl.instruments.spim.instrument import Microscope, _Preview

from .config import LabProfile, LabState, PowerMode
from .hal import HAL

if TYPE_CHECKING:
    from vxl.core.instrument import hal as core_hal

logger = logging.getLogger(__name__)


class LabMicroscope(Microscope):
    """A microscope whose light comes from lasers, modulators and shutters. Applying a profile sets what drives each
    laser and modulator, and its power: the full or the dim one, as the power mode says. A preview lights the lasers
    of its channels."""

    state_cls = LabState

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._lab_hal = HAL(self._config)
        self._hal = cast("core_hal.HAL", self._lab_hal)
        self._power_mode = Cell[PowerMode]("dim")

    @property
    def power_mode(self) -> Readable[PowerMode]:
        """Whether the full or the dim powers of the active profile are in use."""
        return self._power_mode

    async def set_power(self, device: DeviceUid, value: float) -> None:
        """Set the full power of a laser or a modulator in the active profile, in the device's own unit, and save it.
        When the profile has 1 power for each position of a device, set the one for the position it is at now."""
        await self._edit_power("full", device, value)

    async def set_dim_power(self, device: DeviceUid, value: float) -> None:
        """Set the dim power of a laser or a modulator in the active profile, as :meth:`set_power` does."""
        await self._edit_power("dim", device, value)

    async def set_power_mode(self, mode: PowerMode) -> None:
        """Use the full or the dim powers. A running preview changes at once."""
        async with self._scheduler.run("set the power mode", requires=()):
            await self._apply_powers(self._profile(self._active_profile.value), mode)
            await self._power_mode.set(mode)

    async def lights_off(self) -> None:
        """Make every light dark: no light reaches the sample, and a laser whose light something after it stops stays
        on. A running preview goes dark and keeps running."""
        async with self._scheduler.run("turn the lights off", requires=()):
            await self._lab_hal.lights_off()

    async def lasers_off(self) -> None:
        """Turn off every laser and modulator, and close every shutter. A running preview goes dark and keeps
        running."""
        async with self._scheduler.run("turn the lasers off", requires=()):
            await self._lab_hal.lasers_off()

    async def set_generator_timeline(self, generator: DeviceUid, timeline: Timeline) -> None:
        requires = {generator, self._store, self._active_profile}
        async with self._scheduler.run("set a generator timeline", requires=requires):
            await super().set_generator_timeline(generator, timeline)
            await self._apply_light(self._profile(self._active_profile.value))

    def _profile(self, profile_id: ProfileId) -> LabProfile:
        return cast("LabProfile", self._store.value.profiles[profile_id])

    async def _edit_power(self, mode: PowerMode, device: DeviceUid, value: float) -> None:
        async with self._scheduler.run("set a power", requires={self._store}):
            hal = self._lab_hal
            ranges = await hal.light_power_ranges()
            if device not in ranges:
                raise RejectedError(f"'{device}' is not a laser or a modulator")
            active = self._active_profile.value
            before = self._profile(active).power
            where = await hal.router_positions() if before.router(device) is not None else {}
            try:
                after = before.with_power(mode, device, Quantity.of(value, ranges[device][0].unit), where)
            except ValueError as error:
                raise RejectedError(str(error)) from error
            if problems := after.device_problems(ranges).under("profiles", active, "power"):
                raise RejectedError(str(problems), problems)
            await self._store.update({("profiles", active, "power"): after.model_dump(mode="json")})
            in_use = self._power_mode.value
            now = after.at(in_use, where).get(device)
            if now is not None and now != before.at(in_use, where).get(device):
                await hal.set_light_powers({device: now.number})

    async def _apply_profile(self, profile_id: ProfileId) -> None:
        """Set the devices to a saved profile, in order: every light off, device positions, device properties, camera
        regions, setup commands, each generator's cycle on its own clock, then what drives each laser and modulator,
        and its power. Make it the active profile when every step succeeds."""
        state = self._store.value
        profile = self._profile(profile_id)
        hal = self._lab_hal
        if problems := profile.power.device_problems(await hal.light_power_ranges()).under(
            "profiles", profile_id, "power"
        ):
            raise RejectedError(str(problems), problems)
        await hal.lights_off()
        positions = {**state.positions_at(await self.stage_position(), {}), **profile.positions}
        await gather_all(*(self._move_axis(device, position) for device, position in positions.items()), message="move")
        for device, props in profile.props.items():
            results = await hal.device(device).props.set(**props)
            if failed := sorted(name for name, result in results.results.items() if not result.is_ok):
                raise RejectedError(f"'{device}' refused the properties {failed} of profile '{profile_id}'")
        regions = (hal.cameras[camera].update_roi(channel.fov) for camera, channel in profile.channels.items())
        await gather_all(*regions, message="camera regions")
        for device, commands in profile.setup.items():
            if not (await hal.device(device).run_commands(commands)).is_ok:
                raise RejectedError(f"The setup commands of profile '{profile_id}' failed on '{device}'")
        cycles = {
            generator: self._generator_cycle(generator, timeline, OwnClock())
            for generator, timeline in profile.timelines.items()
        }
        loads = (hal.signal_generators[generator].load(cycle) for generator, cycle in cycles.items())
        await gather_all(*loads, message="timelines")
        await self._apply_light(profile)
        await self._active_profile.set(profile_id)
        await self._preview_channels.set(self._preview_choice(profile_id))

    async def _apply_light(self, profile: LabProfile) -> None:
        """Set what controls each laser and modulator, as the profile's timelines say, then their powers."""
        await self._lab_hal.set_light_control_modes(profile.live_inputs(self._config))
        await self._apply_powers(profile, self._power_mode.value)

    async def _apply_powers(self, profile: LabProfile, mode: PowerMode) -> None:
        """Set each power of the profile in a power mode, for the position each device that sends the light a
        different way is at now."""
        powers = profile.power.at(mode, await self._lab_hal.router_positions())
        await self._lab_hal.set_light_powers({device: power.number for device, power in powers.items()})

    async def _begin_preview(self) -> None:
        """Start the preview's devices, in order: the scan axis disarmed when it scans, the chosen channels' cameras,
        the light of their lasers, every generator of the profile. Then hold the active profile, those devices, and
        every device on a path that the lasers' light can take, so a change to one of them lights the sample again. A
        laser whose light has no way to the sample now stays off, and the preview runs without it. When a step fails,
        turn every light off and stop what started."""
        hal = self._lab_hal
        profile = self._profile(self._active_profile.value)
        cameras = self._preview_channels.value
        generators = tuple(profile.timelines)
        sources = dict.fromkeys(profile.channels[c].illumination for c in cameras)
        axis = hal.stage[self._config.scan.axis]
        if await axis.scan_state.get() != "idle":
            await axis.halt()
        try:
            await gather_all(*(hal.cameras[c].start_preview() for c in cameras), message="cameras")
            lit = await hal.lights_on(sources)
            await gather_all(*(hal.signal_generators[g].start() for g in generators), message="generators")
        except BaseException:
            await self._stop_preview_devices(cameras, (), generators)
            raise
        if blocked := sorted(source for source, paths in lit.items() if not paths):
            logger.warning("The preview runs without %s: its light has no way to the sample now", ", ".join(blocked))
        paths = (path for source in sources for path in self._config.optics.paths_from(source, {}))
        on_paths = {node for path in paths for node in path.nodes if node in self._config.all_devices}
        requires = {self._active_profile, *cameras, *generators, *on_paths}
        activity = await self._scheduler.start(ActivityInfo(kind="preview"), requires, restart=self._restart_preview)
        self._preview = _Preview(activity, cameras, (), generators)

    async def _stop_preview_devices(
        self, cameras: Sequence[DeviceUid], lasers: Sequence[DeviceUid], generators: Sequence[DeviceUid]
    ) -> None:
        try:
            await self._lab_hal.lights_off()
        finally:
            await super()._stop_preview_devices(cameras, lasers, generators)


__all__ = ["LabMicroscope"]
