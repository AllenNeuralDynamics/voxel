import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from vxl.analog_out import AOSignals
from vxl_web.protocol.profile import (
    ApplyPropsRequest,
    ApplyRoiRequest,
    ProfilePropsApplied,
    ProfilePropsSaved,
    ProfileRoiApplied,
    ProfileRoiSaved,
    ProfileSelection,
    SavePropsRequest,
    SaveRoiRequest,
)

from ._deps import AppDep, BusDep, SessionDep

log = logging.getLogger(__name__)
router = APIRouter(prefix="/profile", tags=["profile"])


@router.post("/active")
async def set_active_profile(request: ProfileSelection, svc: SessionDep) -> dict[str, str]:
    """Profile-changed event + status broadcast fire automatically via the
    ``profile_changed`` subscription wired in ``services/profile.setup``.
    """
    try:
        await svc.session.set_active_profile(request.profile_id)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"profile_id": request.profile_id}


@router.post("/save-props")
async def save_props(request: SavePropsRequest, svc: SessionDep, app: AppDep, bus: BusDep) -> dict[str, list[str]]:
    try:
        profiles = svc.session.microscope.profiles
        if request.device_id is None:
            saved = await profiles.save_all_device_props()
        else:
            await profiles.save_device_props(request.device_id)
            saved = [request.device_id]
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    saved_props = {dev: profiles.active.props.get(dev, {}) for dev in saved}
    bus.broadcast("profile.props.saved", ProfilePropsSaved(saved={profiles.active_id: saved_props}))
    await app.broadcast_status()
    return {"saved": saved}


@router.post("/apply-props")
async def apply_props(request: ApplyPropsRequest, svc: SessionDep, app: AppDep, bus: BusDep) -> dict[str, list[str]]:
    applied = await svc.session.microscope.profiles.apply_profile_props(request.device_ids)
    bus.broadcast("profile.props.applied", ProfilePropsApplied(devices=applied))
    await app.broadcast_status()
    return {"applied": applied}


@router.post("/save-roi")
async def save_roi(request: SaveRoiRequest, svc: SessionDep, app: AppDep, bus: BusDep) -> dict[str, Any]:
    try:
        profiles = svc.session.microscope.profiles
        roi = await profiles.save_camera_roi(request.camera_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    bus.broadcast(
        "profile.roi.saved",
        ProfileRoiSaved(profile_id=profiles.active_id, camera_id=request.camera_id, roi=roi),
    )
    await app.broadcast_status()
    return {"camera_id": request.camera_id, "roi": roi.model_dump()}


@router.post("/apply-roi")
async def apply_roi(request: ApplyRoiRequest, svc: SessionDep, app: AppDep, bus: BusDep) -> dict[str, Any]:
    try:
        roi = await svc.session.microscope.profiles.revert_camera_roi(request.camera_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    bus.broadcast("profile.roi.applied", ProfileRoiApplied(camera_id=request.camera_id))
    await app.broadcast_status()
    return {"camera_id": request.camera_id, "roi": roi.model_dump() if roi else None}


@router.patch("/sync/{ao_uid}")
async def update_ao_signals(ao_uid: str, signals: AOSignals, svc: SessionDep, app: AppDep) -> dict[str, Any]:
    """Push new ``AOSignals`` to the named AO device and commit to the active profile on success.

    Apply-first ordering: if the driver rejects the signals, the in-memory config is
    left untouched and a 400 is returned. The streamed ``loaded`` property on the AO
    device is the single source of truth for what's currently running.
    """
    try:
        await svc.session.update_ao_signals(ao_uid, signals)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await app.broadcast_status()
    return {"ao_uid": ao_uid}
