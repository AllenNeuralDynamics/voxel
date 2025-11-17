from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from pyrig import RigConfig


class DeviceType(StrEnum):
    DAQ = "daq"
    CAMERA = "camera"
    LASER = "laser"


class DaqConfig(BaseModel):
    device: str
    acq_ports: dict[str, str]

    @field_validator("acq_ports")
    @classmethod
    def validate_unique_ports(cls, v: dict[str, str]) -> dict[str, str]:
        ports = list(v.values())
        if len(ports) != len(set(ports)):
            duplicates = [p for p in set(ports) if ports.count(p) > 1]
            raise ValueError(f"Duplicate acq_ports detected: {duplicates}")
        return v


class StageConfig(BaseModel):
    x: str
    y: str
    z: str
    roll: str | None = None
    pitch: str | None = None
    yaw: str | None = None


class OpticalPathConfig(BaseModel):
    aux_devices: list[str] = Field(default_factory=list)


class DetectionPathConfig(OpticalPathConfig):
    filter_wheels: list[str]


class IlluminationPathConfig(OpticalPathConfig): ...


class SpimLayout(BaseModel):
    detection: dict[str, DetectionPathConfig]
    illumination: dict[str, IlluminationPathConfig]


class SpimRigConfig(RigConfig):
    daq: DaqConfig
    # stage: StageConfig
    detection: dict[str, DetectionPathConfig]
    illumination: dict[str, IlluminationPathConfig]

    @model_validator(mode="after")
    def validate_device_references(self) -> Self:
        """Validate that all device references exist in nodes."""
        devices = self.device_uids
        errors = []

        # Validate detection paths reference valid devices
        for device_id in self.detection:
            if device_id not in devices:
                errors.append(f"Detection path '{device_id}' not found in devices")

        # Validate illumination paths reference valid devices
        for device_id in self.illumination:
            if device_id not in devices:
                errors.append(f"Illumination path '{device_id}' not found in devices")

        # Validate DAQ device reference
        if self.daq.device not in devices:
            errors.append(f"DAQ device '{self.daq.device}' not found in devices")

        # Validate DAQ acq_ports reference valid devices
        for device_id in self.daq.acq_ports:
            if device_id not in devices:
                errors.append(f"DAQ acq_port device '{device_id}' not found in devices")

        # Validate filter_wheels and aux_devices in detection paths
        for path_id, path in self.detection.items():
            for fw in path.filter_wheels:
                if fw not in devices:
                    errors.append(f"Filter wheel '{fw}' in detection path '{path_id}' not found in devices")
            for aux in path.aux_devices:
                if aux not in devices:
                    errors.append(f"Aux device '{aux}' in detection path '{path_id}' not found in devices")

        # Validate aux_devices in illumination paths
        for path_id, path in self.illumination.items():
            for aux in path.aux_devices:
                if aux not in devices:
                    errors.append(f"Aux device '{aux}' in illumination path '{path_id}' not found in devices")

        # Validate stage axis references
        # if hasattr(self, "stage") and self.stage is not None:
        #     for axis_name in ["x", "y", "z"]:
        #         axis_device = getattr(self.stage, axis_name)
        #         if axis_device not in devices:
        #             errors.append(f"Stage axis '{axis_name}' device '{axis_device}' not found in devices")
        #     for axis_name in ["roll", "pitch", "yaw"]:
        #         axis_device = getattr(self.stage, axis_name)
        #         if axis_device is not None and axis_device not in devices:
        #             errors.append(f"Stage axis '{axis_name}' device '{axis_device}' not found in devices")

        if errors:
            raise ValueError("\n".join(errors))

        return self
