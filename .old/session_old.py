"""Session runtime — manages rig interaction, stacks, metadata, and acquisition."""

import datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vxl.rig_old import RigMode, VoxelRig

from vxl.camera.base import SensorROI
from vxl.config import OutputConfig, SessionConfig, SessionInfo
from vxl.daq import FrameTiming
from vxl.daq.wave import validate_waveform
from vxl.metadata import resolve_metadata_class
from vxl.stack import Stack, StackOrder, StackResult, StackStatus
from vxl.store import SessionStore

if TYPE_CHECKING:
    from vxl.config import GridConfig


class Session:
    """Manages a Voxel acquisition session.

    Owns the runtime state: rig interaction, stack management, metadata,
    and acquisition execution. Persistence is delegated to the injected store.
    """

    _AUTOSAVE_INTERVAL = 0.5  # seconds between autosave ticks

    def __init__(self, config: SessionConfig, store: SessionStore, rig: VoxelRig) -> None:
        self._config = config
        self._store = store
        self._rig = rig
        self._log = logging.getLogger(f"Session({config.info.uid})")

        # FOV from rig topic (set during rig.start(), updated via subscription)
        self._fov_size: tuple[float, float] | None = rig.get_topic_value("fov")
        self._unsubscribe_fov = rig.subscribe("fov", self._on_fov_changed)

    async def start(self) -> None:
        """Begin autosaving the config through the store."""
        await self._store.start_autosave(self._AUTOSAVE_INTERVAL)

    # ==================== Properties ====================

    @property
    def config(self) -> SessionConfig:
        return self._config

    @property
    def rig(self) -> VoxelRig:
        return self._rig

    @property
    def info(self) -> SessionInfo:
        return self._config.info

    @property
    def acq(self) -> OutputConfig:
        return self._config.output

    @property
    def store_path(self) -> Path:
        """Resolved base path for acquired zarrs.

        Prefers ``info.data_path`` (session-level chosen at creation) over
        ``plan.store_path`` (user-editable default).
        """
        data_path = self._config.info.data_path
        return Path(data_path) if data_path else self._config.output.store_path

    @property
    def stacks(self) -> dict[str, Stack]:
        return self._config.stacks

    @property
    def grid(self) -> "GridConfig":
        return self._config.grid

    @property
    def stack_order(self) -> StackOrder:
        return self._config.plan.stack_order

    def compute_stack_order(self) -> list[str]:
        """Compute optimal traversal order for all stacks.

        Returns stack_ids ordered: completed/failed (chronological) -> planned (spatial) -> skipped.
        """
        all_stacks = self._config.stacks.values()
        plan = self._config.plan

        completed = sorted(
            [s for s in all_stacks if s.status in (StackStatus.COMPLETED, StackStatus.FAILED)],
            key=lambda s: s.completed_at or datetime.datetime.min.replace(tzinfo=datetime.UTC),
        )

        planned = [s for s in all_stacks if s.status in (StackStatus.PLANNED, StackStatus.ACQUIRING)]
        if plan.sort_by_profile:
            ordered_planned: list[Stack] = []
            by_profile: dict[str, list[Stack]] = {}
            for s in planned:
                by_profile.setdefault(s.profile_id, []).append(s)
            for pid in plan.profile_order:
                if pid in by_profile:
                    ordered_planned.extend(plan.stack_order(by_profile.pop(pid)))
            for remaining in by_profile.values():
                ordered_planned.extend(plan.stack_order(remaining))
            planned = ordered_planned
        else:
            planned = plan.stack_order(planned)

        skipped = sorted(
            [s for s in all_stacks if s.status == StackStatus.SKIPPED],
            key=lambda s: s.skipped_at or datetime.datetime.min.replace(tzinfo=datetime.UTC),
        )

        return [s.stack_id for s in completed + planned + skipped]

    # ==================== Metadata ====================

    @property
    def metadata(self) -> dict[str, Any]:
        return self._config.metadata

    @property
    def metadata_schema(self) -> str:
        return self._config.metadata_schema

    @property
    def has_acquired(self) -> bool:
        return any(s.status in (StackStatus.COMPLETED, StackStatus.FAILED) for s in self._config.stacks.values())

    def set_metadata_target(self, target: str) -> None:
        """Change the metadata schema class and reset metadata to defaults."""
        if self.has_acquired:
            raise ValueError("Cannot change metadata schema after acquisition has started")
        cls = resolve_metadata_class(target)
        instance = cls()
        self._config.metadata_schema = target
        self._config.metadata = instance.model_dump()

    def update_metadata(self, values: dict[str, Any]) -> None:
        """Update experiment metadata, respecting provenance locking."""
        cls = resolve_metadata_class(self._config.metadata_schema)

        if self.has_acquired:
            annotation_fields = cls.annotation_fields()
            for key in values:
                if key not in annotation_fields:
                    raise ValueError(f"Cannot modify provenance field '{key}' after acquisition has started")

        merged = {**self._config.metadata, **values}
        cls(**merged)
        self._config.metadata = merged

    # ==================== Device Props (Save to Profile) ====================

    async def save_device_props(self, device_id: str) -> None:
        """Capture and persist current device properties to the active profile."""
        if not self._rig.active_profile_id:
            raise RuntimeError("No active profile")
        profile_id = self._rig.active_profile_id
        captured = await self._rig.capture_device_props(device_id)
        self._config.rig.profiles[profile_id].props[device_id] = captured

    async def save_all_device_props(self) -> list[str]:
        """Capture and persist properties for all settable devices in the active profile."""
        if not self._rig.active_profile_id:
            raise RuntimeError("No active profile")
        profile_id = self._rig.active_profile_id
        profile_devices = self._rig.config.get_profile_device_ids(profile_id)
        settable = profile_devices - self._rig.config.filter_wheels
        saved: list[str] = []
        for device_id in sorted(settable):
            if device_id not in self._rig.handles:
                continue
            await self.save_device_props(device_id)
            saved.append(device_id)
        return saved

    # ==================== Camera ROI (Save to Profile) ====================

    async def save_camera_roi(self, camera_id: str) -> SensorROI:
        """Capture current camera ROI and persist to the active profile."""
        if not self._rig.active_profile_id:
            raise RuntimeError("No active profile")
        roi = await self._rig.capture_camera_roi(camera_id)
        self._config.rig.profiles[self._rig.active_profile_id].rois[camera_id] = roi
        return roi

    # ==================== Profile Settings ====================

    async def update_profile_waveforms(self, waveforms: dict | None = None, timing: dict | None = None) -> None:
        """Update waveform definitions for the active profile and recreate DAQ tasks."""
        profile_id = self._rig.active_profile_id
        if not profile_id:
            raise RuntimeError("No active profile")
        profile = self._config.rig.profiles[profile_id]
        if waveforms is not None:
            for device_id, wf_data in waveforms.items():
                profile.daq.waveforms[device_id] = validate_waveform(wf_data)
        if timing is not None:
            profile.daq.timing = FrameTiming.model_validate(timing)

        if self._rig.daq is not None:
            ao_range = await self._rig.daq.get_ao_voltage_range()
            for device_id, wf in profile.daq.waveforms.items():
                if wf.voltage.min < ao_range.min or wf.voltage.max > ao_range.max:
                    raise ValueError(
                        f"Waveform '{device_id}' voltage [{wf.voltage.min}, {wf.voltage.max}]V "
                        f"exceeds DAQ range [{ao_range.min}, {ao_range.max}]V"
                    )

        await self._rig.update_active_waveforms()

    async def apply_profile_props(self, device_ids: list[str] | None = None) -> list[str]:
        """Apply saved profile properties to hardware devices."""
        profile_id = self._rig.active_profile_id
        if not profile_id:
            raise RuntimeError("No active profile")
        profile = self._config.rig.profiles[profile_id]
        targets = device_ids if device_ids is not None else list(profile.props.keys())
        applied: list[str] = []
        for device_id in targets:
            props = profile.props.get(device_id)
            if not props:
                continue
            try:
                await self._rig.apply_device_props(device_id, props)
                applied.append(device_id)
            except Exception:
                self._log.exception(f"Failed to apply props for '{device_id}'")
        return applied

    async def revert_camera_roi(self, camera_id: str) -> SensorROI | None:
        """Apply saved profile ROI back to camera hardware."""
        if not self._rig.active_profile_id:
            raise RuntimeError("No active profile")
        roi = self._config.rig.profiles[self._rig.active_profile_id].rois.get(camera_id)
        if not roi:
            return None
        return await self._rig.apply_camera_roi(camera_id, roi)

    # ==================== FOV & Grid ====================

    def get_fov_size(self) -> tuple[float, float]:
        if self._fov_size is None:
            raise ValueError("FOV not available (no active profile or cameras)")
        return self._fov_size

    async def _on_fov_changed(self, fov: tuple[float, float]) -> None:
        self._fov_size = fov
        active_pid = self._rig.active_profile_id
        fov_w, fov_h = fov
        for stack in self._config.stacks.values():
            if stack.status == StackStatus.PLANNED and stack.profile_id == active_pid:
                stack.w = fov_w
                stack.h = fov_h

    def set_default_z_range(self, default_z_start: float, default_z_end: float) -> None:
        self._config.plan.default_z_start = default_z_start
        self._config.plan.default_z_end = default_z_end

    def update_grid(
        self,
        x_offset: float | None = None,
        y_offset: float | None = None,
        overlap_x: float | None = None,
        overlap_y: float | None = None,
    ) -> None:
        gc = self._config.grid
        if x_offset is not None:
            gc.x_offset = x_offset
        if y_offset is not None:
            gc.y_offset = y_offset
        if overlap_x is not None:
            if not 0.0 <= overlap_x < 1.0:
                raise ValueError(f"Overlap X must be in [0.0, 1.0), got {overlap_x}")
            gc.overlap_x = overlap_x
        if overlap_y is not None:
            if not 0.0 <= overlap_y < 1.0:
                raise ValueError(f"Overlap Y must be in [0.0, 1.0), got {overlap_y}")
            gc.overlap_y = overlap_y

    # ==================== Stack Management ====================

    def clear_profile_stacks(self, profile_id: str) -> None:
        self._config.stacks = {sid: s for sid, s in self._config.stacks.items() if s.profile_id != profile_id}
        if profile_id in self._config.plan.profile_order:
            self._config.plan.profile_order.remove(profile_id)

    def _has_stack_near(self, x: float, y: float, profile_id: str, tolerance: float = 0.1) -> bool:
        return any(
            s.profile_id == profile_id and abs(s.x - x) < tolerance and abs(s.y - y) < tolerance
            for s in self._config.stacks.values()
        )

    def add_stacks(self, stacks: list[dict[str, float]]) -> list[Stack]:
        """Add multiple stacks at specified positions. Single save at end."""
        if not stacks:
            return []

        active_pid = self._rig.active_profile_id
        if active_pid is None:
            raise RuntimeError("No active profile - select a profile before adding stacks")

        if active_pid not in self._config.plan.profile_order:
            self._config.plan.profile_order.append(active_pid)

        fov_w, fov_h = self.get_fov_size()

        added: list[Stack] = []
        for s in stacks:
            sx, sy = float(s["x"]), float(s["y"])
            z_start, z_end = float(s["z_start"]), float(s["z_end"])

            if self._has_stack_near(sx, sy, active_pid):
                raise ValueError(f"Stack already exists near ({sx:.1f}, {sy:.1f}) for profile '{active_pid}'")

            stack = Stack(
                x=sx,
                y=sy,
                w=fov_w,
                h=fov_h,
                z_start=z_start,
                z_end=z_end,
                z_step=self._config.plan.z_step,
                profile_id=active_pid,
                status=StackStatus.PLANNED,
            )
            self._config.stacks[stack.stack_id] = stack
            added.append(stack)

        return added

    def edit_stacks(self, edits: list[dict[str, str | float]]) -> list[Stack]:
        """Edit multiple stacks' position and/or z parameters. Single save at end."""
        if not edits:
            return []

        edited: list[Stack] = []
        for e in edits:
            stack_id = str(e["stack_id"])
            stack = self._config.stacks.get(stack_id)
            if stack is None:
                raise ValueError(f"Stack {stack_id} not found")
            if stack.status != StackStatus.PLANNED:
                raise RuntimeError(f"Cannot edit stack {stack_id} with status {stack.status}")

            if "x" in e:
                stack.x = float(e["x"])
            if "y" in e:
                stack.y = float(e["y"])
            if "z_start" in e:
                stack.z_start = float(e["z_start"])
            if "z_end" in e:
                stack.z_end = float(e["z_end"])

            stack.edited_at = datetime.datetime.now(tz=datetime.UTC)
            edited.append(stack)

        return edited

    def remove_stacks(self, stack_ids: list[str]) -> None:
        """Remove multiple stacks by ID. Single save at end."""
        if not stack_ids:
            return

        for stack_id in stack_ids:
            stack = self._config.stacks.get(stack_id)
            if stack is None:
                raise ValueError(f"Stack {stack_id} not found")
            if stack.status == StackStatus.COMPLETED:
                raise RuntimeError(f"Cannot remove completed stack {stack_id}")
            del self._config.stacks[stack_id]

        profiles_with_stacks = {s.profile_id for s in self._config.stacks.values()}
        self._config.plan.profile_order = [
            pid for pid in self._config.plan.profile_order if pid in profiles_with_stacks
        ]

    def set_stack_order(self, order: StackOrder) -> None:
        self._config.plan.stack_order = order

    def set_sort_by_profile(self, sort_by_profile: bool) -> None:
        self._config.plan.sort_by_profile = sort_by_profile

    def reorder_profiles(self, profile_ids: list[str]) -> None:
        plan = self._config.plan
        plan.profile_order = [pid for pid in profile_ids if pid in plan.profile_order]

    # ==================== Acquisition ====================

    async def acquire_stack(self, stack_id: str) -> StackResult:
        """Acquire a single stack by ID."""
        stack = self._config.stacks.get(stack_id)
        if stack is None:
            raise ValueError(f"Stack {stack_id} not found")
        if stack.status != StackStatus.PLANNED:
            raise RuntimeError(f"Stack {stack_id} has status {stack.status}, expected PLANNED")
        if self._rig.mode == RigMode.ACQUIRING:
            raise RuntimeError("Another stack is currently being acquired")

        stack.started_at = datetime.datetime.now(tz=datetime.UTC)
        result = await self._rig.acquire_stack(
            stack,
            store_path=self.store_path,
            max_level=self._config.output.max_level,
            compression=self._config.output.compression,
        )

        stack.status = result.status
        stack.output_path = str(result.output_dir)
        stack.completed_at = datetime.datetime.now(tz=datetime.UTC)
        return result

    def _pick_next_stack(self) -> Stack | None:
        order = self.compute_stack_order()
        for stack_id in order:
            stack = self._config.stacks.get(stack_id)
            if stack and stack.status == StackStatus.PLANNED:
                return stack
        return None

    async def acquire_all(self) -> list[StackResult]:
        """Acquire all PLANNED stacks, picking the next dynamically after each."""
        results: list[StackResult] = []
        total = sum(1 for s in self._config.stacks.values() if s.status == StackStatus.PLANNED)
        self._log.info(f"Starting acquisition of {total} stacks")

        while (stack := self._pick_next_stack()) is not None:
            result = await self.acquire_stack(stack.stack_id)
            results.append(result)

        self._log.info(f"Acquisition complete: {len(results)} stacks processed")
        return results

    async def stop_acquisition(self) -> None:
        self._log.warning("Stopping acquisitions is currently not supported")

    # ==================== Lifecycle ====================

    async def close(self) -> None:
        """Stop autosaving (with a final flush), unsubscribe, and stop the rig."""
        self._unsubscribe_fov()
        await self._store.stop_autosave()
        await self._rig.close()
        self._log.info("Session closed")
