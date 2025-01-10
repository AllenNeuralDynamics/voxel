import logging
from datetime import datetime

import inflection

from voxel.metadata.base import BaseMetadata

DATE_FORMATS = {
    "Year/Month/Day/Hour/Minute/Second": "%Y-%m-%d_%H-%M-%S",
    "Month/Day/Year/Hour/Minute/Second": "%m-%d-%Y_%H-%M-%S",
    "Month/Day/Year": "%m-%d-%Y",
    "None": None,
}


class MetadataClass(BaseMetadata):
    """Class to handle metadata"""

    def __init__(self, metadata_dictionary: dict, date_format: str = "None", name_specs: dict = {}):

        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        super().__init__()

        for key, value in metadata_dictionary.items():
            # create properties from keyword entries
            setattr(self, f"_{key}", value)
            new_property = property(
                fget=lambda instance, k=key: self.get_class_attribute(instance, k),
                fset=lambda metadataclass, val, k=key: self.set_class_attribute(val, k),
            )
            setattr(type(self), key, new_property)
        # initialize properties
        self.date_format = date_format
        if "delimiter" not in name_specs.keys():
            self.log.warning('no delimiter specified in yaml file. defaulting to "_".')
        self.delimiter = name_specs.get("delimiter", "_")
        self.acquisition_name_format = name_specs.get("format", [])
        self._acquisition_name = self.generate_acquisition_name()

    def set_class_attribute(self, value, name):
        """Function to set attribute of class to act as setters"""

        if inflection.pluralize(name).upper() in globals().keys():
            opt_dict = globals()[inflection.pluralize(name).upper()]
            if value not in opt_dict.keys():
                raise ValueError(f"{value} not in {opt_dict.keys()}")
            else:
                setattr(self, f"_{name}", opt_dict[value])
        else:
            setattr(self, f"_{name}", value)

    def get_class_attribute(self, instance, name):
        """Function to get attribute of class to act as getters"""

        if inflection.pluralize(name).upper() in globals().keys():
            opt_dict = globals()[inflection.pluralize(name).upper()]
            inv = {v: k for k, v in opt_dict}
            return inv[getattr(self, f"_{name}")]
        else:
            return getattr(self, f"_{name}")

    @property
    def date_format(self):
        """Format of date used in acquisition_name"""
        return self._date_format

    @date_format.setter
    def date_format(self, format):
        if format not in list(DATE_FORMATS.keys()):
            raise ValueError(f"{format} is not a valid datime format. Please choose from {DATE_FORMATS.keys()}")
        self._date_format = DATE_FORMATS[format]

    @property
    def acquisition_name_format(self):
        """Ordered list of metadata class properties to include in acquisition_name"""
        return self._acquisition_name_format

    @acquisition_name_format.setter
    def acquisition_name_format(self, form: list):
        for prop_name in form:
            if not isinstance(
                getattr(type(self), prop_name, None), property
            ):  # check if prop name is metadata property
                raise ValueError(f"{prop_name} is not a metadata property. Please choose from {self.__dir__()}")
        self._acquisition_name_format = form

    @property
    def delimiter(self):
        """Character to separate properties in acquisition name"""
        return self._delimiter

    @delimiter.setter
    def delimiter(self, delimiter: list):

        self._delimiter = delimiter

    @property
    def acquisition_name(self):
        """Unique name that descibes acquisition adhering to passed in name_specs and date of acquisition"""
        return self.generate_acquisition_name()

    def generate_acquisition_name(self):
        """Function to generate name of acquisition based on format"""

        delimiter = self.delimiter
        form = self._acquisition_name_format

        if form == []:
            return "test"
        else:
            name = []
            for prop_name in form:
                if not isinstance(
                    getattr(type(self), prop_name, None), property
                ):  # check if prop name is metadata property
                    raise ValueError(f"{prop_name} is not a metadata property. Please choose from {self.__dir__()}")
                name.append(str(getattr(self, prop_name)))
            if self._date_format is not None:
                name.append(datetime.now().strftime(self._date_format))
            return f"{delimiter}".join(name)
