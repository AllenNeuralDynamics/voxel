import logging
from typing import Dict, Optional

from voxel.devices.daq.base import BaseDAQ

# lets just simulate the PCIe-6738

MAX_AO_RATE_HZ = 350e3
MIN_AO_RATE_HZ = 1e3
MAX_DO_RATE_HZ = 350e3
MAX_AO_VOLTS = 10
MIN_AO_VOLTS = -10

AO_PHYSICAL_CHANS = [
    "ao0",
    "ao1",
    "ao2",
    "ao3",
    "ao4",
    "ao5",
    "ao6",
    "ao7",
    "ao8",
    "ao9",
    "ao10",
    "ao11",
    "ao12",
    "ao13",
    "ao14",
    "ao15",
    "ao16",
    "ao17",
    "ao18",
    "ao19",
    "ao20",
    "ao21",
    "ao22",
    "ao23",
    "ao24",
    "ao25",
    "ao26",
    "ao27",
    "ao28",
    "ao29",
    "ao30",
    "ao31",
]

CO_PHYSICAL_CHANS = ["ctr0", "ctr1"]

DO_PHYSICAL_CHANS = ["port0", "port1"]

DIO_PORTS = ["PFI0", "PFI1"]


class SimulatedDAQ(BaseDAQ):
    """DAQ class for handling simulated DAQ devices."""

    def __init__(self, dev: str) -> None:
        """
        Initialize the DAQ object.

        :param dev: Device name
        :type dev: str
        """
        self.do_task: Optional[dict] = None
        self.ao_task: Optional[dict] = None
        self.co_task: Optional[dict] = None
        self._tasks: Optional[Dict[str, dict]] = None

        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.id = dev
        self.ao_physical_chans = list()
        self.co_physical_chans = list()
        self.do_physical_chans = list()
        self.dio_ports = list()
        for channel in AO_PHYSICAL_CHANS:
            self.ao_physical_chans.append(f"{self.id}/{channel}")
        for channel in CO_PHYSICAL_CHANS:
            self.co_physical_chans.append(f"{self.id}/{channel}")
        for channel in DO_PHYSICAL_CHANS:
            self.do_physical_chans.append(f"{self.id}/{channel}")
        for port in DIO_PORTS:
            self.dio_ports.append(f"{self.id}/{port}")
        self.max_ao_rate = MAX_AO_RATE_HZ
        self.min_ao_rate = MIN_AO_RATE_HZ
        self.max_do_rate = MAX_DO_RATE_HZ
        self.max_ao_volts = MAX_AO_VOLTS
        self.min_ao_volts = MIN_AO_VOLTS
        self.log.info("resetting nidaq")
        self.task_time_s = dict()
        self.ao_waveforms = dict()
        self.do_waveforms = dict()
        self.ao_total_time_ms = 0
        self.do_total_time_ms = 0

    def add_task(self, task_type: str, pulse_count: Optional[int] = None) -> None:
        """
        Add a task to the DAQ.

        :param task_type: Type of the task ('ao', 'co', 'do')
        :type task_type: str
        :param pulse_count: Number of pulses for the task, defaults to None
        :type pulse_count: int, optional
        :raises ValueError: If the task type is invalid or if any parameter is out of range
        """
        # check task type
        if task_type not in ["ao", "co", "do"]:
            raise ValueError(f"{task_type} must be one of {['ao', 'co', 'do']}")

        task = self.tasks[f"{task_type}_task"]

        if old_task := getattr(self, f"{task_type}_task", False):
            old_task.close()  # close old task
            delattr(self, f"{task_type}_task")  # Delete previously configured tasks
        timing = task["timing"]

        for k, v in timing.items():
            global_var = globals().get(k.upper(), {})
            valid = list(global_var.keys()) if type(global_var) == dict else global_var
            if v not in valid and valid != []:
                raise ValueError(f"{k} must be one of {valid}")

        channel_options = {"ao": self.ao_physical_chans, "do": self.do_physical_chans, "co": self.co_physical_chans}

        if task_type in ["ao", "do"]:
            self._timing_checks(task_type)

            for port, specs in task["ports"].items():
                # add channel to task
                channel_port = specs["port"]
                if f"{self.id}/{channel_port}" not in channel_options[task_type]:
                    raise ValueError(f"{task_type} number must be one of {channel_options[task_type]}")

            total_time_ms = timing["period_time_ms"] + timing["rest_time_ms"]

            if timing["trigger_mode"] == "on":
                pass
            else:
                pass

            # store the total task time
            self.task_time_s[task["name"]] = total_time_ms / 1000

        else:  # co channel

            if timing["frequency_hz"] < 0:
                raise ValueError(f"frequency must be >0 Hz")

            for channel_number in task["counters"]:
                if f"{self.id}/{channel_number}" not in self.co_physical_chans:
                    raise ValueError("co number must be one of %r." % self.co_physical_chans)
            if timing["trigger_mode"] == "off":
                pass
            else:
                raise ValueError("triggering not support for counter output tasks.")

            # store the total task time
            self.task_time_s[task["name"]] = 1 / timing["frequency_hz"]
            setattr(self, f"{task_type}_frequency_hz", timing["frequency_hz"])

        setattr(self, f"{task_type}_task", SimulatedTask())  # set task attribute

    def write_ao_waveforms(self, rereserve_buffer: bool = True) -> None:
        """
        Write analog output waveforms to the DAQ.

        :param rereserve_buffer: Whether to re-reserve the buffer, defaults to True
        :type rereserve_buffer: bool, optional
        """
        pass

    def write_do_waveforms(self, rereserve_buffer: bool = True) -> None:
        """
        Write digital output waveforms to the DAQ.

        :param rereserve_buffer: Whether to re-reserve the buffer, defaults to True
        :type rereserve_buffer: bool, optional
        """
        pass

    def start(self) -> None:
        """
        Start all tasks.
        """
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                pass

    def stop(self) -> None:
        """
        Stop all tasks.
        """
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                pass

    def close(self) -> None:
        """
        Close all tasks.
        """
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                pass

    def restart(self) -> None:
        """
        Restart all tasks.
        """
        self.stop()
        self.start()

    def wait_until_done_all(self, timeout: float = 1.0) -> None:
        """
        Wait until all tasks are done.

        :param timeout: Timeout in seconds, defaults to 1.0
        :type timeout: float, optional
        """
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                task.wait_until_done(timeout)

    def is_finished_all(self) -> bool:
        """
        Check if all tasks are finished.

        :return: True if all tasks are finished, False otherwise
        :rtype: bool
        """
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                if not task.is_task_done():
                    return False
            else:
                pass
        return True


class SimulatedTask:

    def start(self) -> None:
        """
        Start the task.
        """
        pass

    def stop(self) -> None:
        """
        Stop the task.
        """
        pass

    def close(self) -> None:
        """
        Close the task.
        """
        pass

    def restart(self) -> None:
        """
        Restart the task.
        """
        self.stop()
        self.start()
