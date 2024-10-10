import numpy as np
import time
import threading
import logging
import sys
import shutil
import os
import subprocess
import platform
from ruamel.yaml import YAML
from pathlib import Path
from psutil import virtual_memory
from gputools import get_device
from voxel.instruments.instrument import Instrument
from voxel.writers.data_structures.shared_double_buffer import SharedDoubleBuffer
import inflection
import inspect
import re

class Acquisition:

    def __init__(self, instrument: Instrument, config_filename: str, yaml_handler: YAML = None, log_level='INFO'):

        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.log.setLevel(log_level)

        # create yaml object to use when loading and dumping config
        self.yaml = yaml_handler if yaml_handler is not None else YAML(typ='safe')

        self.config_path = Path(config_filename)
        self.config = self.yaml.load(Path(self.config_path))

        self.instrument = instrument

        # initialize metadata attribute. NOT a dictionary since only one metadata class can exist in acquisition
        # TODO: Validation of config should check that metadata exists and only one
        self.metadata = self._construct_class(self.config['acquisition']['metadata'])
        self.acquisition_name = None    # initialize acquisition_name that will be populated at start of acquisition

        # initialize operations
        for operation_type, operation_dict in self.config['acquisition']['operations'].items():
            setattr(self, operation_type, dict())
            self._construct_operations(operation_type, operation_dict)

    def _load_class(self, driver: str, module: str, kwds: dict = dict()):
        """Load in device based on config. Expecting driver, module, and kwds input"""
        self.log.info(f'loading {driver}.{module}')
        __import__(driver)
        device_class = getattr(sys.modules[driver], module)
        return device_class(**kwds)

    def _setup_class(self, device: object, properties: dict):
        """Setup device based on properties dictionary
        :param device: device to be setup
        :param properties: dictionary of attributes, values to set according to config"""

        self.log.info(f'setting up {device}')
        # successively iterate through properties keys and if there is setter, set
        for key, value in properties.items():
            try:
                setattr(device, key, value)
            except (TypeError, AttributeError):
                self.log.info(f'{device} property {key} has no setter')

    def _construct_operations(self, device_name: str, operation_dictionary: dict):
        """Load and setup operations of an acquisition
        :param device_name: name of device which operation pertain to
        :param operation_dictionary: dictionary of operation pertaining to device"""

        for operation_name, operation_specs in operation_dictionary.items():
            operation_type = inflection.pluralize(operation_specs['type'])
            operation_object = self._construct_class(operation_specs)

            # create operation dictionary if it doesn't already exist and add operation to dictionary
            if not hasattr(self, operation_type):
                setattr(self, operation_type, {device_name: {}})
            elif not getattr(self, operation_type).get(device_name, False):
                getattr(self, operation_type)[device_name] = {}
            getattr(self, operation_type)[device_name][operation_name] = operation_object

    def _construct_class(self, class_specs: dict):
        """Construct a class object based on dictionary specifications
        :param """

        driver = class_specs['driver']
        module = class_specs['module']
        init = class_specs.get('init', {})
        class_object = self._load_class(driver, module, init)
        properties = class_specs.get('properties', {})
        self.log.info(f'constructing {driver}')
        self._setup_class(class_object, properties)

        return class_object

    @property
    def _acquisition_rate_hz(self):
        # use master device to determine theoretical instrument speed.
        # master device is last device in trigger tree
        master_device_name = self.instrument.master_device['name']
        master_device_type = self.instrument.master_device['type']
        # if camera, calculate acquisition rate based on frame time
        if master_device_type == 'camera':
            acquisition_rate_hz = 1.0 / (self.instrument.cameras[master_device_name].frame_time_ms / 1000)
        # if scanning stage, calculate acquisition rate based on speed and voxel size
        elif master_device_type == 'scanning stage':
            speed_mm_s = self.instrument.scanning_stages[master_device_name].speed_mm_s
            voxel_size_um = tile['voxel_size_um']
            acquisition_rate_hz = speed_mm_s / (voxel_size_um / 1000)
        # if daq, calculate based on task interval time
        elif master_device_type == 'daq':
            master_task = self.instrument.master_device['task']
            acquisition_rate_hz = 1.0 / self.instrument.daqs[master_device_name].task_time_s[master_task]
        # otherwise assertion, these are the only three supported master devices
        else:
            raise ValueError(f'master device type {master_device_type} is not supported.')
        return acquisition_rate_hz

    def run(self):
        """Run function. This method must be overwritten for each specific microscope"""

        self.acquisition_name = self.metadata.acquisition_name
        self._set_acquisition_name()
        self._verify_acquisition()
        self._create_directories()

    def _create_directories(self):
        """Using the latest metadata derived acquisition_name, correctly set writers and transfer and create
        directories if needed"""

        self.log.info(f'verifying local and external directories')

        # check if local directories exist and create if not
        for writer_dictionary in self.writers.values():
            for writer in writer_dictionary.values():
                local_path = Path(writer.path, self.acquisition_name)
                if not os.path.isdir(local_path):
                    os.makedirs(local_path)
        # check if external directories exist and create if not
        if hasattr(self, 'transfers'):
            for transfer_dictionary in self.transfers.values():
                for transfer in transfer_dictionary.values():
                    external_path = Path(transfer.external_path, self.acquisition_name)
                    if not os.path.isdir(external_path):
                        os.makedirs(external_path)

    def _set_acquisition_name(self):
        """Iterate through operations and set acquisition name if it has attr"""

        for device_name, operation_dict in self.config['acquisition']['operations'].items():
            for op_name, op_specs in operation_dict.items():
                op_type = inflection.pluralize(op_specs['type'])
                operation = getattr(self, op_type)[device_name][op_name]
                if hasattr(operation, 'acquisition_name'):
                    setattr(operation, 'acquisition_name', self.acquisition_name)

    def _verify_acquisition(self):

        self.log.info(f'verifying acquisition configuration')

        # check that there is an associated writer for each camera
        for camera_id, camera in self.instrument.cameras.items():
            if camera_id not in self.writers.keys():
                raise ValueError(f'no writer found for camera {camera_id}. check yaml files.')

        # check that files won't be overwritten if multiple writers/transfers per device
        for device_name, writers in self.writers.items():
            paths = [write.path for write in writers.values()]
            if len(paths) != len(set(paths)):
                raise ValueError(f'More than one operation for device {device_name} is writing to the same folder. '
                                 f'This will cause data to be overwritten.')
        # check that files won't be overwritten if multiple writers/transfers per device
        for device_name, transfers in getattr(self, 'transfers', {}).items():
            external_directories = [transfer.external_path for transfer in transfers.values()]
            if len(external_directories) != len(set(external_directories)):
                raise ValueError(f'More than one operation for device {device_name} is transferring to the same folder.'
                                 f' This will cause data to be overwritten.')

        # check tile parameters
        for tile in self.config['acquisition']['tiles']:
            position_axes = list(tile['position_mm'].keys())
            if position_axes.sort() != self.instrument.stage_axes.sort():
                raise ValueError(f'not all stage axes are defined for tile positions')
            tile_channel = tile['channel']
            if tile_channel not in self.instrument.channels:
                raise ValueError(f'channel {tile_channel} is not in {self.instrument.channels}')

    def _frame_size_mb(self, camera_id: str, writer_id: str):
        row_count_px = self.instrument.cameras[camera_id].height_px
        column_count_px = self.instrument.cameras[camera_id].width_px
        data_type = self.writers[camera_id][writer_id].data_type
        frame_size_mb = row_count_px * column_count_px * np.dtype(data_type).itemsize / 1024 ** 2
        return frame_size_mb

    def _pyramid_factor(self, levels: int):
        pyramid_factor = 0
        for level in range(levels):
            pyramid_factor += (1 / (2 ** level)) ** 3
        return pyramid_factor

    def _check_compression_ratio(self, camera_id: str, writer_id: str):
        self.log.info(f'estimating acquisition compression ratio')
        # get the correct camera and writer
        camera = self.instrument.cameras[camera_id]
        writer = self.writers[camera_id][writer_id]
        if writer.compression != 'none':
            # store initial trigger mode
            initial_trigger = camera.trigger
            # turn trigger off
            new_trigger = initial_trigger
            new_trigger['mode'] = 'off'
            camera.trigger = new_trigger

            # prepare the writer
            writer.row_count_px = camera.height_px
            writer.column_count_px = camera.width_px
            writer.frame_count_px = writer.chunk_count_px
            writer.filename = 'compression_ratio_test'

            chunk_size = writer.chunk_count_px
            chunk_lock = threading.Lock()
            img_buffer = SharedDoubleBuffer((chunk_size, camera.height_px, camera.width_px),
                                            dtype=writer.data_type)

            # set up and start writer and camera
            writer.prepare()
            camera.prepare()
            writer.start()
            camera.start()

            frame_index = 0
            for frame_index in range(writer.chunk_count_px):
                # grab camera frame

                current_frame = camera.grab_frame()
                # put into image buffer
                img_buffer.write_buf[frame_index] = current_frame
                frame_index += 1

            while not writer.done_reading.is_set():
                time.sleep(0.001)

            with chunk_lock:
                img_buffer.toggle_buffers()
                if writer.path is not None:
                    writer.shm_name = \
                        img_buffer.read_buf_mem_name
                    writer.done_reading.clear()

                    # close writer and camera
            writer.wait_to_finish()
            camera.stop()

            # reset the trigger
            camera.trigger = initial_trigger

            # clean up the image buffer
            img_buffer.close_and_unlink()
            del img_buffer

            # check the compressed file size
            filepath = str((writer.path / Path(f"{writer.filename}")).absolute())
            compressed_file_size_mb = os.stat(filepath).st_size / (1024 ** 2)
            # calculate the raw file size
            frame_size_mb = self._frame_size_mb(camera_id, writer_id)
            # get pyramid factor
            pyramid_factor = self._pyramid_factor(levels=3)
            raw_file_size_mb = frame_size_mb * writer.frame_count_px * pyramid_factor
            # calculate the compression ratio
            compression_ratio = raw_file_size_mb / compressed_file_size_mb
            # delete the files
            writer.delete_files()
        else:
            compression_ratio = 1.0
        self.log.info(f'compression ratio for camera: {camera_id} writer: {writer_id} ~ {compression_ratio:.1f}')
        return compression_ratio

    def check_local_acquisition_disk_space(self):
        """Checks local and ext disk space before scan to see if disk has enough space scan
        """
        self.log.info(f"checking total local storage directory space")
        drives = dict()
        for camera_id, camera in self.instrument.cameras.items():
            data_size_gb = 0
            for writer_id, writer in self.writers[camera_id].items():
                # if windows
                if platform.system() == 'Windows':
                    local_drive = os.path.splitdrive(writer.path)[0]
                # if unix
                else:
                    abs_path = os.path.abspath(writer.path)
                    # TODO FIX THIS, SYNTAX FOR UNIX DRIVES?
                    local_drive = '/'
                for tile in self.config['acquisition']['tiles']:
                    frame_size_mb = self._frame_size_mb(camera_id, writer_id)
                    frame_count_px = tile['steps']
                    data_size_gb += frame_count_px * frame_size_mb / 1024
                drives.setdefault(local_drive, []).append(data_size_gb)

        for drive in drives:
            required_size_gb = sum(drives[drive])
            self.log.info(f'required disk space = {required_size_gb:.1f} [GB] on drive {drive}')
            free_size_gb = shutil.disk_usage(drive).free / 1024 ** 3
            if data_size_gb >= free_size_gb:
                self.log.error(f"only {free_size_gb:.1f} available on drive: {drive}")
                raise ValueError(f"only {free_size_gb:.1f} available on drive: {drive}")
            else:
                self.log.info(f'available disk space = {free_size_gb:.1f} [GB] on drive {drive}')

    def check_external_acquisition_disk_space(self):
        """Checks local and ext disk space before scan to see if disk has enough space scan
        """
        self.log.info(f"checking total external storage directory space")
        if self.transfers:
            drives = dict()
            for camera_id, camera in self.instrument.cameras.items():
                for transfer_id, transfer in self.transfers[camera_id].items():
                    for writer_id, writer in self.writers[camera_id].items():
                        data_size_gb = 0
                        # if windows
                        if platform.system() == 'Windows':
                            external_drive = os.path.splitdrive(transfer.external_path)[0]
                        # if unix
                        else:
                            abs_path = os.path.abspath(transfer.external_path)
                            # TODO FIX THIS, SYNTAX FOR UNIX DRIVES?
                            external_drive = '/'
                        for tile in self.config['acquisition']['tiles']:
                            frame_size_mb = self._frame_size_mb(camera_id, writer_id)
                            frame_count_px = tile['steps']
                            data_size_gb += frame_count_px * frame_size_mb / 1024
                        drives.setdefault(external_drive, []).append(data_size_gb)
            for drive in drives:
                required_size_gb = sum(drives[drive])
                self.log.info(f'required disk space = {required_size_gb:.1f} [GB] on drive {drive}')
                free_size_gb = shutil.disk_usage(drive).free / 1024 ** 3
                if data_size_gb >= free_size_gb:
                    self.log.error(f"only {free_size_gb:.1f} available on drive: {drive}")
                    raise ValueError(f"only {free_size_gb:.1f} available on drive: {drive}")
                else:
                    self.log.info(f'available disk space = {free_size_gb:.1f} [GB] on drive {drive}')
        else:
            raise ValueError(f'no transfers configured. check yaml files.')

    def check_local_tile_disk_space(self, tile: dict):
        """Checks local and ext disk space before scan to see if disk has enough space scan
        """
        self.log.info(f"checking local storage directory space for next tile")
        drives = dict()
        data_size_gb = 0
        for camera_id, camera in self.instrument.cameras.items():
            for writer_id, writer in self.writers[camera_id].items():
                # if windows
                if platform.system() == 'Windows':
                    local_drive = os.path.splitdrive(writer.path)[0]
                # if unix
                else:
                    abs_path = os.path.abspath(writer.path)
                    local_drive = '/'

                frame_size_mb = self._frame_size_mb(camera_id, writer_id)
                frame_count_px = tile['steps']
                data_size_gb += frame_count_px * frame_size_mb / 1024

                drives.setdefault(local_drive, []).append(data_size_gb)

        for drive in drives:
            required_size_gb = sum(drives[drive])
            self.log.info(f'required disk space = {required_size_gb:.1f} [GB] on drive {drive}')
            free_size_gb = shutil.disk_usage(drive).free / 1024 ** 3
            if data_size_gb >= free_size_gb:
                self.log.error(f"only {free_size_gb:.1f} available on drive: {drive}")
                return False
            else:
                self.log.info(f'available disk space = {free_size_gb:.1f} [GB] on drive {drive}')
                return True

    def check_external_tile_disk_space(self, tile: dict):
        """Checks local and ext disk space before scan to see if disk has enough space scan
        """
        self.log.info(f"checking external storage directory space for next tile")
        if self.transfers:
            drives = dict()
            for camera_id, camera in self.instrument.cameras.items():
                data_size_gb = 0
                # if windows
                if platform.system() == 'Windows':
                    external_drive = os.path.splitdrive(self.transfers[camera_id].external_path)[0]
                # if unix
                else:
                    abs_path = os.path.abspath(self.transfers[camera_id].external_path)
                    # TODO FIX THIS
                    external_drive = '/'
                frame_size_mb = self._frame_size_mb(camera_id)
                frame_count_px = tile['steps']
                data_size_gb += frame_count_px * frame_size_mb / 1024
                drives.setdefault(external_drive, []).append(data_size_gb)
            for drive in drives:
                required_size_gb = sum(drives[drive])
                self.log.info(f'required disk space = {required_size_gb:.1f} [GB] on drive {drive}')
                free_size_gb = shutil.disk_usage(drive).free / 1024 ** 3
                if data_size_gb >= free_size_gb:
                    self.log.error(f"only {free_size_gb:.1f} available on drive: {drive}")
                    raise ValueError(f"only {free_size_gb:.1f} available on drive: {drive}")
                else:
                    self.log.info(f'available disk space = {free_size_gb:.1f} [GB] on drive {drive}')
        else:
            raise ValueError(f'no transfers configured. check yaml files.')

    def check_write_speed(self, size='16Gb', bs='1M', direct=1, numjobs=1,
                          iodepth=1, runtime=0):
        """Check local read/write speeds to make sure it can keep up with acquisition

        :param size: Size of test file
        :param bs: Block size in bytes used for I/O units
        :param direct: Specifying buffered (0) or unbuffered (1) operation
        :param numjobs: Number of clones of this job. Each clone of job is spawned as an independent thread or process
        :param ioengine: Defines how the job issues I/O to the file
        :param iodepth: Number of I/O units to keep in flight against the file.
        :param runtime: Limit runtime. The test will run until it completes the configured I/O workload or until it has
                        run for this specified amount of time, whichever occurs first
        """
        self.log.info(f"checking write speed to local and external directories")
        # windows ioengine
        if platform.system() == 'Windows':
            ioengine = 'windowsaio'
        # unix ioengine
        else:
            ioengine = 'posixaio'

        drives = dict()
        camera_speed_mb_s = dict()

        # loop over cameras and see where they are acquiring data
        for camera_id, camera in self.instrument.cameras.items():
            for writer_id, writer in self.writers[camera_id].items():
                # check the compression ratio for this camera
                compression_ratio = self._check_compression_ratio(camera_id, writer_id)
                # grab the frame size and acquisition rate
                frame_size_mb = self._frame_size_mb(camera_id, writer_id)
                acquisition_rate_hz = self._acquisition_rate_hz
                local_path = writer.path
                # strip drive letters from paths so that we can combine
                # cameras acquiring to the same drives
                if platform.system() == 'Windows':
                    local_drive_letter = os.path.splitdrive(local_path)[0]
                # if unix
                else:
                    # TODO FIX THIS -> what is syntax for unix drives?
                    local_abs_path = os.path.abspath(local_path)
                    local_drive_letter = '/'
                # add into drives dictionary append to list if same drive letter
                drives.setdefault(local_drive_letter, []).append(local_path)
                camera_speed_mb_s.setdefault(local_drive_letter, []).append(
                    acquisition_rate_hz * frame_size_mb / compression_ratio)
                if self.transfers:
                    for transfer_id, transfer in self.transfers[camera_id].items():
                        external_path = transfer.external_path
                        # strip drive letters from paths so that we can combine
                        # cameras acquiring to the same drives
                        if platform.system() == 'Windows':
                            external_drive_letter = os.path.splitdrive(local_path)[0]
                        # if unix
                        else:
                            # TODO FIX THIS -> what is syntax for unix drives?
                            external_abs_path = os.path.abspath(local_path)
                            external_drive_letter = '/'
                        # add into drives dictionary append to list if same drive letter
                        drives.setdefault(external_drive_letter, []).append(external_path)
                        camera_speed_mb_s.setdefault(external_drive_letter, []).append(
                            acquisition_rate_hz * frame_size_mb)

        for drive in drives:
            # if more than one stream on this drive, just test the first directory location
            local_path = drives[drive][0]
            test_filename = Path(f'{local_path}/iotest')
            f = open(test_filename, 'a')  # Create empty file to check reading/writing speed
            f.close()
            try:
                output = subprocess.check_output(
                    fr'fio --name=test --filename={test_filename} --size={size} --rw=write --bs={bs} '
                    fr'--direct={direct} --numjobs={numjobs} --ioengine={ioengine} --iodepth={iodepth} '
                    fr'--runtime={runtime} --startdelay=0 --thread --group_reporting', shell=True)
                out = str(output)
                # Converting MiB to MB = (10**6/2**20)
                write_speed_mb_s = round(
                    float(out[out.find('BW=') + len('BW='):out.find('MiB/s')]) / (10 ** 6 / 2 ** 20))

                total_speed_mb_s = sum(camera_speed_mb_s[drive])
                # check if drive write speed exceeds the sum of all cameras streaming to this drive
                if write_speed_mb_s < total_speed_mb_s:
                    self.log.warning(f'write speed too slow on drive {drive}')
                    raise ValueError(f'write speed too slow on drive {drive}')

                self.log.info(f'available write speed = {write_speed_mb_s:.1f} [MB/sec] to directory {drive}')
                self.log.info(f'required write speed = {total_speed_mb_s:.1f} [MB/sec] to directory {drive}')

            except subprocess.CalledProcessError:
                self.log.warning('fios not installed on computer. Cannot verify read/write speed')
            finally:
                # Delete test file
                os.remove(test_filename)

    def check_system_memory(self):
        """Make sure this machine can image under the specified configuration.

        :param channel_count: the number of channels we want to image with.
        :param mem_chunk: the number of images to hold in one chunk for
            compression
        :raises MemoryError:
        """
        self.log.info(f"checking available system memory")
        # Calculate double buffer size for all channels.
        memory_gb = 0
        for camera_id, camera in self.instrument.cameras.items():
            for writer_id, writer in self.writers[camera_id].items():
                chunk_count_px = writer.chunk_count_px
                # factor of 2 for concurrent chunks being written/read
                frame_size_mb = self._frame_size_mb(camera_id, writer_id)
                memory_gb += 2 * chunk_count_px * frame_size_mb / 1024

        free_memory_gb = virtual_memory()[1] / 1024 ** 3

        self.log.info(f'required RAM = {memory_gb:.1f} [GB]')
        self.log.info(f'available RAM = {free_memory_gb:.1f} [GB]')

        if free_memory_gb < memory_gb:
            raise MemoryError('system does not have enough memory to run')

    def check_gpu_memory(self):
        # check GPU resources for downscaling
        memory_gb = 0
        for camera_id, camera in self.instrument.cameras.items():
            for writer_id, writer in self.writers[camera_id].items():
                chunk_count_px = writer.chunk_count_px
            # factor of 2 for concurrent chunks being written/read
            frame_size_mb = self._frame_size_mb(camera_id, writer_id)
            memory_gb += 2 * chunk_count_px * frame_size_mb / 1024
        # TODO, SHOULD WE USE SOMETHING BESIDES GPUTOOLS TO CHECK GPU MEMORY?
        total_gpu_memory_gb = get_device().get_info('MAX_MEM_ALLOC_SIZE') / 1024 ** 3
        self.log.info(f'required GPU RAM = {memory_gb:.1f} [GB]')
        self.log.info(f'available GPU RAM = {total_gpu_memory_gb:.1f} [GB]')
        if memory_gb >= total_gpu_memory_gb:
            raise ValueError(f'{memory_gb} [GB] \
                                GPU RAM requested but only \
                                {total_gpu_memory_gb} [GB] available')

    def update_current_state_config(self):
        """Capture current state of instrument in config form"""

        # update properties of operations
        for device_name, op_dict in self.config['acquisition']['operations'].items():
            for op_name, op_specs in op_dict.items():
                op = getattr(self, inflection.pluralize(op_specs['type']))[device_name][op_name]
                op_specs['properties'] = self._collect_properties(op)
        # update properties of metadata
        self.config['acquisition']['metadata']['properties'] = self._collect_properties(self.metadata)

    @staticmethod
    def _collect_properties(obj: object):
        """Scan through object and return dictionary of properties
        :param obj: object to find properties from """

        properties = {}
        for attr_name in dir(obj):
            attr = getattr(type(obj), attr_name, None)
            if isinstance(attr, property) or isinstance(inspect.unwrap(attr), property):
                properties[attr_name] = getattr(obj, attr_name)
        return properties

    def save_config(self, path: Path):
        """Save current config to path provided
        :param path: path to save config to"""

        with path.open("w") as f:
            self.yaml.dump(self.config, f)

    def stop_acquisition(self):
        """Method to force quit acquisition by raising error"""
        raise RuntimeError

    def close(self):
        """Close functionality"""
        pass
