# -*- coding: utf-8 -*-
"""
This module wraps the pco.recorder to python data structures.

Copyright @ Excelitas PCO GmbH 2005-2023

The a instance of the Recorder class is part of pco.Camera
"""


import ctypes as C
import sys
import os
import time
from datetime import datetime
import platform
import warnings
import logging

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class PCO_TIMESTAMP_STRUCT(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("dwImgCounter", C.c_uint32),
        ("wYear", C.c_uint16),
        ("wMonth", C.c_uint16),
        ("wDay", C.c_uint16),
        ("wHour", C.c_uint16),
        ("wMinute", C.c_uint16),
        ("wSecond", C.c_uint16),
        ("dwMicroSeconds", C.c_uint32),
    ]


class PCO_METADATA_STRUCT(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wVersion", C.c_uint16),
        ("bIMAGE_COUNTER_BCD", C.c_uint8 * 4),
        ("bIMAGE_TIME_US_BCD", C.c_uint8 * 3),
        ("bIMAGE_TIME_SEC_BCD", C.c_uint8),
        ("bIMAGE_TIME_MIN_BCD", C.c_uint8),
        ("bIMAGE_TIME_HOUR_BCD", C.c_uint8),
        ("bIMAGE_TIME_DAY_BCD", C.c_uint8),
        ("bIMAGE_TIME_MON_BCD", C.c_uint8),
        ("bIMAGE_TIME_YEAR_BCD", C.c_uint8),
        ("bIMAGE_TIME_STATUS", C.c_uint8),
        ("wEXPOSURE_TIME_BASE", C.c_uint16),
        ("dwEXPOSURE_TIME", C.c_uint32),
        ("dwFRAMERATE_MILLIHZ", C.c_uint32),
        ("sSENSOR_TEMPERATURE", C.c_short),
        ("wIMAGE_SIZE_X", C.c_uint16),
        ("wIMAGE_SIZE_Y", C.c_uint16),
        ("bBINNING_X", C.c_uint8),
        ("bBINNING_Y", C.c_uint8),
        ("dwSENSOR_READOUT_FREQUENCY", C.c_uint32),
        ("wSENSOR_CONV_FACTOR", C.c_uint16),
        ("dwCAMERA_SERIAL_NO", C.c_uint32),
        ("wCAMERA_TYPE", C.c_uint16),
        ("bBIT_RESOLUTION", C.c_uint8),
        ("bSYNC_STATUS", C.c_uint8),
        ("wDARK_OFFSET", C.c_uint16),
        ("bTRIGGER_MODE", C.c_uint8),
        ("bDOUBLE_IMAGE_MODE", C.c_uint8),
        ("bCAMERA_SYNC_MODE", C.c_uint8),
        ("bIMAGE_TYPE", C.c_uint8),
        ("wCOLOR_PATTERN", C.c_uint16),
        ("wCAMERA_SUBTYPE", C.c_uint16),
        ("dwEVENT_NUMBER", C.c_uint32),
        ("wIMAGE_SIZE_X_Offset", C.c_uint16),
        ("wIMAGE_SIZE_Y_Offset", C.c_uint16),
    ]


class PCO_RECORDER_COMPRESSION_PARAMETER(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("dGainK", C.c_double),
        ("dDarkNoise_e", C.c_double),
        ("dDSNU_e", C.c_double),
        ("dPRNU_pct", C.c_double),
        ("dLightSourceNoise_pct", C.c_double),
    ]


class Recorder:
    class exception(Exception):
        def __str__(self):
            return "Exception: {0} {1:08x}".format(
                self.args[0], self.args[1] & (2**32 - 1)
            )

    def __bcd_to_decimal(self, byte_value):
        """
        Convert a 16 bit bcd encoded value to its decimal representation
        """
        return ((byte_value / 0x10) * 10) + (byte_value % 0x10)

    def __init__(self, sdk, camera_handle, name=""):

        if platform.architecture()[0] != "64bit":
            print("Python Interpreter not x64")
            raise OSError

        if sys.platform.startswith('win32'):
            self.__dll_name = "PCO_Recorder.dll"
        elif sys.platform.startswith('linux'):
            self.__dll_name = "libpco_recorder.so.3"
        else:
            print("Package not supported on platform " + sys.platform)
            raise SystemError

        dll_path = os.path.dirname(__file__).replace("\\", "/")

        # set working directory
        # workaround, due to implicit load of PCO_File.dll
        current_working_directory = os.getcwd()
        os.chdir(dll_path)

        try:
            if sys.platform.startswith('win32'):
                self.PCO_Recorder = C.windll.LoadLibrary(dll_path + "/" + self.__dll_name)
            else:  # if sys.platform.startswith('linux'):
                self.PCO_Recorder = C.cdll.LoadLibrary(dll_path + "/" + self.__dll_name)
        except OSError:
            print(
                "Error: "
                + '"'
                + self.__dll_name
                + '" not found in directory "'
                + dll_path
                + '".'
            )
            os.chdir(current_working_directory)
            raise

        os.chdir(current_working_directory)

        self.recorder_handle = C.c_void_p(0)
        self.camera_handle = camera_handle
        self.sdk = sdk

        self.name = name

        """ARGTYPES"""
        self.PCO_Recorder.PCO_RecorderGetVersion.argtypes = [
            C.POINTER(C.c_int),
            C.POINTER(C.c_int),
            C.POINTER(C.c_int),
            C.POINTER(C.c_int),
        ]

        self.PCO_Recorder.PCO_RecorderResetLib.argtypes = [
            C.c_bool,
        ]

        self.PCO_Recorder.PCO_RecorderCreate.argtypes = [
            C.POINTER(C.c_void_p),
            C.POINTER(C.c_void_p),
            C.POINTER(C.c_uint32),
            C.c_uint16,
            C.c_uint16,
            C.c_char_p,
            C.POINTER(C.c_uint32),
        ]

        self.PCO_Recorder.PCO_RecorderDelete.argtypes = [
            C.c_void_p,
        ]

        self.PCO_Recorder.PCO_RecorderInit.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_char_p,
            C.POINTER(C.c_uint16),
        ]

        self.PCO_Recorder.PCO_RecorderCleanup.argtypes = [
            C.c_void_p,
            C.c_void_p,
        ]

        self.PCO_Recorder.PCO_RecorderGetSettings.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.PCO_Recorder.PCO_RecorderStartRecord.argtypes = [
            C.c_void_p,
            C.c_void_p,
        ]

        self.PCO_Recorder.PCO_RecorderStopRecord.argtypes = [
            C.c_void_p,
            C.c_void_p,
        ]

        self.PCO_Recorder.PCO_RecorderSetAutoExposure.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_bool,
            C.c_uint16,
            C.c_uint32,
            C.c_uint32,
            C.c_uint16,
        ]

        self.PCO_Recorder.PCO_RecorderSetAutoExpRegions.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_uint16,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.c_uint16,
        ]

        self.PCO_Recorder.PCO_RecorderSetCompressionParams.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.POINTER(PCO_RECORDER_COMPRESSION_PARAMETER),
        ]

        self.PCO_Recorder.PCO_RecorderGetStatus.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.POINTER(C.c_bool),
            C.POINTER(C.c_bool),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_bool),
            C.POINTER(C.c_bool),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
        ]

        self.PCO_Recorder.PCO_RecorderCopyImage.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_uint32,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
            C.POINTER(PCO_METADATA_STRUCT),
            C.POINTER(PCO_TIMESTAMP_STRUCT),
        ]

        self.PCO_Recorder.PCO_RecorderCopyAverageImage.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_uint32,
            C.c_uint32,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.POINTER(C.c_uint16),
        ]

        self.PCO_Recorder.PCO_RecorderCopyImageCompressed.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_uint32,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
            C.POINTER(PCO_METADATA_STRUCT),
            C.POINTER(PCO_TIMESTAMP_STRUCT),
        ]

        self.PCO_Recorder.PCO_RecorderExportImage.argtypes = [
            C.c_void_p,
            C.c_uint32,
            C.c_char_p,
            C.c_bool,
        ]

    def get_error_text(self, error):
        return self.sdk.get_error_text(error)

    # -------------------------------------------------------------------------
    # 2.1 PCO_RecorderGetVersion
    # -------------------------------------------------------------------------
    def get_version(self):
        """"""

        iMajor = C.c_int(0)
        iMinor = C.c_int(0)
        iPatch = C.c_int(0)
        iBuild = C.c_int(0)

        time_start = time.perf_counter()
        self.PCO_Recorder.PCO_RecorderGetVersion(iMajor, iMinor, iPatch, iBuild)
        duration = time.perf_counter() - time_start

        ret = {}

        ret.update(
            {
                "name": self.__dll_name,
                "major": iMajor.value,
                "minor": iMinor.value,
                "patch": iPatch.value,
                "build": iBuild.value,
            }
        )

        return ret

    # -------------------------------------------------------------------------
    # 2.2 PCO_RecorderSaveImage
    # -------------------------------------------------------------------------

    def save_image(self):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.3 PCO_RecorderSaveOverlay
    # -------------------------------------------------------------------------
    def save_overlay(self):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.4 PCO_RecorderResetLib
    # -------------------------------------------------------------------------
    def reset_lib(self):
        """"""

        bSilent = C.c_bool(True)

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderResetLib(bSilent)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        self.recorder_handle = C.c_void_p(0)

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5 PCO_RecorderCreate
    # -------------------------------------------------------------------------
    def create(self, mode, dpcore=False, file_path=None):
        """
        Initilize and create recorder
        """

        self.recorder_handle = C.c_void_p(0)

        if file_path is not None:
            letter = file_path[0]
        else:
            letter = "C"

        path = C.c_char_p()
        path.value = letter.encode("utf-8")

        recorder_mode = {"file": 1, "memory": 2, "camram": 3}

        dwImgDistributionArr = C.c_uint32(1)
        wArrLength = C.c_uint16(1)
        wRecMode = C.c_uint16()
        cDriveLetter = path
        dwMaxImgCountArr = C.c_uint32()

        wRecMode = recorder_mode[mode]
        if dpcore:
            wRecMode = wRecMode | 0x1000

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderCreate(
            self.recorder_handle,
            self.camera_handle,
            dwImgDistributionArr,
            wArrLength,
            wRecMode,
            cDriveLetter,
            dwMaxImgCountArr,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"maximum available images": dwMaxImgCountArr.value})

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6 PCO_RecorderDelete
    # -------------------------------------------------------------------------
    def delete(self):
        """"""

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderDelete(self.recorder_handle)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        self.recorder_handle = C.c_void_p(0)

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.7 PCO_RecorderInit
    # -------------------------------------------------------------------------
    def init(self, number_of_images, recorder_type, file_path=None):
        """"""

        dwImgCountArr = C.c_uint32(number_of_images)
        wArrLength = C.c_uint16(1)
        wType = C.c_uint16()
        wNoOverwrite = C.c_uint16(0)

        path = C.c_char_p()
        if file_path is not None:
            path.value = file_path.encode("utf-8")
        else:
            path.value = "C:\\".encode("utf-8")

        wRamSegmentArr = C.c_uint16()

        recorder_mode = {
            "sequence": 1,
            "ring buffer": 2,
            "fifo": 3,
            "tif": 1,
            "multitif": 2,
            "pcoraw": 3,
            "b16": 4,
            "dicom": 5,
            "multidicom": 6,
        }

        wType = recorder_mode[recorder_type]

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderInit(
            self.recorder_handle,
            dwImgCountArr,
            wArrLength,
            wType,
            wNoOverwrite,
            path,
            wRamSegmentArr,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.8 PCO_RecorderCleanup
    # -------------------------------------------------------------------------
    def cleanup(self):
        """"""

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderInit(
            self.recorder_handle, self.camera_handle
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.9 PCO_RecorderGetSettings
    # -------------------------------------------------------------------------
    def get_settings(self):
        """"""

        dwRecmode = C.c_uint32()
        dwMaxImgCount = C.c_uint32()
        dwReqImgCount = C.c_uint32()
        wWidth = C.c_uint16()
        wHeight = C.c_uint16()
        wMetadataLines = C.c_uint16()

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderGetSettings(
            self.recorder_handle,
            self.camera_handle,
            dwRecmode,
            dwMaxImgCount,
            dwReqImgCount,
            wWidth,
            wHeight,
            wMetadataLines,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"recorder mode": dwRecmode.value})
            ret.update({"maximum number of images": dwMaxImgCount.value})
            ret.update({"required number of images": dwReqImgCount.value})
            ret.update({"width": wWidth.value})
            ret.update({"height": wHeight.value})
            ret.update({"metadata lines": wMetadataLines.value})

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.10 PCO_RecorderStartRecord
    # -------------------------------------------------------------------------
    def start_record(self):
        """"""

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderStartRecord(
            self.recorder_handle, self.camera_handle
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.11 PCO_RecorderStopRecord
    # -------------------------------------------------------------------------
    def stop_record(self):
        """"""

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderStopRecord(
            self.recorder_handle, self.camera_handle
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.12 PCO_RecorderSetAutoExposure
    # -------------------------------------------------------------------------
    def set_auto_exposure(
        self, mode, smoothness=2, min_exposure_time=1e-3, max_exposure_time=100e-3
    ):
        """
        Set auto exposure

        :param active: bool
        :param smoothness: int
        :param min_exposure_time: float
        :param max_exposure_time: float
        """

        if mode == "on":
            active = True
        else:
            active = False

        # Only check min for timebase, since max is always greater
        if min_exposure_time <= 4e-3:
            min_time = int(min_exposure_time * 1e9)
            max_time = int(max_exposure_time * 1e9)
            timebase = 0  # ns

        elif min_exposure_time <= 4:
            min_time = int(min_exposure_time * 1e6)
            max_time = int(max_exposure_time * 1e6)
            timebase = 1  # us

        elif min_exposure_time > 4:
            min_time = int(min_exposure_time * 1e3)
            max_time = int(max_exposure_time * 1e3)
            timebase = 2  # ms

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderSetAutoExposure(
            self.recorder_handle,
            self.camera_handle,
            active,
            smoothness,
            min_time,
            max_time,
            timebase,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.13 PCO_RecorderSetAutoExpRegions
    # -------------------------------------------------------------------------
    def set_auto_exp_regions(self, region_type="balanced", region_array=[(0, 0)]):
        """
        Set auto exposure regions

        :param region_type: string
        :param region_array: List of Tuples
                            (only needed for region_type = custom)
        """

        types = {
            "balanced": 0,
            "center based": 1,
            "corner based": 2,
            "full": 3,
            "custom": 4,
        }

        array_length = len(region_array)
        x0_array, y0_array = zip(*region_array)

        wRegionType = types[region_type]
        wRoiX0Arr = (C.c_uint16 * array_length)(*x0_array)
        wRoiY0Arr = (C.c_uint16 * array_length)(*y0_array)

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderSetAutoExpRegions(
            self.recorder_handle,
            self.camera_handle,
            wRegionType,
            wRoiX0Arr,
            wRoiY0Arr,
            array_length,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.14 PCO_RecorderSetCompressionParams
    # -------------------------------------------------------------------------
    def set_compression_params(
        self, compr_param
    ):
        """
        Set parameter for compression mode

        :param compr_param: dict()
        """

        parameter = PCO_RECORDER_COMPRESSION_PARAMETER()

        parameter.dGainK = C.c_double(compr_param['gain'])
        parameter.dDarkNoise_e = C.c_double(compr_param['dark noise'])
        parameter.dDSNU_e = C.c_double(compr_param['dsnu'])
        parameter.dPRNU_pct = C.c_double(compr_param['prnu'])
        parameter.dLightSourceNoise_pct = C.c_double(compr_param['light noise'])

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderSetCompressionParams(
            self.recorder_handle, self.camera_handle, parameter
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.15 PCO_RecorderGetStatus
    # -------------------------------------------------------------------------
    def get_status(self):
        """
        Get status of recorder
        """
        bIsRunning = C.c_bool()
        bAutoExpState = C.c_bool()
        dwLastError = C.c_uint32()
        dwProcImgCount = C.c_uint32()
        dwReqImgCount = C.c_uint32()
        bBuffersFull = C.c_bool()
        bFIFOOverflow = C.c_bool()
        dwStartTime = C.c_uint32()
        dwStopTime = C.c_uint32()

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderGetStatus(
            self.recorder_handle,
            self.camera_handle,
            bIsRunning,
            bAutoExpState,
            dwLastError,
            dwProcImgCount,
            dwReqImgCount,
            bBuffersFull,
            bFIFOOverflow,
            dwStartTime,
            dwStopTime,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"is running": bIsRunning.value})
            ret.update({"bIsRunning": bIsRunning.value})
            ret.update({"bAutoExpState": bAutoExpState.value})
            ret.update({"dwLastError": dwLastError.value})
            ret.update({"dwProcImgCount": dwProcImgCount.value})
            ret.update({"dwReqImgCount": dwReqImgCount.value})
            ret.update({"bBuffersFull": bBuffersFull.value})
            ret.update({"bFIFOOverflow": bFIFOOverflow.value})
            ret.update({"dwStartTime": dwStartTime.value})
            ret.update({"dwStopTime": dwStopTime.value})

        logger.debug("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.16 PCO_RecorderGetImageAddress
    # -------------------------------------------------------------------------
    def get_image_address(self, index, x0, y0, x1, y1):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.17 PCO_RecorderCopyImage
    # -------------------------------------------------------------------------

    def copy_image(self, index, x0, y0, x1, y1):
        """
        Copy image from index of recorder memory

        :param index: image index
        :param x0, y0, x1, y1: roi of image

        :return: dict of 'image', 'metadata', 'timestamp'
        """
        image = (C.c_uint16 * (((x1 - x0) + 1) * ((y1 - y0) + 1)))()
        p_wImgBuf = C.cast(image, C.POINTER(C.c_uint16))
        dwImgNumber = C.c_uint32()
        metadata = PCO_METADATA_STRUCT()
        metadata.wSize = C.sizeof(PCO_METADATA_STRUCT)
        timestamp = PCO_TIMESTAMP_STRUCT()
        timestamp.wSize = C.sizeof(PCO_TIMESTAMP_STRUCT)

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderCopyImage(
            self.recorder_handle,
            self.camera_handle,
            index,
            x0,
            y0,
            x1,
            y1,
            p_wImgBuf,
            dwImgNumber,
            metadata,
            timestamp,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            timestamp_dict = {
                "image_counter": timestamp.dwImgCounter,
                "year": timestamp.wYear,
                "month": timestamp.wMonth,
                "day": timestamp.wDay,
                "hour": timestamp.wHour,
                "minute": timestamp.wMinute,
                "second": (timestamp.wSecond + (timestamp.dwMicroSeconds / 1e6)),
                "status": 0
            }

            if any(timestamp_dict.values()):
                pass
            else:
                timestamp_dict.clear()

            # timebase = {"ms": 1e-3, "us": 1e-6, "ns": 1e-9}
            timebase = {0: 1e-3, 1: 1e-6, 2: 1e-9}
            meta_dict = {
                "version": metadata.wVersion,
                "exposure time": metadata.dwEXPOSURE_TIME * timebase[metadata.wEXPOSURE_TIME_BASE],
                "framerate": metadata.dwFRAMERATE_MILLIHZ / 1e3,
                "sensor temperature": metadata.sSENSOR_TEMPERATURE,
                "pixel clock": metadata.dwSENSOR_READOUT_FREQUENCY,
                "conversion factor": metadata.wSENSOR_CONV_FACTOR,
                "serial number": metadata.dwCAMERA_SERIAL_NO,
                "camera type": metadata.wCAMERA_TYPE,
                "bit resolution": metadata.bBIT_RESOLUTION,
                "sync status": metadata.bSYNC_STATUS,
                "dark offset": metadata.wDARK_OFFSET,
                "trigger mode": metadata.bTRIGGER_MODE,
                "double image mode": metadata.bDOUBLE_IMAGE_MODE,
                "camera sync mode": metadata.bCAMERA_SYNC_MODE,
                "image type": metadata.bIMAGE_TYPE,
                "color pattern": metadata.wCOLOR_PATTERN,
            }

            # to preserve any() to indicate meta data
            if any(meta_dict.values()):
                meta_dict.update({
                    "image size": (metadata.wIMAGE_SIZE_X, metadata.wIMAGE_SIZE_Y),
                    "binning": (metadata.bBINNING_X, metadata.bBINNING_Y)
                })

                if metadata.wVersion > 1:
                    meta_dict.update({"camera subtype": metadata.wCAMERA_SUBTYPE})
                    meta_dict.update({"event number": metadata.dwEVENT_NUMBER})
                    meta_dict.update({"image size offset": (
                        metadata.wIMAGE_SIZE_X_Offset, metadata.wIMAGE_SIZE_Y_Offset)})

                meta_dict.update({"timestamp bcd": {
                    "image counter": 1e6 * self.__bcd_to_decimal(metadata.bIMAGE_COUNTER_BCD[0]) +
                    1e4 * self.__bcd_to_decimal(metadata.bIMAGE_COUNTER_BCD[1]) +
                    1e2 * self.__bcd_to_decimal(metadata.bIMAGE_COUNTER_BCD[2]) +
                    1e0 * self.__bcd_to_decimal(metadata.bIMAGE_COUNTER_BCD[3]),
                    "seconds": self.__bcd_to_decimal(metadata.bIMAGE_TIME_SEC_BCD) +
                    1e-2 * self.__bcd_to_decimal(metadata.bIMAGE_TIME_US_BCD[0]) +
                    1e-4 * self.__bcd_to_decimal(metadata.bIMAGE_TIME_US_BCD[1]) +
                    1e-6 * self.__bcd_to_decimal(metadata.bIMAGE_TIME_US_BCD[2]),
                    "minute": self.__bcd_to_decimal(metadata.bIMAGE_TIME_MIN_BCD),
                    "hour": self.__bcd_to_decimal(metadata.bIMAGE_TIME_HOUR_BCD),
                    "day": self.__bcd_to_decimal(metadata.bIMAGE_TIME_DAY_BCD),
                    "month": self.__bcd_to_decimal(metadata.bIMAGE_TIME_MON_BCD),
                    "year": self.__bcd_to_decimal(metadata.bIMAGE_TIME_YEAR_BCD) + 2000,
                    "status": self.__bcd_to_decimal(metadata.bIMAGE_TIME_STATUS)
                }})

            else:
                meta_dict.clear()

            ret.update({"recorder image number": dwImgNumber.value})
            ret.update({"timestamp": timestamp_dict})
            ret.update({"metadata": meta_dict})

            ret.update({"image": image})

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            warnings.warn("Did you wait for the first image in buffer?")
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.18 PCO_RecorderCopyAverageImage
    # -------------------------------------------------------------------------
    def copy_average_image(self, start, stop, x0, y0, x1, y1):
        """
        Copy averaged image over multiple images from recorder memory

        :param start, stop: indices of recorder images
        :param x0, y0, x1, y1: roi of image

        :return: dict of 'image', 'metadata', 'timestamp'
        """

        image = (C.c_uint16 * (((x1 - x0) + 1) * ((y1 - y0) + 1)))()
        p_wImgBuf = C.cast(image, C.POINTER(C.c_uint16))
        dwStartIdx = C.c_uint32(start)
        dwStopIdx = C.c_uint32(stop)
        wRoiX0 = C.c_uint16(x0)
        wRoiY0 = C.c_uint16(y0)
        wRoiX1 = C.c_uint16(x1)
        wRoiY1 = C.c_uint16(y1)

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderCopyAverageImage(
            self.recorder_handle,
            self.camera_handle,
            dwStartIdx,
            dwStopIdx,
            wRoiX0,
            wRoiY0,
            wRoiX1,
            wRoiY1,
            p_wImgBuf,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"average image": image})

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.19 PCO_RecorderCopyImageCompressed
    # -------------------------------------------------------------------------
    def copy_image_compressed(self, index, x0, y0, x1, y1):
        """
        Copy compressed image from index of recorder memory. Compression parameter have to be set before

        :param index: image index
        :param x0, y0, x1, y1: roi of image

        :return: dict of 'image', 'metadata', 'timestamp'
        """

        image = (C.c_uint8 * (((x1 - x0) + 1) * ((y1 - y0) + 1)))()
        p_wImgBuf = C.cast(image, C.POINTER(C.c_uint16))
        dwImgNumber = C.c_uint32()
        metadata = PCO_METADATA_STRUCT()
        metadata.wSize = C.sizeof(PCO_METADATA_STRUCT)
        timestamp = PCO_TIMESTAMP_STRUCT()
        timestamp.wSize = C.sizeof(PCO_TIMESTAMP_STRUCT)

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderCopyImageCompressed(
            self.recorder_handle,
            self.camera_handle,
            index,
            x0,
            y0,
            x1,
            y1,
            p_wImgBuf,
            dwImgNumber,
            metadata,
            timestamp,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            timestamp_dict = {
                "image_counter": timestamp.dwImgCounter,
                "year": timestamp.wYear,
                "month": timestamp.wMonth,
                "day": timestamp.wDay,
                "hour": timestamp.wHour,
                "minute": timestamp.wMinute,
                "second": (timestamp.wSecond + (timestamp.dwMicroSeconds / 1e6))
            }

            if any(timestamp_dict.values()):
                pass
            else:
                timestamp_dict.clear()

            # timebase = {"ms": 1e-3, "us": 1e-6, "ns": 1e-9}
            timebase = {0: 1e-3, 1: 1e-6, 2: 1e-9}
            meta_dict = {
                "version": metadata.wVersion,
                "exposure time": metadata.dwEXPOSURE_TIME * timebase[metadata.wEXPOSURE_TIME_BASE],
                "framerate": metadata.dwFRAMERATE_MILLIHZ / 1e3,
                "sensor temperature": metadata.sSENSOR_TEMPERATURE,
                "pixel clock": metadata.dwSENSOR_READOUT_FREQUENCY,
                "conversion factor": metadata.wSENSOR_CONV_FACTOR,
                "serial number": metadata.dwCAMERA_SERIAL_NO,
                "camera type": metadata.wCAMERA_TYPE,
                "bit resolution": metadata.bBIT_RESOLUTION,
                "sync status": metadata.bSYNC_STATUS,
                "dark offset": metadata.wDARK_OFFSET,
                "trigger mode": metadata.bTRIGGER_MODE,
                "double image mode": metadata.bDOUBLE_IMAGE_MODE,
                "camera sync mode": metadata.bCAMERA_SYNC_MODE,
                "image type": metadata.bIMAGE_TYPE,
                "color pattern": metadata.wCOLOR_PATTERN,
            }

            # to preserve any() to indicate meta data
            if any(meta_dict.values()):
                meta_dict.update({
                    "image size": (metadata.wIMAGE_SIZE_X, metadata.wIMAGE_SIZE_Y),
                    "binning": (metadata.bBINNING_X, metadata.bBINNING_Y)
                })

                if metadata.wVersion > 1:
                    meta_dict.update({"camera subtype": metadata.wCAMERA_SUBTYPE})
                    meta_dict.update({"event number": metadata.dwEVENT_NUMBER})
                    meta_dict.update({"image size offset": (
                        metadata.wIMAGE_SIZE_X_Offset, metadata.wIMAGE_SIZE_Y_Offset)})

                meta_dict.update({"timestamp bcd": {
                    "image counter": 1e6 * self.__bcd_to_decimal(metadata.bIMAGE_COUNTER_BCD[0]) +
                    1e4 * self.__bcd_to_decimal(metadata.bIMAGE_COUNTER_BCD[1]) +
                    1e2 * self.__bcd_to_decimal(metadata.bIMAGE_COUNTER_BCD[2]) +
                    1e0 * self.__bcd_to_decimal(metadata.bIMAGE_COUNTER_BCD[3]),
                    "seconds": self.__bcd_to_decimal(metadata.bIMAGE_TIME_SEC_BCD) +
                    1e-2 * self.__bcd_to_decimal(metadata.bIMAGE_TIME_US_BCD[0]) +
                    1e-4 * self.__bcd_to_decimal(metadata.bIMAGE_TIME_US_BCD[1]) +
                    1e-6 * self.__bcd_to_decimal(metadata.bIMAGE_TIME_US_BCD[2]),
                    "minute": self.__bcd_to_decimal(metadata.bIMAGE_TIME_MIN_BCD),
                    "hour": self.__bcd_to_decimal(metadata.bIMAGE_TIME_HOUR_BCD),
                    "day": self.__bcd_to_decimal(metadata.bIMAGE_TIME_DAY_BCD),
                    "month": self.__bcd_to_decimal(metadata.bIMAGE_TIME_MON_BCD),
                    "year": self.__bcd_to_decimal(metadata.bIMAGE_TIME_YEAR_BCD) + 2000,
                    "status": self.__bcd_to_decimal(metadata.bIMAGE_TIME_STATUS)
                }})

            else:
                meta_dict.clear()

            ret.update({"recorder image number": dwImgNumber.value})
            ret.update({"timestamp": timestamp_dict})
            ret.update({"metadata": meta_dict})

            ret.update({"image": image})

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.20 PCO_RecorderExportImage
    # -------------------------------------------------------------------------

    def export_image(self, index, file_path, overwrite=True):
        """
        Export the selected image for the selected camera to the selected file path
        Allowed are only raw image formats, i.e. b16, tif, dcm
        """

        parameter = PCO_RECORDER_COMPRESSION_PARAMETER()

        dwImgIdx = C.c_uint32(index)
        szFilePath = C.c_char_p(file_path.encode("utf-8"))
        bOverwrite = C.c_bool(overwrite)

        time_start = time.perf_counter()
        error = self.PCO_Recorder.PCO_RecorderExportImage(
            self.recorder_handle, self.camera_handle, dwImgIdx, szFilePath, bOverwrite
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [rec] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))
