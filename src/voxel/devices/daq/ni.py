import logging
from typing import Dict, Optional

import nidaqmx
import numpy as np
from nidaqmx.constants import AcquisitionType as AcqType
from nidaqmx.constants import AOIdleOutputBehavior, Edge, FrequencyUnits, Level, Slope

from voxel.devices.daq.base import BaseDAQ

TRIGGER_MODE = ["on", "off"]

SAMPLE_MODE = {"finite": AcqType.FINITE, "continuous": AcqType.CONTINUOUS}

TRIGGER_POLARITY = {"rising": Edge.RISING, "falling": Edge.FALLING}

TRIGGER_EDGE = {
    "rising": Slope.RISING,
    "falling": Slope.FALLING,
}

RETRIGGERABLE = {"on": True, "off": False}


class NIDAQ(BaseDAQ):
    """DAQ class for handling NI DAQ devices."""

    def __init__(self, dev: str) -> None:
        """
        Initialize the DAQ object.

        :param dev: Device name
        :type dev: str
        :raises ValueError: If the device name is not found in the system
        """
        self.do_task: Optional[nidaqmx.Task] = None
        self.ao_task: Optional[nidaqmx.Task] = None
        self.co_task: Optional[nidaqmx.Task] = None
        self._tasks: Optional[Dict[str, dict]] = None

        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.devs = list()
        for device in nidaqmx.system.System.local().devices:
            self.devs.append(device.name)
        if dev not in self.devs:
            raise ValueError("dev name must be one of %r." % self.devs)
        self.id = dev
        self.dev = nidaqmx.system.device.Device(self.id)
        self.log.info("resetting nidaq")
        self.dev.reset_device()
        self.ao_physical_chans = self.dev.ao_physical_chans.channel_names
        self.co_physical_chans = self.dev.co_physical_chans.channel_names
        self.do_physical_chans = self.dev.do_ports.channel_names
        self.dio_ports = [channel.replace("port", "PFI") for channel in self.dev.do_ports.channel_names]
        self.dio_lines = self.dev.di_lines.channel_names
        self.max_ao_rate = self.dev.ao_max_rate
        self.min_ao_rate = self.dev.ao_min_rate
        self.max_do_rate = self.dev.do_max_rate
        self.max_ao_volts = self.dev.ao_voltage_rngs[1]
        self.min_ao_volts = self.dev.ao_voltage_rngs[0]
        self.task_time_s = dict()
        self.ao_waveforms = dict()
        self.do_waveforms = dict()

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
        daq_task = nidaqmx.Task(task["name"])
        timing = task["timing"]

        for k, v in timing.items():
            global_var = globals().get(k.upper(), {})
            valid = list(global_var.keys()) if type(global_var) == dict else global_var
            if v not in valid and valid != []:
                raise ValueError(f"{k} must be one of {valid}")

        channel_options = {"ao": self.ao_physical_chans, "do": self.do_physical_chans, "co": self.co_physical_chans}
        add_task_options = {"ao": daq_task.ao_channels.add_ao_voltage_chan, "do": daq_task.do_channels.add_do_chan}

        if task_type in ["ao", "do"]:
            self._timing_checks(task_type)

            trigger_port = timing["trigger_port"]

            for name, specs in task["ports"].items():
                # add channel to task
                channel_port = specs["port"]
                if f"{self.id}/{channel_port}" not in channel_options[task_type]:
                    raise ValueError(f"{task_type} number must be one of {channel_options[task_type]}")
                physical_name = f"/{self.id}/{channel_port}"
                channel = add_task_options[task_type](physical_name)
                # maintain last voltage value
                if task_type == "ao":
                    try:
                        channel.ao_idle_output_behavior = AOIdleOutputBehavior.ZERO_VOLTS
                    except Exception as e:
                        self.log.debug(
                            "could not set AOIdleOutputBehavior to MAINTAIN_EXISTING_VALUE "
                            f"on channel {physical_name} for {channel}."
                        )

            total_time_ms = timing["period_time_ms"] + timing["rest_time_ms"]
            daq_samples = int(((total_time_ms) / 1000) * timing["sampling_frequency_hz"])

            if timing["trigger_mode"] == "on":
                daq_task.timing.cfg_samp_clk_timing(
                    rate=timing["sampling_frequency_hz"],
                    active_edge=TRIGGER_POLARITY[timing["trigger_polarity"]],
                    sample_mode=SAMPLE_MODE[timing["sample_mode"]],
                    samps_per_chan=daq_samples,
                )
                daq_task.triggers.start_trigger.cfg_dig_edge_start_trig(
                    trigger_source=f"/{self.id}/{trigger_port}", trigger_edge=TRIGGER_EDGE[timing["trigger_polarity"]]
                )
                daq_task.triggers.start_trigger.retriggerable = RETRIGGERABLE[timing["retriggerable"]]
            else:
                daq_task.timing.cfg_samp_clk_timing(
                    rate=timing["sampling_frequency_hz"],
                    sample_mode=SAMPLE_MODE[timing["sample_mode"]],
                    samps_per_chan=int((timing["period_time_ms"] / 1000) / timing["sampling_frequency_hz"]),
                )

            setattr(daq_task, f"{task_type}_line_states_done_state", Level.LOW)
            setattr(daq_task, f"{task_type}_line_states_paused_state", Level.LOW)

            # store the total task time
            self.task_time_s[task["name"]] = total_time_ms / 1000

        else:  # co channel

            if timing["frequency_hz"] < 0:
                raise ValueError("frequency must be >0 Hz")

            for channel_number in task["counters"]:
                if f"{self.id}/{channel_number}" not in self.co_physical_chans:
                    raise ValueError("co number must be one of %r." % self.co_physical_chans)
                physical_name = f"/{self.id}/{channel_number}"
                co_chan = daq_task.co_channels.add_co_pulse_chan_freq(
                    counter=physical_name, units=FrequencyUnits.HZ, freq=timing["frequency_hz"], duty_cycle=0.5
                )
                co_chan.co_pulse_term = f'/{self.id}/{timing["output_port"]}'
                pulse_count = (
                    {"sample_mode": AcqType.FINITE, "samps_per_chan": pulse_count}
                    if pulse_count is not None
                    else {"sample_mode": AcqType.CONTINUOUS}
                )
            if timing["trigger_mode"] == "off":
                daq_task.timing.cfg_implicit_timing(**pulse_count)
            else:
                raise ValueError(f"triggering not support for counter output tasks.")

            # store the total task time
            self.task_time_s[task["name"]] = 1 / timing["frequency_hz"]
            setattr(self, f"{task_type}_frequency_hz", timing["frequency_hz"])

        setattr(self, f"{task_type}_task", daq_task)  # set task attribute

    def write_ao_waveforms(self, rereserve_buffer: bool = True) -> None:
        """
        Write analog output waveforms to the DAQ.

        :param rereserve_buffer: Whether to re-reserve the buffer, defaults to True
        :type rereserve_buffer: bool, optional
        """
        ao_voltages = np.array(list(self.ao_waveforms.values()))
        self.ao_task.write(np.array(ao_voltages))

    def write_do_waveforms(self, rereserve_buffer: bool = True) -> None:
        """
        Write digital output waveforms to the DAQ.

        :param rereserve_buffer: Whether to re-reserve the buffer, defaults to True
        :type rereserve_buffer: bool, optional
        """
        do_voltages = np.array(list(self.do_waveforms.values()))
        do_voltages = do_voltages.astype("uint32")[0] if len(do_voltages) == 1 else do_voltages.astype("uint32")
        self.do_task.write(do_voltages)

    def start(self) -> None:
        """
        Start all tasks.
        """
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                task.start()

    def stop(self) -> None:
        """
        Stop all tasks.
        """
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                task.stop()

    def close(self) -> None:
        """
        Close all tasks.
        """
        self.log.info("closing daq.")
        for task in [self.ao_task, self.do_task, self.co_task]:
            if task is not None:
                task.close()

    def restart(self) -> None:
        """
        Restart all tasks.
        """
        self.stop()
        self.start()

    def wait_until_done_all(self, timeout: float = 10.0) -> None:
        """
        Wait until all tasks are done.

        :param timeout: Timeout in seconds, defaults to 10.0
        :type timeout: float, optional
        """
        for task in [self.ao_task, self.do_task]:
            if task is not None:
                task.wait_until_done(timeout)

    def is_finished_all(self) -> bool:
        """
        Check if all tasks are finished.

        :return: True if all tasks are finished, False otherwise
        :rtype: bool
        """
        for task in [self.ao_task, self.do_task]:
            if task is not None:
                if not task.is_task_done():
                    return False
            else:
                pass
        return True
