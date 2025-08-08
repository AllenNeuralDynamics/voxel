from voxel_classic.metadata.metadata_class import MetadataClass

X_ANATOMICAL_DIRECTIONS = {
    "Anterior to Posterior": "Anterior_to_posterior",
    "Posterior to Anterior": "Posterior_to_anterior",
}

Y_ANATOMICAL_DIRECTIONS = {
    "Inferior to Superior": "Inferior_to_superior",
    "Superior to Inferior": "Superior_to_inferior",
}

Z_ANATOMICAL_DIRECTIONS = {"Left to Right": "Left_to_right", "Right to Left": "Right_to_left"}

# the inflection package we're using to pluralize words chose media for plural of mediums
MEDIA = {"air": "air", "multi": "multi", "oil": "oil", "PBS": "PBS", "water": "water", "other": "other"}

DATE_FORMATS = {
    "Year/Month/Day/Hour/Minute/Second": "%Y-%m-%d_%H-%M-%S",
    "Month/Day/Year/Hour/Minute/Second": "%m-%d-%Y_%H-%M-%S",
    "Month/Day/Year": "%m-%d-%Y",
    "None": None,
}


class AINDMetadataClass(MetadataClass):
    """
    Metadata class that includes inputs for anatomical directions and mediums.
    """
