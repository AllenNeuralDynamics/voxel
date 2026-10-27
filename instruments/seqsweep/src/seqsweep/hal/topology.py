from typing import Self

from pydantic import Field, model_validator

from rigup import RigConfig


class SeqSweepHardwareTopology(RigConfig, frozen=True):
    """The hardware blueprint (``hal``): a rig (``devices`` + ``nodes``, inherited) plus the role each device
    plays. Mirrors Voxel's ``HardwareTopology``: loaded once, never edited at runtime.
    """

    scan_controller: str = Field(description="UID of the scan controller in the rig")
    # TODO: cameras, lasers, z_axis roles

    @property
    def device_uids(self) -> set[str]:
        return set(self.devices) | {uid for node in self.nodes.values() for uid in node.devices}

    @model_validator(mode="after")
    def _check_device_references(self) -> Self:
        for role, uid in [("scan_controller", self.scan_controller)]:
            if uid not in self.device_uids:
                raise ValueError(f"{role} '{uid}' is not a device in the rig")
        return self
