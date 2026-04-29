"""Wire schemas for the ``device.*`` topic namespace.

Properties and command results stream out per-device; ``device_id`` lives in
the body so the topic stays static (good for typed dispatch) instead of being
encoded into the topic string (`device/{id}/properties` in the legacy path).
"""

from typing import Any

from pydantic import BaseModel

from rigup import DeviceInterface, PropResults

# ==================== Models (also REST response shapes) ====================


class DeviceSnapshot(BaseModel):
    """One device's identity + interface (or error) at a point in time."""

    id: str
    connected: bool
    interface: DeviceInterface | None = None
    error: str | None = None


class DevicesSnapshot(BaseModel):
    """All devices at a point in time. Used by REST and nested in ``SessionDetails``."""

    devices: dict[str, DeviceSnapshot]
    count: int


# ==================== Events ====================


class DevicePropsUpdate(BaseModel):
    """Broadcast on ``device.props.update`` whenever a device's properties change.

    Driven by the device handle's ``on_props_change`` signal and by explicit
    ``set_property`` commands. ``properties`` carries the per-prop status from
    the underlying call (success values, validation errors).
    """

    device: str
    properties: PropResults


class DeviceCommandResult(BaseModel):
    """Broadcast on ``device.command.executed`` after a device command runs.

    ``result`` is the rigup command response model_dump'd — preserves ok/err
    discrimination so subscribers can react to failures.
    """

    device: str
    command: str
    result: Any


# ==================== Commands ====================


class DeviceSetProperty(BaseModel):
    """Inbound ``device.set_property`` — write one or more properties."""

    device: str
    properties: dict[str, Any]


class DeviceExecuteCommand(BaseModel):
    """Inbound ``device.execute_command`` — run a named command on a device."""

    device: str
    command: str
    args: list[Any] = []
    kwargs: dict[str, Any] = {}


# ==================== Requests (REST) ====================
#
# REST request bodies omit ``device`` (it lives in the URL path
# ``/devices/{device_id}/...``) — the bus equivalents above carry it inside
# the body since topics are static.


class SetPropertiesRequest(BaseModel):
    """PATCH ``/session/devices/{device_id}/properties``."""

    properties: dict[str, Any]


class ExecuteCommandRequest(BaseModel):
    """POST ``/session/devices/{device_id}/commands/{command_name}``."""

    args: list[Any] = []
    kwargs: dict[str, Any] = {}
