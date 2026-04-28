"""Wire schemas for the ``stacks.*`` REST namespace.

No bus events or commands today — stack mutations trigger an ``app.status``
broadcast at the route level rather than a per-stack typed event. Only REST
request bodies live here.
"""

from pydantic import BaseModel

from vxl.stack import StackOrder

# ==================== Requests (REST) ====================


class StackInput(BaseModel):
    """One row of POST ``/session/stacks`` — a fresh stack to add."""

    x: float
    y: float
    z_start: float
    z_end: float


class AddStacksRequest(BaseModel):
    """POST ``/session/stacks`` — bulk add."""

    stacks: list[StackInput]


class StackEditInput(BaseModel):
    """One row of PATCH ``/session/stacks`` — partial update keyed by ``stack_id``."""

    stack_id: str
    x: float | None = None
    y: float | None = None
    z_start: float | None = None
    z_end: float | None = None


class EditStacksRequest(BaseModel):
    """PATCH ``/session/stacks`` — bulk edit."""

    edits: list[StackEditInput]


class RemoveStacksRequest(BaseModel):
    """DELETE ``/session/stacks`` — bulk remove by id."""

    stack_ids: list[str]


class UpdateOrderRequest(BaseModel):
    """PUT ``/session/stacks/order`` — change traversal: algorithm, sort-by-profile, or explicit profile order."""

    stack_order: StackOrder | None = None
    sort_by_profile: bool | None = None
    profile_order: list[str] | None = None


class UpdateDefaultsRequest(BaseModel):
    """PUT ``/session/stacks/defaults`` — defaults applied to newly-created stacks."""

    z_step: float | None = None
    default_z_start: float | None = None
    default_z_end: float | None = None
