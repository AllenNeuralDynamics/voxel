from enum import StrEnum

from pydantic import BaseModel, field_validator


class AnatomicalOrientation(StrEnum):
    ANTERIOR_POSTERIOR = "anterior_posterior"
    POSTERIOR_ANTERIOR = "posterior_anterior"
    INFERIOR_SUPERIOR = "inferior_superior"
    SUPERIOR_INFERIOR = "superior_inferior"
    LEFT_RIGHT = "left_right"
    RIGHT_LEFT = "right_left"


class VoxelMetadata(BaseModel):
    instrument_name: str
    experiment_id: str
    subject_id: str
    experimenter_full_name: str
    immersion_medium: str
    immersion_medium_index: float | int
    x_anatomical_orientation: AnatomicalOrientation
    y_anatomical_orientation: AnatomicalOrientation
    z_anatomical_orientation: AnatomicalOrientation

    @field_validator("subject_id", mode="before")
    @classmethod
    def coerce_subject_id(cls, v) -> str:
        return str(v)

    def __repr__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return self.model_dump_json(indent=2)


# class MetadataNameFormat(TypedDict):
#     delimiter: str
#     properties: list[str]


# @dataclass
# class VoxelMetadata:
#     instrument_name: str
#     experiment_id: str
#     subject_id: str
#     experimenter_full_name: str
#     immersion_medium:
#     name_format: MetadataNameFormat

#     def __post_init__(self):
#         if not self.name_format:
#             self.name_format = {"delimiter": "_", "properties": ["instrument_type", "subject_id"]}
#         if not self.name_format["properties"]:
#             raise ValueError("Name format must contain at least one property.")
#         for prop in self.name_format["properties"]:
#             if not hasattr(self, prop):
#                 raise ValueError(f"Property {prop} not found in metadata.")

#     @property
#     def name(self):
#         return self.name_format["delimiter"].join([str(getattr(self, prop)) for prop in self.name_format["properties"]])

#     def to_dict(self):
#         return {
#             "instrument_name": self.instrument_name,
#             "experiment_id": self.experiment_id,
#             "subject_id": self.subject_id,
#             "experimenter_full_name": self.experimenter_full_name,
#         }
