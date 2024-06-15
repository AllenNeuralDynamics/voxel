from abc import ABC


class BaseChiller(ABC):
    """
    Base class for all chillers.
    """

    def __init__(self, id: str):
        self.id = id

    @property
    def temperature_c(self) -> float:
        """
        Get the current temperature of the chiller.

        Returns
        -------
        float
            The current temperature of the chiller.
        """
        pass

    @temperature_c.setter
    def temperature_c(self, temperature: float):
        """
        Set the temperature of the chiller.

        Parameters
        ----------
        temperature : float
            The temperature to set the chiller to.
        """
        pass

    def __repr__(self):
        return f'<{self.__class__.__name__} Chiller {self.id} - temp: {self.tempurature_c}°C>'
