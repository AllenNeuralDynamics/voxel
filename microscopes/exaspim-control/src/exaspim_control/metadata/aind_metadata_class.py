from datetime import datetime
from typing import Any

import inflection
from voxel.utils.log import VoxelLogging

X_ANATOMICAL_DIRECTIONS = {
    'Anterior to Posterior': 'Anterior_to_posterior',
    'Posterior to Anterior': 'Posterior_to_anterior',
}

Y_ANATOMICAL_DIRECTIONS = {
    'Inferior to Superior': 'Inferior_to_superior',
    'Superior to Inferior': 'Superior_to_inferior',
}

Z_ANATOMICAL_DIRECTIONS = {'Left to Right': 'Left_to_right', 'Right to Left': 'Right_to_left'}

# the inflection package we're using to pluralize words chose media for plural of mediums
MEDIA = {'air': 'air', 'multi': 'multi', 'oil': 'oil', 'PBS': 'PBS', 'water': 'water', 'other': 'other'}

DATE_FORMATS = {
    'Year/Month/Day/Hour/Minute/Second': '%Y-%m-%d_%H-%M-%S',
    'Month/Day/Year/Hour/Minute/Second': '%m-%d-%Y_%H-%M-%S',
    'Month/Day/Year': '%m-%d-%Y',
    'None': None,
}


class AINDMetadataClass:
    """Metadata class for handling metadata properties and generating acquisition names."""

    def __init__(
        self,
        metadata_dictionary: dict[str, Any],
        date_format: str = 'None',
        name_specs: dict[str, Any] | None = None,
    ):
        """Initialize the MetadataClass.

        :param metadata_dictionary: Dictionary containing metadata properties.
        :type metadata_dictionary: dict
        :param date_format: Date format for the acquisition name, defaults to "None".
        :type date_format: str, optional
        :param name_specs: Specifications for the acquisition name format, defaults to {}.
        :type name_specs: dict, optional
        """
        name_specs = name_specs or {}
        self.log = VoxelLogging.get_logger(obj=self)

        for key, value in metadata_dictionary.items():
            # create properties from keyword entries
            setattr(self, f'_{key}', value)
            new_property = property(
                fget=lambda instance, k=key: self.get_class_attribute(instance, k),
                fset=lambda metadataclass, val, k=key: self.set_class_attribute(val, k),
            )
            setattr(type(self), key, new_property)
        # initialize properties
        self.date_format = date_format
        if 'delimiter' not in name_specs:
            self.log.warning('no delimiter specified in yaml file. defaulting to "_".')
        self.delimiter = name_specs.get('delimiter', '_')
        self.acquisition_name_format = name_specs.get('format', [])
        self._acquisition_name = self.generate_acquisition_name()

    def set_class_attribute(self, value: Any, name: str) -> None:
        """Set the value of a class attribute.

        :param value: The value to set.
        :type value: Any
        :param name: The name of the attribute.
        :type name: str
        :raises ValueError: If the value is not valid for the attribute.
        """
        if inflection.pluralize(name).upper() in globals():
            opt_dict = globals()[inflection.pluralize(name).upper()]
            if value not in opt_dict:
                msg = f'{value} not in {opt_dict.keys()}'
                raise ValueError(msg)
            setattr(self, f'_{name}', opt_dict[value])
        else:
            setattr(self, f'_{name}', value)

    def get_class_attribute(self, instance: Any, name: str) -> Any:
        """Get the value of a class attribute.

        :param instance: The instance of the class.
        :type instance: object
        :param name: The name of the attribute.
        :type name: str
        :return: The value of the attribute.
        :rtype: Any
        """
        if inflection.pluralize(name).upper() in globals():
            opt_dict = globals()[inflection.pluralize(name).upper()]
            inv = {v: k for k, v in opt_dict.items()}
            return inv[getattr(self, f'_{name}')]
        return getattr(self, f'_{name}')

    @property
    def date_format(self) -> str | None:
        """Get the date format.

        :return: The date format.
        :rtype: str
        """
        return self._date_format

    @date_format.setter
    def date_format(self, fmt: str) -> None:
        """Set the date format.

        :param fmt: The date format to set.
        :type fmt: str
        :raises ValueError: If the date format is not valid.
        """
        if fmt not in list(DATE_FORMATS.keys()):
            msg = f'{fmt} is not a valid datetime format. Please choose from {DATE_FORMATS.keys()}'
            raise ValueError(msg)
        self._date_format = DATE_FORMATS[fmt]

    @property
    def acquisition_name_format(self) -> list:
        """Get the acquisition name format.

        :return: The acquisition name format.
        :rtype: list
        """
        return self._acquisition_name_format

    @acquisition_name_format.setter
    def acquisition_name_format(self, form: list) -> None:
        """Set the acquisition name format.

        :param form: The acquisition name format to set.
        :type form: list
        :raises ValueError: If the format contains invalid properties.
        """
        for prop_name in form:
            if not isinstance(
                getattr(type(self), prop_name, None),
                property,
            ):  # check if prop name is metadata property
                msg = f'{prop_name} is not a metadata property. Please choose from {self.__dir__()}'
                raise ValueError(msg)
        self._acquisition_name_format = form

    @property
    def delimiter(self) -> str:
        """Get the delimiter for the acquisition name.

        :return: The delimiter.
        :rtype: str
        """
        return self._delimiter

    @delimiter.setter
    def delimiter(self, delimiter: str) -> None:
        """Set the delimiter for the acquisition name.

        :param delimiter: The delimiter to set.
        :type delimiter: str
        """
        self._delimiter = delimiter

    @property
    def acquisition_name(self) -> str:
        """Get the acquisition name.

        :return: The acquisition name.
        :rtype: str
        """
        return self.generate_acquisition_name()

    def generate_acquisition_name(self) -> str:
        """Generate the acquisition name based on the format and delimiter.

        :raises ValueError: If the format contains invalid properties.
        :return: The generated acquisition name.
        :rtype: str
        """
        delimiter = self.delimiter
        form = self._acquisition_name_format

        if form == []:
            return 'test'
        name = []
        for prop_name in form:
            if not isinstance(
                getattr(type(self), prop_name, None),
                property,
            ):  # check if prop name is metadata property
                msg = f'{prop_name} is not a metadata property. Please choose from {self.__dir__()}'
                raise ValueError(msg)
            name.append(str(getattr(self, prop_name)))
        if self._date_format is not None:
            name.append(datetime.now().strftime(self._date_format))
        return f'{delimiter}'.join(name)
