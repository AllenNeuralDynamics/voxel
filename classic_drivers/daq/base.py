from abc import abstractmethod

from voxel_classic.devices.base import VoxelDevice


class BaseDAQ(VoxelDevice):
    """Base class for DAQ devices."""

    @abstractmethod
    def add_task(self, task_type: str, pulse_count: int | None = None) -> None:
        """
        Add a task to the DAQ.

        :param task_type: Type of the task ('ao', 'co', 'do')
        :type task_type: str
        :param pulse_count: Number of pulses for the task, defaults to None
        :type pulse_count: int, optional
        """
        pass

    @abstractmethod
    def generate_waveforms(self, task_type: str, wavelength: str) -> None:
        """
        Generate waveforms for the task.

        :param task_type: Type of the task ('ao', 'do')
        :type task_type: str
        :param wavelength: Wavelength for the waveform
        :type wavelength: str
        """
        pass

    @abstractmethod
    def write_ao_waveforms(self) -> None:
        """
        Write analog output waveforms to the DAQ.
        """
        pass

    @abstractmethod
    def write_do_waveforms(self) -> None:
        """
        Write digital output waveforms to the DAQ.
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
