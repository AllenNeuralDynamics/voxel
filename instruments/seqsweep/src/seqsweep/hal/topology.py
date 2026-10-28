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
        node_devices = {did for node in self.nodes.values() for did in node.devices}
        return node_devices | set(self.devices.keys())

    @model_validator(mode="after")
    def _check_device_references(self) -> Self:
        if self.scan_controller not in self.device_uids:
            raise ValueError(f"scan_controller '{self.scan_controller}' is not a device in the rig")
        return self
