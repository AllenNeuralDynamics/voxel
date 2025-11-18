"""REST API endpoints for profile management."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from spim_rig import SpimRig
from spim_rig.config import ChannelConfig
from spim_rig.web.control import ControlService, get_control_service_from_request

router = APIRouter(prefix="/profiles", tags=["profiles"])
log = logging.getLogger(__name__)


class ProfileResponse(BaseModel):
    """Profile information with embedded channel configs."""

    id: str
    label: str | None = None
    desc: str
    channels: dict[str, ChannelConfig]  # channel_id -> ChannelConfig


class ProfileListResponse(BaseModel):
    """Response model for listing profiles."""

    profiles: list[ProfileResponse]
    active_profile_id: str | None


class SetProfileRequest(BaseModel):
    """Request model for setting active profile."""

    profile_id: str


def get_rig(request: Request) -> SpimRig:
    """Dependency to get the SpimRig instance from app state."""
    return request.app.state.rig


@router.get("", response_model=ProfileListResponse)
async def list_profiles(rig: SpimRig = Depends(get_rig)) -> ProfileListResponse:
    """Get list of all available profiles with their channel information.

    Returns the list of profiles and indicates which one is currently active.
    """
    profiles = []
    for profile_id, profile_config in rig.config.profiles.items():
        # Build channels dict for this profile
        channels = {
            ch_id: rig.config.channels[ch_id] for ch_id in profile_config.channels if ch_id in rig.config.channels
        }

        profiles.append(
            ProfileResponse(
                id=profile_id,
                label=profile_config.label,
                desc=profile_config.desc,
                channels=channels,
            )
        )

    return ProfileListResponse(
        profiles=profiles,
        active_profile_id=rig.active_profile_id,
    )


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: str, rig: SpimRig = Depends(get_rig)) -> ProfileResponse:
    """Get detailed information about a specific profile.

    Args:
        profile_id: The profile ID to retrieve.

    Returns:
        Profile information with embedded channel configs.

    Raises:
        HTTPException: If profile_id does not exist.
    """
    if profile_id not in rig.config.profiles:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

    profile_config = rig.config.profiles[profile_id]

    # Build channels dict for this profile
    channels = {ch_id: rig.config.channels[ch_id] for ch_id in profile_config.channels if ch_id in rig.config.channels}

    return ProfileResponse(
        id=profile_id,
        label=profile_config.label,
        desc=profile_config.desc,
        channels=channels,
    )


@router.post("/active")
async def set_active_profile(
    request: SetProfileRequest,
    rig: SpimRig = Depends(get_rig),
    control: ControlService = Depends(get_control_service_from_request),
) -> dict:
    """Set the active profile.

    This will configure devices (filter wheels, etc.) for the new profile.
    If preview is running, it will seamlessly transition to the new profile's cameras.

    Args:
        request: Request containing the profile_id to activate.

    Returns:
        Success message with the new active profile ID and channels.

    Raises:
        HTTPException: If profile_id does not exist or activation fails.
    """
    try:
        await rig.set_active_profile(request.profile_id)
        log.info(f"Active profile set to '{request.profile_id}'")
        await control.emit_profile_change()

        return {
            "status": "success",
            "active_profile_id": rig.active_profile_id,
            "channels": list(rig.active_channels.keys()),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"Failed to set active profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set active profile: {str(e)}")


@router.get("/active/info", response_model=ProfileResponse | None)
async def get_active_profile(rig: SpimRig = Depends(get_rig)) -> ProfileResponse | None:
    """Get information about the currently active profile.

    Returns:
        Active profile information with channels, or None if no profile is active.
    """
    if not rig.active_profile_id:
        return None

    profile_config = rig.config.profiles[rig.active_profile_id]

    # Build channels dict
    channels = {ch_id: rig.config.channels[ch_id] for ch_id in profile_config.channels if ch_id in rig.config.channels}

    return ProfileResponse(
        id=rig.active_profile_id,
        label=profile_config.label,
        desc=profile_config.desc,
        channels=channels,
    )


@router.delete("/active")
async def clear_active_profile(
    rig: SpimRig = Depends(get_rig),
    control: ControlService = Depends(get_control_service_from_request),
) -> dict:
    """Clear the active profile.

    Returns:
        Success message.
    """
    rig.clear_active_profile()
    await control.emit_profile_change()
    log.info("Active profile cleared")

    return {
        "status": "success",
        "active_profile_id": None,
    }
