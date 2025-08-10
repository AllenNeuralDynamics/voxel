from abc import abstractmethod


class BaseMetadata:
    """
    Base class for metadata handling.
    """

    @property
    @abstractmethod
    def acquisition_name(self) -> str:
        """
        Get the name of the acquisition.

        :return: The acquisition name.
        :rtype: str
        """

        pass
