"""Profiles service — profile switching, waveforms, ROIs, device-prop save/apply.

Owns ``/profile/*`` REST routes and ``profile/*`` WS topics.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from vxl import Session

from .ws import BroadcastCallback

log = logging.getLogger(__name__)
router = APIRouter(tags=["profile"])


# ==================== Service ====================


class ProfilesService:
    """REST + WS surface for ``session.microscope.profiles``."""

    topic_prefixes: tuple[str, ...] = ("profile/",)

    def __init__(self, session: Session, broadcast: BroadcastCallback) -> None:
        self.session = session
        self.broadcast = broadcast
        self._unsub = session.microscope.profiles.profile_changed.subscribe(self._on_profile_changed)

    async def close(self) -> None:
        self._unsub()

    # ---- WS ----

    async def handle_message(self, sender_id: str, topic: str, payload: dict[str, Any]) -> None:
        log.debug("profiles WS from %s → %s", sender_id, topic)
        match topic:
            case "profile/update":
                profile_id = payload.get("profile_id") if isinstance(payload, dict) else payload
                if not profile_id:
                    raise ValueError("Missing profile_id")
                await self.session.set_active_profile(profile_id)

    # ---- Waveform helpers ----

    def get_waveform_traces(self) -> dict[str, Any]:
        """Active profile's waveforms + timing + sampled traces for visualization."""
        profiles = self.session.microscope.profiles
        traces = profiles.preview_traces(target_points=1000)
        daq = profiles.active.daq.model_dump(mode="json")
        return {
            "profile_id": profiles.active_id,
            "traces": traces,
            "waveforms": daq["waveforms"],
            "timing": daq["timing"],
        }

    def broadcast_waveforms(self) -> None:
        try:
            self.broadcast({"topic": "profile/waveforms", "payload": self.get_waveform_traces()}, with_status=True)
        except Exception:
            log.exception("Failed to broadcast waveforms")

    async def _on_profile_changed(self, profile_id: str) -> None:
        self.broadcast_waveforms()
        self.broadcast({"topic": "profile/changed", "payload": {"profile_id": profile_id}}, with_status=True)


# ==================== Dependency ====================


def get_profiles_service(request: Request) -> ProfilesService:
    app_service = request.app.state.app_service
    if app_service.session_service is None:
        raise HTTPException(status_code=503, detail="No active session")
    return app_service.session_service.profiles


# ==================== Request models ====================


class SetProfileRequest(BaseModel):
    profile_id: str


class SavePropsRequest(BaseModel):
    device_id: str | None = None


class ApplyPropsRequest(BaseModel):
    device_ids: list[str] | None = None


class SaveRoiRequest(BaseModel):
    camera_id: str


class ApplyRoiRequest(BaseModel):
    camera_id: str


class UpdateWaveformsRequest(BaseModel):
    waveforms: dict[str, Any] | None = None
    timing: dict[str, Any] | None = None


# ==================== REST ====================


@router.post("/profile/active")
async def set_active_profile(
    request: SetProfileRequest,
    service: Annotated[ProfilesService, Depends(get_profiles_service)],
) -> dict[str, str]:
    try:
        await service.session.set_active_profile(request.profile_id)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"profile_id": request.profile_id}


@router.post("/profile/save-props")
async def save_props(
    request: SavePropsRequest,
    service: Annotated[ProfilesService, Depends(get_profiles_service)],
) -> dict[str, list[str]]:
    try:
        profiles = service.session.microscope.profiles
        if request.device_id is None:
            saved = await profiles.save_all_device_props()
        else:
            await profiles.save_device_props(request.device_id)
            saved = [request.device_id]
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    saved_props = {dev: profiles.active.props.get(dev, {}) for dev in saved}
    service.broadcast(
        {"topic": "profile/props_saved", "payload": {profiles.active_id: saved_props}},
        with_status=True,
    )
    return {"saved": saved}


@router.post("/profile/apply-props")
async def apply_props(
    request: ApplyPropsRequest,
    service: Annotated[ProfilesService, Depends(get_profiles_service)],
) -> dict[str, list[str]]:
    applied = await service.session.microscope.profiles.apply_profile_props(request.device_ids)
    service.broadcast(
        {"topic": "profile/props_applied", "payload": {"devices": applied}},
        with_status=True,
    )
    return {"applied": applied}


@router.post("/profile/save-roi")
async def save_roi(
    request: SaveRoiRequest,
    service: Annotated[ProfilesService, Depends(get_profiles_service)],
) -> dict[str, Any]:
    try:
        profiles = service.session.microscope.profiles
        roi = await profiles.save_camera_roi(request.camera_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    service.broadcast(
        {"topic": "profile/roi_saved", "payload": {
            "profile_id": profiles.active_id,
            "camera_id": request.camera_id,
            "roi": roi.model_dump(),
        }},
        with_status=True,
    )
    return {"camera_id": request.camera_id, "roi": roi.model_dump()}


@router.post("/profile/apply-roi")
async def apply_roi(
    request: ApplyRoiRequest,
    service: Annotated[ProfilesService, Depends(get_profiles_service)],
) -> dict[str, Any]:
    try:
        roi = await service.session.microscope.profiles.revert_camera_roi(request.camera_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    service.broadcast(
        {"topic": "profile/roi_applied", "payload": {"camera_id": request.camera_id}},
        with_status=True,
    )
    return {"camera_id": request.camera_id, "roi": roi.model_dump() if roi else None}


@router.patch("/profile/waveforms")
async def update_waveforms(
    request: UpdateWaveformsRequest,
    service: Annotated[ProfilesService, Depends(get_profiles_service)],
) -> dict[str, Any]:
    try:
        await service.session.update_waveforms(waveforms=request.waveforms, timing=request.timing)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    service.broadcast_waveforms()
    service.broadcast({}, with_status=True)
    return service.get_waveform_traces()


@router.get("/profile/waveforms")
async def get_waveforms(
    service: Annotated[ProfilesService, Depends(get_profiles_service)],
) -> dict[str, Any]:
    return service.get_waveform_traces()
