"""Names that the user makes up for things in the instrument files.

Each one reaches URLs, file paths or other names, so it uses only letters, digits, ``_`` and ``-``. Device UIDs
are defined with the devices, in ``rigup.config``.
"""

from typing import Annotated

from vxlib.schema import identifier

ChannelId = Annotated[str, identifier("Channel id")]
ProfileId = Annotated[str, identifier("Profile id")]
TaskId = Annotated[str, identifier("Task id")]
NetName = Annotated[str, identifier("Net name")]
RoutingDimension = Annotated[str, identifier("Routing dimension")]
RouteName = Annotated[str, identifier("Route name")]

__all__ = ["ChannelId", "NetName", "ProfileId", "RouteName", "RoutingDimension", "TaskId"]
