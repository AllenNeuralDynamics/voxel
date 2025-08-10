import copy
import math
import os
import platform
import shutil
import subprocess
import threading
import time
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from threading import Event, Lock
from typing import TYPE_CHECKING, Any

import inflection
import numpy
from gputools import get_device
from psutil import virtual_memory
from ruamel.yaml import YAML
from voxel_classic.acquisition.acquisition import Acquisition
from voxel_classic.instruments.instrument import Instrument
from voxel_classic.writers.data_structures.shared_double_buffer import SharedDoubleBuffer

if TYPE_CHECKING:
    from voxel_classic.devices.camera.base import BaseCamera
    from voxel_classic.writers.base import BaseWriter

DIRECTORY = Path(__file__).parent.resolve()


class ExASPIMAcquisition(Acquisition):
    """Class for handling ExASPIM acquisition."""

    def __init__(self, instrument: Instrument, config_filename: str | Path, yaml_handler: YAML, log_level="INFO"):
        """
        Initialize the ExASPIMAcquisition object.

        :param instrument: Instrument object
        :type instrument: Instrument
        :param config_filename: Configuration filename
        :type config_filename: str
        :param yaml_handler: YAML handler
        :type yaml_handler: YAML
        :param log_level: Logging level, defaults to "INFO"
        :type log_level: str, optional
        """
        super().__init__(instrument, DIRECTORY / Path(config_filename), yaml_handler, log_level)

        # initialize stop engine event
        self.stop_engine = Event()
        # store initial stage positions
        self.initial_position_mm = {}

    def run(self) -> None:
        """
        Run the acquisition process.

        :raises ValueError: If there is not enough local disk space.
        """
        # verify acquisition
        self._verify_acquisition()

        # set acquisition name
        self._set_acquisition_name()

        # create directories
        self._create_directories()

        # initialize threads and buffers
        file_transfer_threads = {}

        # store devices and routines
        try:
            camera_name, self.camera = next(iter(self.instrument.cameras.items()))  # only 1 camera for exaspim
        except StopIteration as e:
            raise RuntimeError(f"No cameras found for instrument {self.instrument}. Error: {e}")

        try:
            camera_writers = self.writers.get(camera_name, {})
            self.writer = next(iter(camera_writers.values()))  # only 1 writer for exaspim
        except (AttributeError, StopIteration) as e:
            raise RuntimeError(f"No writers found for camera {camera_name}. Error: {e}")

        camera_file_transfers = self.file_transfers.get(camera_name, {})
        file_transfer = next(iter(camera_file_transfers.values())) if camera_file_transfers else {}

        self.scanning_stage = next(iter(self.instrument.scanning_stages.values()))  # only 1 scanning stage for exaspim
        self.daq = next(iter(self.instrument.daqs.values()))  # only 1 daq for exaspim
        # only 1 indicator light for exaspim
        self.indicator_light = (
            next(iter(self.instrument.indicator_lights.values())) if self.instrument.indicator_lights else None
        )

        # processes could be > so leave as a dictionary
        self.processes = self.processes[camera_name] if self.processes else {}

        # tiling stages
        for tiling_stage_id, tiling_stage in self.instrument.tiling_stages.items():
            instrument_axis = tiling_stage.instrument_axis
            self.initial_position_mm[instrument_axis] = tiling_stage.position_mm
        # scanning stage
        instrument_axis = self.scanning_stage.instrument_axis
        self.initial_position_mm[instrument_axis] = self.scanning_stage.position_mm

        # turn on indicator light
        if self.indicator_light is not None:
            self.log.info("turning on indicator light")
            self.indicator_light.enable()
        for tile in self.config["acquisition"]["tiles"]:
            # number of times to repeat tile -> pulled from GUI only make sure in gui.yaml file
            if tile["repeats"] < 0:
                self.log.warning("skipping tile with <0 repeats")
            else:
                for repeat in range(tile["repeats"]):
                    # wait for start delay -> pulled from GUI only make sure in gui.yaml file
                    start_delay = tile["start_delay"]
                    self.log.info(f"waiting for start delay = {start_delay} [s]")
                    time.sleep(tile["start_delay"])

                    tile_num = tile["tile_number"]

                    tile_channel = tile["channel"]
                    tile_prefix = tile["prefix"]
                    if repeat > 0:
                        base_filename = f"{tile_prefix}_{tile_num:06}_ch_{tile_channel}_repeat_{repeat}"
                    else:
                        base_filename = f"{tile_prefix}_{tile_num:06}_ch_{tile_channel}"

                    self.log.info(f"starting tile {base_filename}")

                    # check length of scan
                    round_z_mm = int(tile["round_z_mm"])
                    if (
                        tile["steps"] % round_z_mm != 0
                    ):  # must be divisible by round_z_mm for direct use of IMS pyramid volumes
                        tile_count_px = round_z_mm * math.ceil(tile["steps"] / round_z_mm)
                        tile["steps"] = tile_count_px
                        self.log.info(
                            f"adjusting tile frame count to be divisible by {round_z_mm} -> {tile_count_px} [px]"
                        )

                    # move all tiling stages to correct positions
                    for tiling_stage_id, tiling_stage in self.instrument.tiling_stages.items():
                        # grab stage axis letter
                        instrument_axis = tiling_stage.instrument_axis
                        tile_position = tile["position_mm"][instrument_axis]
                        self.log.info(f"moving stage {tiling_stage_id} to {instrument_axis} = {tile_position:.3f} mm")
                        tiling_stage.move_absolute_mm(tile_position, wait=False)
                        time.sleep(1.0)  # wait one second before polling moving status
                        # wait on tiling stage
                        while tiling_stage.is_axis_moving():
                            self.log.info(
                                f"waiting for stage {tiling_stage_id}: {instrument_axis} ="
                                f"{tiling_stage.position_mm:.3f} -> {tile_position:.3f} mm"
                            )
                            time.sleep(1.0)

                    # prepare the scanning stage for step and shoot behavior
                    self.log.info("setting up scanning stage")
                    instrument_axis = self.scanning_stage.instrument_axis
                    tile_position = tile["position_mm"][instrument_axis]
                    backlash_removal_position = tile_position - 0.01
                    self.log.info(f"moving scanning stage to {instrument_axis} = {backlash_removal_position:.3f} mm")
                    self.scanning_stage.move_absolute_mm(tile_position - 0.01, wait=False)
                    self.log.info(f"moving stage to {instrument_axis} = {tile_position:.3f} mm")
                    self.scanning_stage.move_absolute_mm(tile_position, wait=False)
                    self.log.info("backlash on scanning stage removed")
                    step_size_um = tile["step_size"]
                    self.log.info(f"setting step shoot scan step size to {step_size_um} um")
                    self.scanning_stage.setup_step_shoot_scan(step_size_um)
                    time.sleep(1.0)  # wait one second before polling moving status
                    # wait on scanning stage
                    while self.scanning_stage.is_axis_moving():
                        self.log.info(
                            f"waiting for scanning stage: {instrument_axis} = "
                            f"{self.scanning_stage.position_mm} -> {tile_position:.3f} mm"
                        )

                    # check disable scanning stage stepping
                    if tile["disable_scanning"] == "on":
                        self.log.info("disabling scanning stage stepping")
                        self.scanning_stage.mode = "off"  # turn off step and shoot mode

                    # setup channel i.e. laser and filter wheels
                    self.log.info(f"setting up channel: {tile_channel}")
                    channel = self.instrument.channels[tile_channel]
                    for device_type, devices in channel.items():
                        for device_name in devices:
                            device = getattr(self.instrument, device_type)[device_name]
                            if device_type in ["lasers", "filters"]:
                                self.log.info(f"{device_type} {device_name} enabled")
                                device.enable()
                            for setting, value in tile.get(device_name, {}).items():
                                self.log.info(f"setting {setting} for {device_type} {device_name} to {value}")
                                setattr(device, setting, value)
                                self.log.info(f"{setting} for {device_type} {device_name} set to {value}")

                    if not self.daq.tasks:  # make sure daq tasks are defined
                        raise RuntimeError("No DAQ tasks found.")

                    # update etl offsets if in channel plan table
                    if "etl_left_offset" in tile and tile["etl_left_offset"] is not None:
                        self.daq.tasks["ao_task"]["ports"]["left tunable lens"]["parameters"]["offset_volts"][
                            "channels"
                        ][tile_channel] = tile["etl_left_offset"]
                    if "etl_right_offset" in tile and tile["etl_right_offset"] is not None:
                        self.daq.tasks["ao_task"]["ports"]["right tunable lens"]["parameters"]["offset_volts"][
                            "channels"
                        ][tile_channel] = tile["etl_right_offset"]

                    # setup daq
                    time.sleep(1.0)
                    self.log.info("setting up daq")
                    if self.daq.tasks.get("ao_task", None) is not None:
                        self.log.info("adding ao task")
                        self.daq.add_task("ao")
                        self.log.info("generating ao waveforms")
                        self.daq.generate_waveforms("ao", tile_channel)
                        self.log.info("writing ao waveforms")
                        self.daq.write_ao_waveforms()
                    if self.daq.tasks.get("do_task", None) is not None:
                        self.daq.add_task("do")
                        self.daq.generate_waveforms("do", tile_channel)
                        self.daq.write_do_waveforms()
                    if self.daq.tasks.get("co_task", None) is not None:
                        pulse_count = (
                            self.writer.chunk_count_px
                        )  # number of pulses matched to number of frames in a chunk
                        self.daq.add_task("co", pulse_count)

                    # log daq values
                    for name, port_values in self.daq.tasks["ao_task"]["ports"].items():
                        parameters = port_values["parameters"]
                        port = port_values["port"]
                        for parameter, channel_values in parameters.items():
                            daq_value = channel_values["channels"][tile_channel]
                            self.log.info(f"{name} on {port}: {parameter} = {daq_value}")

                    # run any pre-routines for all devices
                    for device_name, routine_dictionary in getattr(self, "routines", {}).items():
                        device_type = self.instrument.config["instrument"]["devices"][device_name]["type"]
                        self.log.info(f"running routines for {device_type} {device_name}")
                        for routine_name, routine in routine_dictionary.items():
                            device_object = getattr(self.instrument, inflection.pluralize(device_type))[device_name]
                            routine.filename = base_filename + "_" + routine_name
                            routine.start(device=device_object)

                    # setup writers
                    self.log.info("setting up writer")
                    self.writer.row_count_px = self.camera.image_height_px
                    self.writer.column_count_px = self.camera.image_width_px
                    self.writer.frame_count_px = tile["steps"]
                    self.writer.x_position_mm = tile["position_mm"]["x"]
                    self.writer.y_position_mm = tile["position_mm"]["y"]
                    self.writer.z_position_mm = tile["position_mm"]["z"]
                    self.writer.x_voxel_size_um = self.camera.sampling_um_px
                    self.writer.y_voxel_size_um = self.camera.sampling_um_px
                    self.writer.z_voxel_size_um = tile["step_size"]
                    self.writer.filename = base_filename
                    self.writer.channel = tile["channel"]

                    if tile["prechecks"] == "on":
                        # estimate the compresion ratio
                        compression_ratio = self.check_compression_ratio(self.camera, self.writer)
                        # check write speed
                        if file_transfer:
                            self.check_write_speed(
                                daq=self.daq,
                                writer=self.writer,
                                file_transfer=file_transfer,
                                compression_ratio=compression_ratio,
                            )
                        else:
                            self.check_write_speed(
                                daq=self.daq, writer=self.writer, compression_ratio=compression_ratio
                            )
                        # check local memory
                        self.check_system_memory(self.writer)
                        # check gpu memory
                        self.check_gpu_memory(self.writer)
                    else:
                        compression_ratio = 1.0

                    # check local disk space and run if enough disk space
                    # check external disk space
                    if file_transfer:
                        while not self.check_external_disk_space(self.writer, file_transfer, compression_ratio):
                            # recheck external disk space every minute, if not enough space, do not run
                            time.sleep(60)
                    # check local disk space and run if enough disk space
                    if self.check_local_disk_space(self.writer, compression_ratio):
                        self.acquisition_engine(
                            tile, base_filename, self.camera, self.daq, self.writer, self.processes, self.scanning_stage
                        )
                    # if not enough local disk space, but file transfers are running
                    # wait for them to finish, because this will free up disk space
                    elif len(file_transfer_threads) != 0:
                        # check if any transfer threads are still running, if so wait on them
                        for tile_num, threads_dict in file_transfer_threads.items():
                            for tile_channel, transfer_thread in threads_dict.items():
                                if transfer_thread.is_alive():
                                    transfer_thread.wait_until_finished()
                    # otherwise this is the first tile and there is simply not enough disk space
                    # for the first tile
                    else:
                        raise ValueError("not enough local disk space")

                    # stop the daq tasks
                    self.log.info("stopping daq")
                    if self.daq.co_task:
                        self.daq.co_task.stop()
                    # sleep to allow last ao to play with 10% buffer
                    time.sleep(1.0 / (self.daq.co_frequency_hz or 1) * 1.1)
                    # stop the ao task
                    if self.daq.ao_task:
                        self.daq.ao_task.stop()
                    self.daq.close()

                    # create and start transfer threads from previous tile
                    if file_transfer:
                        if tile_num not in file_transfer_threads:
                            file_transfer_threads[tile_num] = {}
                        if tile_channel not in file_transfer_threads[tile_num]:
                            file_transfer_threads[tile_num][tile_channel] = {}
                        file_transfer_threads[tile_num][tile_channel][repeat] = copy.deepcopy(file_transfer)
                        file_transfer_threads[tile_num][tile_channel][repeat].filename = base_filename
                        self.log.info(f"starting file transfer for {base_filename}")
                        file_transfer_threads[tile_num][tile_channel][repeat].start()

        # wait for last tiles file transfer
        if file_transfer:
            for tile_num, threads_dict in file_transfer_threads.items():
                for tile_channel, repeat_dict in threads_dict.items():
                    for repeat, thread in repeat_dict.items():
                        if thread.is_alive():
                            thread.wait_until_finished()

        if getattr(self, "file_transfers", {}) != {}:  # save to external paths
            # save acquisition config
            for device_name, transfer_dict in getattr(self, "file_transfers", {}).items():
                for transfer in transfer_dict.values():
                    self.update_current_state_config()
                    self.save_config(
                        Path(transfer.external_path, transfer.acquisition_name) / "acquisition_config.yaml"
                    )

            # save instrument config
            for device_name, transfer_dict in getattr(self, "file_transfers", {}).items():
                for transfer in transfer_dict.values():
                    self.instrument.update_current_state_config()
                    self.instrument.save_config(
                        Path(transfer.external_path, transfer.acquisition_name) / "instrument_config.yaml"
                    )

        else:  # no transfers so save locally
            # save acquisition config
            for device_name, writer_dict in self.writers.items():
                for writer in writer_dict.values():
                    self.update_current_state_config()
                    self.save_config(Path(writer.path, writer.acquisition_name) / "acquisition_config.yaml")

            # save instrument config
            for device_name, writer_dict in self.writers.items():
                for writer in writer_dict.values():
                    self.instrument.update_current_state_config()
                    self.instrument.save_config(Path(writer.path, writer.acquisition_name) / "instrument_config.yaml")

        # return to initial stage positions
        # tiling stages
        for tiling_stage_id, tiling_stage in self.instrument.tiling_stages.items():
            instrument_axis = tiling_stage.instrument_axis
            tiling_stage.position_mm = self.initial_position_mm[instrument_axis]
            self.log.info(
                f"moving stage {tiling_stage_id} to {instrument_axis} = {self.initial_position_mm[instrument_axis]:.3f} mm"
            )
        # scanning stage
        instrument_axis = self.scanning_stage.instrument_axis
        self.scanning_stage.position_mm = self.initial_position_mm[instrument_axis]
        self.log.info(f"moving stage to {instrument_axis} = {self.initial_position_mm[instrument_axis]:.3f} mm")

        # turn off indicator light
        if self.indicator_light:
            self.log.info("turning off indicator light")
            self.indicator_light.disable()

    def acquisition_engine(
        self, tile: dict, base_filename: str, camera, daq, writer, processes: dict, scanning_stage
    ) -> None:
        """
        Run the acquisition engine.

        :param tile: Tile configuration
        :type tile: dict
        :param base_filename: Base filename for the acquisition
        :type base_filename: str
        :param camera: Camera object
        :type camera: Camera
        :param daq: Data acquisition object
        :type daq: DAQ
        :param writer: Writer object
        :type writer: Writer
        :param processes: Dictionary of processes
        :type processes: dict
        :param scanning_stage: Scanning stage object
        :type scanning_stage: ScanningStage
        """
        # initatlized shared double buffer and processes
        self.log.info("setting up buffers")
        process_buffers = {}
        chunk_lock = Lock()
        img_buffer = SharedDoubleBuffer(
            (writer.chunk_count_px, camera.image_height_px, camera.image_width_px),
            dtype=writer.data_type,
        )

        # setup processes
        self.log.info("setting up processes")
        for process_name, process in processes.items():
            process.row_count_px = camera.image_height_px
            process.column_count_px = camera.image_width_px
            process.binning = camera.binning
            process.frame_count_px = tile["steps"]
            process.filename = base_filename
            img_bytes = (
                numpy.prod(camera.image_height_px * camera.image_width_px) * numpy.dtype(process.data_type).itemsize
            )
            buffer = SharedMemory(create=True, size=int(img_bytes))
            process_buffers[process_name] = buffer
            process.buffer_image = numpy.ndarray(
                (camera.image_height_px, camera.image_width_px),
                dtype=process.data_type,
                buffer=buffer.buf,
            )
            process.prepare(buffer.name)

        # set up writer and camera
        camera.prepare()
        writer.prepare()
        writer.start()
        time.sleep(1)

        # start camera and set frame number to 0
        camera.frame_number = 0
        camera.start()

        # start processes
        for process in processes.values():
            process.start()

        last_frame_index = tile["steps"] - 1

        # Images arrive serialized in repeating channel order.
        for frame_index in range(tile["steps"]):
            if self.stop_engine.is_set():
                break
            chunk_index = frame_index % writer.chunk_count_px
            # Start a batch of pulses to generate more frames and movements.
            if chunk_index == 0:
                # log metrics from devices
                laser_name = self.instrument.channels[tile["channel"]]["lasers"][0]
                laser = self.instrument.lasers[laser_name]
                memory_info = virtual_memory()
                self.log.info(f"RAM in use = {memory_info.used / (1024**3):.2f} GB")
                self.log.info(f"laser {laser.id} power = {laser.power_mw:.2f} [mW]")
                self.log.info(f"laser {laser.id} temperature = {laser.temperature_c:.2f} [mW]")
                # self.log.info(f"camera {camera.id} sensor temperature = {camera.sensor_temperature_c:.2f} [C]")
                # self.log.info(f"camera {camera.id} mainboard temperature = {camera.mainboard_temperature_c:.2f} [C]")
                # try:
                #     temperature_sensor, _ = self._grab_first(self.instrument.temperature_sensors)
                #     self.log.info(
                #         f"sensor {temperature_sensor.id} temperature = {temperature_sensor.temperature_c:.2f} [C]"
                #     )
                #     self.log.info(
                #         f"sensor {temperature_sensor.id} humidity = {temperature_sensor.relative_humidity_percent:.2f} [%]"
                #     )
                # except Exception:
                #     self.log.info("no temperature humidity sensor detected")

                # start the camera
                camera.stop()
                camera.prepare()
                camera.start()

                # Start the daq tasks.
                self.log.info("starting daq")
                for task in [daq.ao_task, daq.do_task, daq.co_task]:  # must start co task last in list
                    if task is not None:
                        task.start()

            # Grab camera frame and add to shared double buffer.
            current_frame = camera.grab_frame()
            img_buffer.add_image(current_frame)

            # Log the current state of the camera.
            camera.acquisition_state()

            # Log the current state of the writer.
            while not writer._log_queue.empty():
                self.log.info(f"writer: {writer._log_queue.get_nowait()}")

            # Dispatch either a full chunk of frames or the last chunk,
            # which may not be a multiple of the chunk size.
            if chunk_index + 1 == writer.chunk_count_px or frame_index == last_frame_index:
                daq.stop()
                # Toggle double buffer to continue writing images.
                while not writer.done_reading.is_set() and not self.stop_engine.is_set():
                    time.sleep(0.001)
                with chunk_lock:
                    img_buffer.toggle_buffers()
                    writer.shm_name = img_buffer.read_buf_mem_name
                    writer.done_reading.clear()

            # check on processes
            for process in processes.values():
                while process.new_image.is_set():
                    time.sleep(0.1)
                process.buffer_image[:, :] = current_frame
                process.new_image.set()

            frame_index += 1

        if self.stop_engine.is_set():
            # wait for daq tasks to finish - prevents devices from stopping in
            # unsafe state, i.e. lasers still on
            self.log.info("stopping daq")
            if self.daq.co_task:
                self.daq.co_task.stop()
            else:
                self.log.warning("Could not stop CO task because it is not running")
            # sleep to allow last ao to play with 10% buffer
            time.sleep(1.0 / (self.daq.co_frequency_hz or 1) * 1.1)
            # stop the ao task
            if self.daq.ao_task:
                self.daq.ao_task.stop()
            else:
                self.log.warning("Could not stop AO task because it is not running")
            self.daq.close()
            self.log.info("stopping scanning stage")
            self.scanning_stage.halt()
            self.log.info("stopping camera")
            self.camera.abort()
            # need to directly terminate writer process
            self.log.info("stopping writer")
            self.writer._process.terminate() if self.writer._process else None
            self.stop_engine.clear()
        else:
            # stop the camera and set frame number back to 0
            camera.stop()
            camera.frame_number = 0

            # wait for the writer to finish
            writer.wait_to_finish()

            # stop the daq
            self.log.info("stopping daq")
            daq.stop()

            # disable scanning stage stepping
            scanning_stage.mode = "off"  # turn off step and shoot mode

            # log any statements in the writer log queue
            while not writer._log_queue.empty():
                self.log.info(writer._log_queue.get_nowait())

            # wait for the processes to finish
            for process in processes.values():
                process.wait_to_finish()

            # clean up the image buffer
            self.log.info("deallocating shared double buffer.")
            img_buffer.close_and_unlink()
            del img_buffer
            for buffer in process_buffers.values():
                buffer.close()
                buffer.unlink()
                del buffer

    def stop_acquisition(self) -> None:
        """
        Stop acquisition.
        """
        self.log.info("stopping acquisition")
        self.stop_engine.set()

    def _get_drive(self, path: str) -> str:
        """
        Get the drive path for the writer.

        :param writer: Writer object
        :type writer: object
        :return: Drive path
        :rtype: str
        """
        # TODO: for non-windows - not completed, needs to be fixed
        return os.path.splitdrive(path)[0] if platform.system() == "Windows" else "/"

    def check_local_disk_space(self, writer, compression_ratio: float = 1) -> bool:
        """
        Check if there is enough local disk space for the next tile.

        :param writer: Writer object
        :type writer: object
        :param compression_ratio: Compression ratio, defaults to 1
        :type compression_ratio: float, optional
        :return: True if there is enough disk space, False otherwise
        :rtype: bool
        """
        drive = self._get_drive(writer.path)
        self.log.info("checking local storage directory space for next tile")
        required_size_gb = writer.get_stack_size_mb() / compression_ratio / 1024
        self.log.info(f"required disk space = {required_size_gb:.1f} [GB] on drive {drive}")
        free_size_gb = shutil.disk_usage(drive).free / 1024**3
        self.log.info(f"available disk space = {free_size_gb:.1f} [GB] on drive {drive}")
        if required_size_gb >= free_size_gb:
            self.log.warning(f"only {free_size_gb:.1f} available on drive: {drive}")
            return False
        return True

    def check_external_disk_space(self, writer, file_transfer, compression_ratio: float = 1) -> bool:
        """
        Check if there is enough external disk space for the next tile.

        :param writer: Writer object
        :type writer: object
        :param file_transfer: File transfer object
        :type file_transfer: object
        :param compression_ratio: Compression ratio, defaults to 1
        :type compression_ratio: float, optional
        :return: True if there is enough disk space, False otherwise
        :rtype: bool
        """
        drive = self._get_drive(file_transfer.external_path)

        self.log.info("checking external storage directory space for next tile")
        required_size_gb = writer.get_stack_size_mb() / compression_ratio / 1024
        self.log.info(f"required disk space = {required_size_gb:.1f} [GB] on drive {drive}")
        free_size_gb = shutil.disk_usage(drive).free / 1024**3
        self.log.info(f"available disk space = {free_size_gb:.1f} [GB] on drive {drive}")
        if required_size_gb >= free_size_gb:
            self.log.warning(f"only {free_size_gb:.1f} available on drive: {drive}")
            return False
        return True

    def check_system_memory(self, writer) -> None:
        """
        Check if there is enough system memory for the acquisition.

        :param writer: Writer object
        :type writer: object
        :raises MemoryError: If there is not enough system memory
        """
        self.log.info("checking available system memory")
        # factor of 2 for concurrent chunks being written/read
        required_memory_gb = 2 * writer.chunk_count_px * writer.get_frame_size_mb() / 1024
        self.log.info(f"required RAM = {required_memory_gb:.2f} [GB]")
        free_memory_gb = virtual_memory()[1] / 1024**3
        self.log.info(f"available RAM = {free_memory_gb:.2f} [GB]")
        if free_memory_gb < required_memory_gb:
            raise MemoryError("system does not have enough memory to run")

    def check_write_speed(
        self,
        writer: Any,
        daq: Any,
        file_transfer: Any | None = None,
        compression_ratio: float = 1,
        size: str = "16Gb",
        bs: str = "1M",
        direct: int = 1,
        numjobs: int = 1,
        iodepth: int = 1,
        runtime: int = 0,
    ) -> None:
        """
        Check the write speed to local and external directories.

        :param writer: Writer object
        :type writer: object
        :param daq: Data acquisition object
        :type daq: object
        :param file_transfer: File transfer object, defaults to None
        :type file_transfer: object, optional
        :param compression_ratio: Compression ratio, defaults to 1
        :type compression_ratio: float, optional
        :param size: Size of the test file, defaults to "16Gb"
        :type size: str, optional
        :param bs: Block size, defaults to "1M"
        :type bs: str, optional
        :param direct: Direct I/O, defaults to 1
        :type direct: int, optional
        :param numjobs: Number of jobs, defaults to 1
        :type numjobs: int, optional
        :param iodepth: I/O depth, defaults to 1
        :type iodepth: int, optional
        :param runtime: Runtime, defaults to 0
        :type runtime: int, optional
        :raises ValueError: If the write speed is too slow
        :raises ValueError: If the write speed is too slow
        """
        self.log.info("checking write speed to local and external directories")
        # windows ioengine
        if platform.system() == "Windows":
            ioengine = "windowsaio"
            local_drive = os.path.splitdrive(writer.path)[0]
            external_drive = os.path.splitdrive(writer.path)[0] if not file_transfer else None
        # unix ioengine
        else:
            ioengine = "posixaio"
            local_drive = "/"
            external_drive = "/" if file_transfer else None  # TODO: not completed needs to be fixed

        # get the required write speed
        acquisition_rate_hz = 1.0 / daq.co_frequency_hz
        camera_speed_mb_s = writer.get_frame_size_mb() / acquisition_rate_hz
        required_write_speed_mb_s = camera_speed_mb_s / compression_ratio
        self.log.info(f"required write speed = {required_write_speed_mb_s:.1f} [MB/sec] to directory {local_drive}")
        test_filename = str(Path(f"{writer.path}/{writer.acquisition_name}/iotest").absolute())
        with open(test_filename, "a"):
            pass  # Create empty file to check reading/writing speed
        try:
            output = subprocess.check_output(
                rf"fio --name=test --filename={test_filename} --size={size} --rw=write --bs={bs} "
                rf"--direct={direct} --numjobs={numjobs} --ioengine={ioengine} --iodepth={iodepth} "
                rf"--runtime={runtime} --startdelay=0 --thread --group_reporting",
                shell=True,
            )
            out = str(output)
            # converting MiB to MB = (1024**2/2**20)
            available_write_speed_mb_s = round(
                float(out[out.find("BW=") + len("BW=") : out.find("MiB/s")]) / (1024**2 / 2**20)
            )
            self.log.info(
                f"available write speed = {available_write_speed_mb_s:.1f} [MB/sec] to directory {local_drive}"
            )
            if available_write_speed_mb_s < required_write_speed_mb_s:
                raise ValueError(f"write speed too slow on drive {local_drive}")
        except subprocess.CalledProcessError:
            self.log.warning("fio not installed on computer. Cannot verify read/write speed")
        finally:
            # Delete test file
            os.remove(test_filename)
        if file_transfer:
            self.log.info(
                f"required write speed = {required_write_speed_mb_s:.1f} [MB/sec] to directory {external_drive}"
            )
            test_filename = str(
                Path(f"{file_transfer.external_path}/{file_transfer.acquisition_name}/iotest").absolute()
            )
            with open(test_filename, "a"):
                pass  # Create empty file to check reading/writing speed
            try:
                output = subprocess.check_output(
                    rf"fio --name=test --filename={test_filename} --size={size} --rw=write --bs={bs} "
                    rf"--direct={direct} --numjobs={numjobs} --ioengine={ioengine} --iodepth={iodepth} "
                    rf"--runtime={runtime} --startdelay=0 --thread --group_reporting",
                    shell=True,
                )
                out = str(output)
                # converting MiB to MB = (1024**2/2**20)
                available_write_speed_mb_s = round(
                    float(out[out.find("BW=") + len("BW=") : out.find("MiB/s")]) / (1024**2 / 2**20)
                )
                self.log.info(
                    f"available write speed = {available_write_speed_mb_s:.1f} [MB/sec] to directory {external_drive}"
                )
                if available_write_speed_mb_s < required_write_speed_mb_s:
                    raise ValueError(f"write speed too slow on drive {external_drive}")
            except subprocess.CalledProcessError:
                self.log.warning("fio not installed on computer. Cannot verify read/write speed")
            finally:
                # Delete test file
                os.remove(test_filename)

    def check_gpu_memory(self, writer: Any) -> None:
        """
        Check if there is enough GPU memory for the acquisition.

        :param writer: Writer object
        :type writer: object
        :raises ValueError: If there is not enough GPU memory
        """
        # check GPU resources for downscaling
        required_memory_gb = writer.get_frame_size_mb() / 1024
        total_gpu_memory_gb = get_device().get_info("MAX_MEM_ALLOC_SIZE") / 1024**3
        self.log.info(f"required GPU RAM = {required_memory_gb:.1f} [GB]")
        self.log.info(f"available GPU RAM = {total_gpu_memory_gb:.1f} [GB]")
        if required_memory_gb >= total_gpu_memory_gb:
            raise ValueError(
                f"{required_memory_gb} [GB] GPU RAM requested but only {total_gpu_memory_gb} [GB] available"
            )

    def check_compression_ratio(self, camera: "BaseCamera", writer: "BaseWriter") -> float:
        """
        Estimate the compression ratio for the acquisition.

        :param camera: Camera object
        :type camera: object
        :param writer: Writer object
        :type writer: object
        :return: Estimated compression ratio
        :rtype: float
        """
        self.log.info("estimating acquisition compression ratio")
        if writer.compression != "none":
            # store initial trigger mode, frame count, filename
            trigger = camera.trigger
            frame_count_px = writer.frame_count_px
            filename = writer.filename

            # turn trigger off
            trigger["mode"] = "off"
            camera.trigger = trigger
            # prepare the writer
            writer.frame_count_px = writer.chunk_count_px
            writer.filename = "compression_ratio_test"

            chunk_size = writer.chunk_count_px
            chunk_lock = threading.Lock()
            img_buffer = SharedDoubleBuffer(
                (chunk_size, camera.image_height_px, camera.image_width_px), dtype=str(writer.data_type)
            )

            # set up and start writer and camera
            camera.frame_number = 0
            writer.prepare()
            camera.prepare()
            writer.start()
            camera.start()

            for frame_index in range(writer.chunk_count_px):
                # grab camera frame
                current_frame = camera.grab_frame()
                img_buffer.add_image(current_frame)
                # Log the current state of the camera.
                camera.acquisition_state()
            # stop the camera
            camera.stop()

            while not writer.done_reading.is_set():
                time.sleep(0.001)

            with chunk_lock:
                img_buffer.toggle_buffers()
                if writer.path is not None:
                    writer.shm_name = img_buffer.read_buf_mem_name
                    writer.done_reading.clear()

            # close writer
            writer.wait_to_finish()

            # clean up the image buffer
            img_buffer.close_and_unlink()
            del img_buffer

            # check the compressed file size
            filepath = str(Path(writer.path / writer.acquisition_name / writer.filename).absolute())
            compressed_file_size_mb = os.stat(filepath).st_size / (1024**2)
            # calculate the raw file size
            raw_file_size_mb = writer.get_stack_size_mb()
            # calculate the compression ratio
            if raw_file_size_mb := writer.get_stack_size_mb():
                compression_ratio = raw_file_size_mb / compressed_file_size_mb
            else:
                compression_ratio = 1.0
            # delete the files
            writer.delete_files()
            # reset the trigger, frame count, and filename
            trigger["mode"] = "on"
            camera.trigger = trigger
            writer.frame_count_px = frame_count_px
            writer.filename = filename
        else:
            compression_ratio = 1.0
        self.log.info(f"compression ratio is ~ {compression_ratio:.1f}")

        return compression_ratio

    def _setup_class(self, device: object, properties: dict) -> None:
        """
        Overwrite to allow metadata class to pass in acquisition_name to devices that require it.

        :param device: Device object
        :type device: object
        :param properties: Properties dictionary
        :type properties: dict
        """
        super()._setup_class(device, properties)

        # set acquisition_name attribute if it exists for object
        if hasattr(device, "acquisition_name") and self.metadata is not None:
            setattr(device, "acquisition_name", self.metadata.acquisition_name)

    def _grab_first(self, object_dict: dict[str, object]) -> object:
        """
        Grab the first object from a dictionary.

        :param object_dict: Dictionary containing devices
        :type object_dict: dict
        :return: The first device in the dictionary
        :rtype: object
        """
        object_name = list(object_dict.keys())[0]
        return object_dict[object_name], object_name

    def _set_acquisition_name(self) -> None:
        """
        Sets the acquisition name for all operations.
        """
        if self.metadata is None:
            self.log.error("Metadata is not set. Cannot set acquisition name.")
            return
        self.acquisition_name = self.metadata.acquisition_name
        for device_name, operation_dict in self.config["acquisition"]["operations"].items():
            for op_name, op_specs in operation_dict.items():
                op_type = inflection.pluralize(op_specs["type"])
                operation = getattr(self, op_type)[device_name][op_name]
                if hasattr(operation, "acquisition_name"):
                    setattr(operation, "acquisition_name", self.acquisition_name)

    def _create_directories(self) -> None:
        """
        Creates necessary directories for acquisition.
        """
        self.log.info("creating local and external directories")

        # check if local directories exist and create if not
        for writer_dictionary in self.writers.values():
            for writer in writer_dictionary.values():
                if self.acquisition_name:
                    local_path = Path(writer.path, self.acquisition_name)
                    if not os.path.isdir(local_path):
                        os.makedirs(local_path)
        # check if external directories exist and create if not
        if self.file_transfers:
            for file_transfer_dictionary in self.file_transfers.values():
                for file_transfer in file_transfer_dictionary.values():
                    if self.acquisition_name:
                        external_path = Path(file_transfer.external_path, self.acquisition_name)
                        if not os.path.isdir(external_path):
                            os.makedirs(external_path)

    def _verify_acquisition(self) -> None:
        """
        Verify the acquisition configuration.

        :raises ValueError: If there is no writer for a camera
        :raises ValueError: If multiple operations write to the same folder
        :raises ValueError: If multiple operations transfer to the same folder
        :raises ValueError: If not all stage axes are defined for tile positions
        :raises ValueError: If the channel is not in the instrument channels
        """
        self.log.info("verifying acquisition configuration")

        # check that there is an associated writer for each camera
        for camera_id, camera in self.instrument.cameras.items():
            if camera_id not in self.writers:
                raise ValueError(f"no writer found for camera {camera_id}. check yaml files.")

        # check that files won't be overwritten if multiple writers/transfers per device
        for device_name, writers in self.writers.items():
            paths = [write.path for write in writers.values()]
            if len(paths) != len(set(paths)):
                raise ValueError(
                    f"More than one operation for device {device_name} is writing to the same folder. "
                    f"This will cause data to be overwritten."
                )
        # check that files won't be overwritten if multiple writers/transfers per device
        for device_name, transfers in getattr(self, "transfers", {}).items():
            external_directories = [transfer.external_path for transfer in transfers.values()]
            if len(external_directories) != len(set(external_directories)):
                raise ValueError(
                    f"More than one operation for device {device_name} is transferring to the same folder."
                    f" This will cause data to be overwritten."
                )
        # check tile parameters
        for tile in self.config["acquisition"]["tiles"]:
            position_axes = list(tile["position_mm"].keys())
            if position_axes.sort() != self.instrument.stage_axes.sort():
                raise ValueError("not all stage axes are defined for tile positions")
            tile_channel = tile["channel"]
            if tile_channel not in self.instrument.channels:
                raise ValueError(f"channel {tile_channel} is not in {self.instrument.channels}")
