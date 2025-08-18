from abc import abstractmethod

from voxel_classic.devices.base import BaseDevice


class BaseDAQ(BaseDevice):
    """Base class for DAQ devices."""

    def __init__(self, uid: str):
        super().__init__(uid)

    @abstractmethod
    def add_ao_task(self) -> None:
        """
        Add a task to the DAQ.
        """
        pass

    @abstractmethod
    def add_co_task(self, pulse_count: int | None = None) -> None:
        """
        Add a task to the DAQ.
        :param pulse_count: Number of pulses for the task, defaults to None
        :type pulse_count: int, optional
        """
        pass

    @abstractmethod
    def generate_waveforms(self, wavelength: str) -> None:
        """
        Generate waveforms for the task.

        :param wavelength: Wavelength for the waveform (channel)
        :type wavelength: str
        """
        pass

    @abstractmethod
    def write_waveforms(self) -> None:
        """
        Write output waveforms to the DAQ.
        """
        pass

    @abstractmethod
    def plot_waveforms_to_pdf(self) -> None:
        """
        Plot waveforms and optionally save to a PDF.
        """
        pass

    @abstractmethod
    def start(self) -> None:
        """
        Start all tasks.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """
        Stop all tasks.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close all tasks.
        """
        pass

    @abstractmethod
    def restart(self) -> None:
        """
        Restart all tasks.
        """
        pass

    @abstractmethod
    def wait_until_done_all(self, timeout: float = 1.0) -> None:
        """
        Wait until all tasks are done.

        :param timeout: Timeout in seconds, defaults to 1.0
        :type timeout: float, optional
        """
        pass

    @abstractmethod
    def is_finished_all(self) -> bool:
        """
        Check if all tasks are finished.

        :return: True if all tasks are finished, False otherwise
        :rtype: bool
        """
        pass
