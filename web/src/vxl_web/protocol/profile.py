"""Wire schemas for the ``profile.*`` topic namespace.

Most profile state changes also trigger an ``app.status`` refresh — these
namespaced events carry the *delta* (which thing changed) so subscribers can
react to specific transitions without re-rendering everything.
"""

from typing import Any

from pydantic import BaseModel

from vxl.camera.base import SensorROI

# ==================== Body shapes (used for inbound/outbound) ====================


class ProfileSelection(BaseModel):
    """Identifies the active profile — body for ``profile.update`` (bus + REST) and ``profile.changed``."""

    profile_id: str


# ==================== Events ====================


class ProfilePropsSaved(BaseModel):
    """Broadcast on ``profile.props.saved`` after writing live props back to a profile.

    ``saved`` is keyed by profile_id, then device_id, then prop name.
    """

    saved: dict[str, dict[str, dict[str, Any]]]


class ProfilePropsApplied(BaseModel):
    """Broadcast on ``profile.props.applied`` after pushing profile props to devices."""

    devices: list[str]


class ProfileRoiSaved(BaseModel):
    """Broadcast on ``profile.roi.saved`` after capturing a camera's current ROI."""

    profile_id: str
    camera_id: str
    roi: SensorROI


class ProfileRoiApplied(BaseModel):
    """Broadcast on ``profile.roi.applied`` after pushing a saved ROI to the camera."""

    camera_id: str


# ==================== Requests (REST) ====================


class SavePropsRequest(BaseModel):
    """POST ``/session/profile/save-props`` — optional single device, else all."""

    device_id: str | None = None


class ApplyPropsRequest(BaseModel):
    """POST ``/session/profile/apply-props`` — optional subset, else all profile-bound devices."""

    device_ids: list[str] | None = None


class SaveRoiRequest(BaseModel):
    """POST ``/session/profile/save-roi`` — capture the named camera's current ROI."""

    camera_id: str


class ApplyRoiRequest(BaseModel):
    """POST ``/session/profile/apply-roi`` — push the saved ROI back to the camera."""

    camera_id: str
