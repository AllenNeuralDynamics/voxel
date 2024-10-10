# -*- coding: utf-8 -*-
"""
This module wraps the pco.convert to python data structures.

Copyright @ Excelitas PCO GmbH 2005-2023

Instances of the Convert class are part of pco.Camera
"""

import sys
import os
import ctypes as C
import logging
import time
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class SRGBCOLCORRCOEFF(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("da11", C.c_double),
        ("da12", C.c_double),
        ("da13", C.c_double),
        ("da21", C.c_double),
        ("da22", C.c_double),
        ("da23", C.c_double),
        ("da31", C.c_double),
        ("da32", C.c_double),
        ("da33", C.c_double),
    ]


class PCO_Display(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wScale_minmax", C.c_uint16),
        ("iScale_maxmax", C.c_int),
        ("iScale_min", C.c_int),
        ("iScale_max", C.c_int),
        ("iColor_temp", C.c_int),
        ("iColor_tint", C.c_int),
        ("iColor_saturation", C.c_int),
        ("iColor_vibrance", C.c_int),
        ("iContrast", C.c_int),
        ("iGamma", C.c_int),
        ("iSRGB", C.c_int),
        ("pHistogramData", C.c_void_p),
        ("dwDialogOpenFlags", C.c_uint32),
        ("dwProcessingFlags", C.c_uint32),
        ("wProzValue4Min", C.c_uint16),
        ("wProzValue4Max", C.c_uint16),
        ("dwzzDummy1", C.c_uint32 * 49),
    ]


class PCO_Bayer(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wDummy", C.c_uint16),
        ("iKernel", C.c_int),
        ("iColorMode", C.c_int),
        ("dwzzDummy1", C.c_uint32 * 61),
    ]


class PCO_Filter(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wDummy", C.c_uint16),
        ("iMode", C.c_int),
        ("iType", C.c_int),
        ("iSharpen", C.c_int),
        ("dwzzDummy1", C.c_uint32 * 60),
    ]


class PCO_SensorInfo(C.Structure):
    _pack_ = 8
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wDummy", C.c_uint16),
        ("iConversionFactor", C.c_int),
        ("iDataBits", C.c_int),
        ("iSensorInfoBits", C.c_int),
        ("iDarkOffset", C.c_int),
        ("dwzzDummy0", C.c_uint32),
        ("strColorCoeff", SRGBCOLCORRCOEFF),
        ("iCamNum", C.c_int),
        ("hCamera", C.c_void_p),
        ("dwzzDummy1", C.c_uint32 * 38),
    ]


class PCO_Convert(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wDummy", C.c_uint16 * 3),
        ("str_Display", PCO_Display),
        ("str_Bayer", PCO_Bayer),
        ("str_Filter", PCO_Filter),
        ("str_SensorInfo", PCO_SensorInfo),
        ("iData_Bits_Out", C.c_int),
        ("dwModeBitsDataOut", C.c_uint32),
        ("iGPU_Processing_mode", C.c_int),
        ("iConvertType", C.c_int),
        ("szConvertInfo", C.c_char * 60),
        ("dwConvertCAPS", C.c_uint32),
        ("dwzzDummy1", C.c_uint32 * 42),
    ]


class Convert:
    def __init__(self, camera_handle, sdk, convert_type, bit_resolution):
        if sys.platform.startswith('win32'):
            self.__dll_name = "pco_conv.dll"
        elif sys.platform.startswith('linux'):
            self.__dll_name = "libpco_convert.so.1"
        else:
            print("Package not supported on platform " + sys.platform)
            raise SystemError

        dll_path = os.path.dirname(__file__).replace("\\", "/")

        # set working directory
        # workaround, due to implicit load of pco_conv.dll
        current_working_directory = os.getcwd()
        os.chdir(dll_path)

        try:
            if sys.platform.startswith('win32'):
                self.PCO_Convert = C.windll.LoadLibrary(dll_path + "/" + self.__dll_name)
            else:  # if sys.platform.startswith('linux'):
                self.PCO_Convert = C.cdll.LoadLibrary(dll_path + "/" + self.__dll_name)
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
            raise ValueError

        os.chdir(current_working_directory)

        self.convert_handle = C.c_void_p(0)
        self.camera_handle = camera_handle
        self.sdk = sdk

        self.convert_types = {
            "bw": 1,
            "color": 2,
            "pseudo": 3,
            "color16": 4
        }

        self.convert_type = convert_type
        self.bit_resolution = bit_resolution

        try:
            self.convert_types[convert_type]
        except KeyError:
            raise ValueError(f'{"Invalid convert type. Available keys: "}{self.convert_types.keys()}')

        self.convert_ctrl = {  # all types
            "sharpen": True,
            "adaptive_sharpen": True,
            "flip_vertical": False,
            "auto_minmax": True,
            "min_limit": 0,
            "max_limit": 20000,
            "gamma": 1.0,
            "contrast": 0
        }
        if self.convert_type == 'color' or self.convert_type == 'color16':
            self.convert_ctrl.update({
                "pco_debayer_algorithm": False,
                "color_temperature": 6500,
                "color_saturation": 0,
                "color_vibrance": 0,
                "color_tint": 0
            })
            if self.convert_type == 'color':
                self._conv_maxmax = 0
                self._conv_maxmin = 0
                self._conv_minmax = 0

        if self.convert_type == 'pseudo':
            self.convert_ctrl.update({
                "color_temperature": 6500,
                "color_saturation": 0,
                "color_vibrance": 0,
                "color_tint": 0,
                "lut_file": ""
            })

        self.do_auto_minmax = True

        self.PCO_Convert.PCO_ConvertCreate.argtypes = [
            C.POINTER(C.c_void_p),
            C.POINTER(PCO_SensorInfo),
            C.c_int,
        ]

        self.PCO_Convert.PCO_ConvertDelete.argtypes = [
            C.c_void_p,
        ]

        self.PCO_Convert.PCO_ConvertGet.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Convert),
        ]

        self.PCO_Convert.PCO_ConvertSet.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Convert),
        ]

        self.PCO_Convert.PCO_ConvertGetDisplay.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Display),
        ]

        self.PCO_Convert.PCO_ConvertSetDisplay.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Display),
        ]

        self.PCO_Convert.PCO_ConvertSetBayer.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Bayer),
        ]

        self.PCO_Convert.PCO_ConvertSetFilter.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Filter),
        ]

        self.PCO_Convert.PCO_ConvertSetSensorInfo.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_SensorInfo),
        ]

        self.PCO_Convert.PCO_SetPseudoLut.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_ubyte),
            C.c_int,
        ]

        self.PCO_Convert.PCO_LoadPseudoLut.argtypes = [
            C.c_void_p,
            C.c_int,
            C.c_char_p,
        ]

        self.PCO_Convert.PCO_Convert16TO8.argtypes = [
            C.c_void_p,
            C.c_int,
            C.c_int,
            C.c_int,
            C.c_int,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint8),
        ]

        self.PCO_Convert.PCO_Convert16TO24.argtypes = [
            C.c_void_p,
            C.c_int,
            C.c_int,
            C.c_int,
            C.c_int,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint8),
        ]

        self.PCO_Convert.PCO_Convert16TOCOL.argtypes = [
            C.c_void_p,
            C.c_int,
            C.c_int,
            C.c_int,
            C.c_int,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint8),
        ]

        self.PCO_Convert.PCO_Convert16TOPSEUDO.argtypes = [
            C.c_void_p,
            C.c_int,
            C.c_int,
            C.c_int,
            C.c_int,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint8),
        ]

        self.PCO_Convert.PCO_Convert16TOCOL16.argtypes = [
            C.c_void_p,
            C.c_int,
            C.c_int,
            C.c_int,
            C.c_int,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.PCO_Convert.PCO_GetWhiteBalance.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_int),
            C.POINTER(C.c_int),
            C.c_int,
            C.c_int,
            C.c_int,
            C.POINTER(C.c_uint16),
            C.c_int,
            C.c_int,
            C.c_int,
            C.c_int,
        ]

        self.PCO_Convert.PCO_GetMaxLimit.argtypes = [
            C.POINTER(C.c_float),
            C.POINTER(C.c_float),
            C.POINTER(C.c_float),
            C.c_float,
            C.c_float,
            C.c_int,
        ]

        self.PCO_Convert.PCO_GetColorValues.argtypes = [
            C.POINTER(C.c_float),
            C.POINTER(C.c_float),
            C.c_int,
            C.c_int,
            C.c_int,
        ]

        self.PCO_Convert.PCO_WhiteBalanceToDisplayStruct.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Display),
            C.c_int,
            C.c_int,
            C.c_int,
            C.POINTER(C.c_uint16),
            C.c_int,
            C.c_int,
            C.c_int,
            C.c_int,
        ]

        self.PCO_Convert.PCO_GetVersionInfoPCO_CONV.argtypes = [
            C.c_char_p,
            C.c_int,
            C.c_char_p,
            C.c_int,
            C.POINTER(C.c_int),
            C.POINTER(C.c_int),
            C.POINTER(C.c_int),
        ]

    def __str__(self) -> str:
        return self.convert_type

    def get_error_text(self, error):
        return self.sdk.get_error_text(error)

    # -------------------------------------------------------------------------
    def _get_color_mode(self, color_pattern, offset_x, offset_y):

        color_mode = 0
        for i in range(4):
            if ((color_pattern >> (4 * i)) & 0x000F) == 1:
                color_mode = i
                break

        if offset_x % 2:
            color_mode += 1

        if offset_y % 2:
            color_mode += 2

        return color_mode % 4

    def get_mode_flags(self, with_alpha=False):
        conv_ctrl = self.convert_ctrl
        mode = 0x1000  # CONVERT_MODE_EXT_FILTER_FLAGS
        if with_alpha:
            mode |= 0x0100  # CONVERT_MODE_OUT_RGB32
        if conv_ctrl["sharpen"]:
            mode |= 0x00100000  # CONVERT_MODE_OUT_DOSHARPEN
        if conv_ctrl["adaptive_sharpen"]:
            mode |= 0x00200000  # CONVERT_MODE_OUT_DOADSHARPEN
        if conv_ctrl["flip_vertical"]:
            mode |= 0x0001  # CONVERT_MODE_OUT_FLIPIMAGE
        if "pco_debayer_algorithm" in conv_ctrl and conv_ctrl["pco_debayer_algorithm"]:
            mode |= 0x00400000  # CONVERT_MODE_OUT_DOPCODEBAYER

        if conv_ctrl["auto_minmax"]:
            mode |= 0x00000020  # CONVERT_MODE_OUT_AUTOMINMAX

        return mode

    # -------------------------------------------------------------------------
    # 2.1 PCO_ConvertCreate
    # -------------------------------------------------------------------------
    def create(self, data_bits, offset, ccm, sensor_info_bits):
        """
        Creates a new convert object based on the PCO_SensorInfo structure.
        The created convert handle will be used during the conversion. Please
        call PCO_ConvertDelete before the application exits and unloads the
        convert dll.
        """

        self.convert_handle = C.c_void_p(0)

        strSensorInfo = PCO_SensorInfo()
        strSensorInfo.wSize = C.sizeof(PCO_SensorInfo)
        strSensorInfo.iConversionFactor = 0
        strSensorInfo.iDataBits = data_bits
        strSensorInfo.iSensorInfoBits = sensor_info_bits
        strSensorInfo.iDarkOffset = offset

        strSensorInfo.strColorCoeff.da11 = ccm[0]
        strSensorInfo.strColorCoeff.da12 = ccm[1]
        strSensorInfo.strColorCoeff.da13 = ccm[2]
        strSensorInfo.strColorCoeff.da21 = ccm[3]
        strSensorInfo.strColorCoeff.da22 = ccm[4]
        strSensorInfo.strColorCoeff.da23 = ccm[5]
        strSensorInfo.strColorCoeff.da31 = ccm[6]
        strSensorInfo.strColorCoeff.da32 = ccm[7]
        strSensorInfo.strColorCoeff.da33 = ccm[8]

        strSensorInfo.iCamNum = 0

        strSensorInfo.hCamera = self.camera_handle

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_ConvertCreate(
            self.convert_handle,
            strSensorInfo,
            C.c_int(self.convert_types[self.convert_type])
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if self.convert_type == 'color':
          self.__check_minmax_scale()
        self.__update_display_settings()

        if error:
            # print("Error: {:08x}".format(error & (2**32 - 1)))
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.2 PCO_ConvertDelete
    # -------------------------------------------------------------------------
    def delete(self):
        """
        Deletes a previously created convert object. It is mandatory to call
        this function before closing the application.
        """

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_ConvertDelete(self.convert_handle)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        self.convert_handle = C.c_void_p(0)

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.3 PCO_ConvertG(S)et
    # -------------------------------------------------------------------------
    def get(self):
        raise NotImplementedError

    def set(self):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.4 PCO_ConvertG(S)etDisplay
    # -------------------------------------------------------------------------
    def get_display(self):
        """
        Get display structure
        """

        pstrDisplay = PCO_Display()
        pstrDisplay.wSize = C.sizeof(PCO_Display)

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_ConvertGetDisplay(self.convert_handle, pstrDisplay)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update(
                {
                    "scale_minmax": pstrDisplay.wScale_minmax,
                    "scale_maxmax": pstrDisplay.iScale_maxmax,
                    "scale_min": pstrDisplay.iScale_min,
                    "scale_max": pstrDisplay.iScale_max,
                    "color_temp": pstrDisplay.iColor_temp,
                    "color_tint": pstrDisplay.iColor_tint,
                    "color_saturation": pstrDisplay.iColor_saturation,
                    "color_vibrance": pstrDisplay.iColor_vibrance,
                    "contrast": pstrDisplay.iContrast,
                    "gamma": float(pstrDisplay.iGamma) / 100.0,
                    "is_rgb": pstrDisplay.iSRGB,
                    "processing_flags": pstrDisplay.dwProcessingFlags,
                    "proz_value_4_min": pstrDisplay.wProzValue4Min,
                    "proz_value_4_max": pstrDisplay.wProzValue4Max,
                }
            )

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    def set_display(self,
                    scale_min,
                    scale_max,
                    color_temp=6500,
                    color_tint=0,
                    color_saturation=0,
                    color_vibrance=0,
                    contrast=0,
                    gamma=1,
                    is_rgb=0,
                    processing_flags=0,
                    proz_value_4_min=0,
                    proz_value_4_max=100):
        """
        Set display structure
        """

        strDisplay = PCO_Display()
        strDisplay.wSize = C.sizeof(PCO_Display)

        strDisplay.iScale_min = C.c_int(scale_min)
        strDisplay.iScale_max = C.c_int(scale_max)
        strDisplay.iColor_temp = C.c_int(color_temp)
        strDisplay.iColor_tint = C.c_int(color_tint)
        strDisplay.iColor_saturation = C.c_int(color_saturation)
        strDisplay.iColor_vibrance = C.c_int(color_vibrance)
        strDisplay.iContrast = C.c_int(contrast)
        strDisplay.iGamma = C.c_int(int(gamma * 100.0))
        strDisplay.iSRGB = C.c_int(is_rgb)
        strDisplay.dwProcessingFlags = C.c_uint32(processing_flags)
        strDisplay.wProzValue4Min = C.c_uint16(proz_value_4_min)
        strDisplay.wProzValue4Max = C.c_uint16(proz_value_4_max)

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_ConvertSetDisplay(self.convert_handle, strDisplay)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    def get_control_properties(self):
        """
        updates convert_ctrl properties with display settings

        :return: convert_control
        :rtype: dict
        """
        display = self.get_display()

        if self.convert_type == "bw":
            self.convert_ctrl.update(
                {
                    "gamma": display["gamma"],
                    "contrast": display["contrast"],
                    "min_limit": display["scale_min"],
                    "max_limit": display["scale_max"]
                }
            )
        else:
            self.convert_ctrl.update(
                {
                    "gamma": display["gamma"],
                    "contrast": display["contrast"],
                    "min_limit": display["scale_min"],
                    "max_limit": display["scale_max"],
                    "color_temperature": display["color_temp"],
                    "color_saturation": display["color_saturation"],
                    "color_vibrance": display["color_vibrance"],
                    "color_tint": display["color_tint"],
                }
            )
        return self.convert_ctrl

    def set_control_properties(self, convert_ctrl):
        if self.convert_type == "pseudo":
            if "lut_file" in convert_ctrl:
                if not Path(convert_ctrl["lut_file"]).is_file():
                    ValueError("Lut file does not exist ({})".format(convert_ctrl["lut_file"]))

                lut_extension = Path(convert_ctrl["lut_file"]).suffix
                lut_format = 1
                if lut_extension == ".lt1":
                    lut_format = 3
                elif lut_extension == ".lt2":
                    lut_format = 2
                elif lut_extension == ".lt3":
                    lut_format = 1
                elif lut_extension == ".lt4":
                    lut_format = 0

                self.load_pseudo_lut(lut_format, convert_ctrl["lut_file"])

        self.convert_ctrl = convert_ctrl

        if self.convert_type == 'color':
            self.__check_minmax_scale()
        self.__update_display_settings()

    # -------------------------------------------------------------------------
    # 2.5 PCO_ConvertSetBayer
    # -------------------------------------------------------------------------

    def set_bayer(self, kernel, color_mode):
        """
        Set bayer structure
        """

        strBayer = PCO_Bayer()
        strBayer.wSize = C.sizeof(PCO_Bayer)

        strBayer.iKernel = kernel
        strBayer.iColorMode = color_mode

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_ConvertSetBayer(self.convert_handle, strBayer)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.6 PCO_ConvertSetFilter
    # -------------------------------------------------------------------------
    def set_filter(self, filter_mode, filter_type, sharpen):
        """
        Set filter structure
        """

        strFilter = PCO_Filter()
        strFilter.wSize = C.sizeof(PCO_Filter)

        strFilter.iMode = filter_mode
        strFilter.iType = filter_type
        strFilter.iSharpen = sharpen

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_ConvertSetFilter(self.convert_handle, strFilter)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.7 PCO_ConvertSetSensorInfo
    # -------------------------------------------------------------------------
    def set_sensor_info(self, data_bits, offset, ccm, sensor_info_bits):
        """
        Set sensor info structure
        """

        strSensorInfo = PCO_SensorInfo()
        strSensorInfo.wSize = C.sizeof(PCO_SensorInfo)

        strSensorInfo.iConversionFactor = 0
        strSensorInfo.iDataBits = data_bits
        strSensorInfo.iSensorInfoBits = sensor_info_bits
        strSensorInfo.iDarkOffset = offset

        strSensorInfo.strColorCoeff.da11 = ccm[0]
        strSensorInfo.strColorCoeff.da12 = ccm[1]
        strSensorInfo.strColorCoeff.da13 = ccm[2]
        strSensorInfo.strColorCoeff.da21 = ccm[3]
        strSensorInfo.strColorCoeff.da22 = ccm[4]
        strSensorInfo.strColorCoeff.da23 = ccm[5]
        strSensorInfo.strColorCoeff.da31 = ccm[6]
        strSensorInfo.strColorCoeff.da32 = ccm[7]
        strSensorInfo.strColorCoeff.da33 = ccm[8]

        strSensorInfo.iCamNum = 0
        strSensorInfo.hCamera = self.camera_handle

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_ConvertSetSensorInfo(self.convert_handle, strSensorInfo)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.8 PCO_SetPseudoLut
    # -------------------------------------------------------------------------
    def set_pseudo_lut(self, lut, color_channels=3):
        """
        load the three pseudolut color tables of plut

        plut:   PSEUDOLUT to write data in
        inumcolors: 3: RGB; 4: 32bit RGBA
        """

        pseudo_lut = lut.ctypes.data_as(C.POINTER(C.c_ubyte))
        inumcolors = C.c_uint32(color_channels)

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_SetPseudoLut(self.convert_handle, pseudo_lut, inumcolors)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.9 PCO_LoadPseudoLut
    # -------------------------------------------------------------------------
    def load_pseudo_lut(self, format, file_path):
        """
        load the three pseudolut color tables of plut
        from the file filename
        which includes data in the following formats

        plut:   PSEUDOLUT to write data in
        filename: name of file with data
        format: 0 = binary 256*RGB
                1 = binary 256*R,256*G,256*R
                2 = ASCII  256*RGB
                3 = ASCII  256*R,256*G,256*R
        """
        path = C.c_char_p(file_path.encode("utf-8"))

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_LoadPseudoLut(
            self.convert_handle,
            C.c_int(format),
            path
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.10a PCO_Convert16TO8
    # -------------------------------------------------------------------------
    def convert_16_to_8(self, image, mode_flags, color_pattern, offset_x, offset_y):
        """
        Convert image to 8 bit grayscale
        """

        if mode_flags & 0x00000020:  # CONVERT_MODE_OUT_AUTOMINMAX
            if self.do_auto_minmax:
                self.__set_auto_minmax(image)
                self.do_auto_minmax = False

        color_mode = self._get_color_mode(color_pattern, offset_x, offset_y)

        imode = C.c_int(mode_flags)
        icolormode = C.c_int(color_mode)
        height, width = image.shape
        iwidth = C.c_int(width)
        iheight = C.c_int(height)
        p_image_input = image.ctypes.data_as(C.POINTER(C.c_ushort))

        even_padded_width = width
        if (width % 4) > 0:
            even_padded_width += (4 - (width % 4))
        image_output = (C.c_uint8 * (even_padded_width * height))(0)
        p_image_output = C.cast(image_output, C.POINTER(C.c_uint8))

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_Convert16TO8(
            self.convert_handle,
            imode,
            icolormode,
            iwidth,
            iheight,
            p_image_input,
            p_image_output,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(duration, str(self), sys._getframe().f_code.co_name,
                                                         f'{iwidth.value}{"x"}{iheight.value}'))
        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return np.array(image_output).reshape(height, even_padded_width)[:, 0:width]

    # -------------------------------------------------------------------------
    # 2.10b PCO_Convert16TO24
    # -------------------------------------------------------------------------
    def convert_16_to_24(self, image, mode_flags, color_pattern, offset_x, offset_y):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.10c PCO_Convert16TOCol
    # -------------------------------------------------------------------------
    def convert_16_to_col(self, image, mode_flags, color_pattern, offset_x, offset_y):
        """
        Convert image to 8 bit color
        """

        if mode_flags & 0x00000020:  # CONVERT_MODE_OUT_AUTOMINMAX
            if self.do_auto_minmax:
                self.__set_auto_minmax(image)
                self.do_auto_minmax = False
        
        if self.convert_type == 'color':
            if self.__check_minmax_scale():
                self.__update_display_settings()

        color_mode = self._get_color_mode(color_pattern, offset_x, offset_y)

        imode = C.c_int(mode_flags)
        icolormode = C.c_int(color_mode)
        height, width = image.shape
        p_image_input = image.ctypes.data_as(C.POINTER(C.c_ushort))

        even_padded_width = width
        channels = 3
        CONVERT_MODE_OUT_RGB32 = 0x0100
        if mode_flags & CONVERT_MODE_OUT_RGB32:
            channels = 4
            width = even_padded_width
        else:
            if (width % 4) > 0:
                even_padded_width += (4 - (width % 4))

        image_output = (C.c_uint8 * (even_padded_width * height * channels))()
        p_image_output = C.cast(image_output, C.POINTER(C.c_uint8))

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_Convert16TOCOL(
            self.convert_handle,
            imode,
            icolormode,
            C.c_int(width),
            C.c_int(height),
            p_image_input,
            p_image_output,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(duration, str(self), sys._getframe().f_code.co_name,
                                                         f'{width}{"x"}{height}{"x"}{channels}'))
        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return np.array(image_output).reshape(height, even_padded_width, channels)[:, 0:width, :]

    # -------------------------------------------------------------------------
    # 2.10d PCO_Convert16TOPseudo
    # -------------------------------------------------------------------------
    def convert_16_to_pseudo(self, image, mode_flags, color_pattern, offset_x, offset_y):
        """
        Convert image to 8 bit pseudo color
        """

        if mode_flags & 0x00000020:  # CONVERT_MODE_OUT_AUTOMINMAX
            if self.do_auto_minmax:
                self.__set_auto_minmax(image)
                self.do_auto_minmax = False

        color_mode = self._get_color_mode(color_pattern, offset_x, offset_y)

        imode = C.c_int(mode_flags)
        icolormode = C.c_int(color_mode)
        height, width = image.shape
        p_image_input = image.ctypes.data_as(C.POINTER(C.c_ushort))

        even_padded_width = width
        channels = 3
        CONVERT_MODE_OUT_RGB32 = 0x0100
        if mode_flags & CONVERT_MODE_OUT_RGB32:
            channels = 4
            width = even_padded_width
        else:
            if (width % 4) > 0:
                even_padded_width += (4 - (width % 4))

        image_output = (C.c_uint8 * (even_padded_width * height * channels))()
        p_image_output = C.cast(image_output, C.POINTER(C.c_uint8))

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_Convert16TOPSEUDO(
            self.convert_handle,
            imode,
            icolormode,
            C.c_int(width),
            C.c_int(height),
            p_image_input,
            p_image_output,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(duration, str(self), sys._getframe().f_code.co_name,
                                                         f'{width}{"x"}{height}{"x"}{channels}'))
        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return np.array(image_output).reshape(height, even_padded_width, channels)[:, 0:width, :]

    # -------------------------------------------------------------------------
    # 2.10e PCO_Convert16TOCol16
    # -------------------------------------------------------------------------
    def convert_16_to_col16(self, image, mode_flags, color_pattern, offset_x, offset_y):
        """
        Convert image to 16bit color
        """

        if mode_flags & 0x00000020:  # CONVERT_MODE_OUT_AUTOMINMAX
            if self.do_auto_minmax:
                self.__set_auto_minmax(image)
                self.do_auto_minmax = False

        color_mode = self._get_color_mode(color_pattern, offset_x, offset_y)

        imode = C.c_int(mode_flags)
        icolormode = C.c_int(color_mode)
        height, width = image.shape
        p_image_input = image.ctypes.data_as(C.POINTER(C.c_ushort))

        # image_output = (C.c_uint8 * (width * height * 2 * 3))()
        # p_image_output = C.cast(image_output, C.POINTER(C.c_uint8))

        image_output = (C.c_uint16 * (width * height * 3))()
        p_image_output = C.cast(image_output, C.POINTER(C.c_uint16))

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_Convert16TOCOL16(
            self.convert_handle,
            imode,
            icolormode,
            C.c_int(width),
            C.c_int(height),
            p_image_input,
            p_image_output,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(duration, str(self), sys._getframe().f_code.co_name,
                                                         f'{width}{"x"}{height}{"x"}{3}'))
        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return np.array(image_output).reshape(height, width, 3)

    # -------------------------------------------------------------------------
    # 2.11 PCO_GetWhiteBalance
    # -------------------------------------------------------------------------
    def get_white_balance(self, image, roi=None):
        """
        gets white balanced values for color_temp and tint
        color_temp: int pointer to get the calculated color temperature
        tint: int pointer to get the calculated tint value
        mode:   0       = normal
                bit0: 1 = flip
                bit1: 1 = mirror
        width:  width of picture
        height: height of picture
        gb12:    pointer to raw picture data array
        x_m..: rectangle to set the image region to be used for calculation
        """

        image_mode = 0
        image_height, image_width = image.shape

        if roi is None:
            roi = (1, 1, image_width, image_height)

        if (roi[2] - roi[0] + 1 > image_width or roi[3] - roi[1] + 1 > image_height):
            raise ValueError("Roi is too large")

        color_temp = C.c_int()
        tint = C.c_int()
        p_image_input = image.ctypes.data_as(C.POINTER(C.c_ushort))
        mode = C.c_int(image_mode)
        width = C.c_int(image_width)
        height = C.c_int(image_height)
        x_min = C.c_int(roi[0])
        y_min = C.c_int(roi[1])
        x_max = C.c_int(roi[2])
        y_max = C.c_int(roi[3])

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_GetWhiteBalance(
            self.convert_handle, color_temp, tint, mode, width, height, p_image_input, x_min, y_min, x_max, y_max)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            ret.update(
                {
                    "color_temp": color_temp.value,
                    "color_tint": tint.value,
                }
            )

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.12 PCO_GetMaxLimit
    # -------------------------------------------------------------------------
    def get_max_limit(self, bit_range):
        """
        GetMaxLimit gets the RGB values for a given temp and tint. The max value within the convert
        control dialog must not exceed the biggest value of the RGB values, e.g. in case R is the biggest
        value, the max value can increase till the R value hits the bit resolution (4095). Same condition
        must be met for decreasing the max value, e.g. in case B is the lowest value, the max value
        can decrease till the B value hits the min value.
        Usual:   ....min....B..max.G...R...4095(12bit), with max = R+G+B/3
        Increase:....min.......B..max.G...R4095 -> max condition, R hits 4095
        Decrease:....minB..max.G...R.......4095 -> min condition, B hits min
        the values can be used to calculate the maximum values for scale_min and scale_max in the convert control
        fmax = max(r_max,g_max,b_max)
        fmin = min(r_max,g_max,b_max)
        flimit = (float)((1 <<  m_strConvertNew.str_SensorInfo.iDataBits) - 1)
        imaxmax = (int)(flimit / fmax);
        iminmax = (int)(fmin * flimit / fmax);
        r_max,g_max,b_max: float pointer to get the multiplicators
        color_temp: color temperature to be used for calculation
        color_tint: tint value to be used for calculation
        bit_range: bit range of raw data
        """
        if self.convert_type != 'color':
            raise ValueError("Max Limits only exists for color types")

        r_max = C.c_float()
        g_max = C.c_float()
        b_max = C.c_float()
        temp = C.c_float(self.convert_ctrl["color_temperature"])
        tint = C.c_float(self.convert_ctrl["color_tint"])

        output_bits = C.c_int(bit_range)

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_GetMaxLimit(r_max, g_max, b_max, temp, tint, output_bits)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            ret.update(
                {
                    "r_max": r_max.value,
                    "g_max": g_max.value,
                    "b_max": b_max.value,
                }
            )

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.13 PCO_GetColorValues
    # -------------------------------------------------------------------------

    def get_color_values(self, r_max, g_max, b_max):
        """
        get color values from rgb data
        """

        pfColorTemp = C.c_float()
        pfColorTint = C.c_float()
        iRedMax = C.c_int(r_max)
        iGreenMax = C.c_int(g_max)
        iBlueMax = C.c_int(b_max)

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_GetColorValues(pfColorTemp, pfColorTint, iRedMax, iGreenMax, iBlueMax)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            ret.update(
                {
                    "color_temp": pfColorTemp.value,
                    "color_tint": pfColorTint.value,
                }
            )

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.14 PCO_WhiteBalanceToDisplayStruct
    # -------------------------------------------------------------------------

    def white_balance_to_display_struct(self, image, roi=None):
        """
         Calculates the white balance and sets the values to the strDisplay struct while maintaining the limits
         Gets the struct strDisplay from the convert Handle internally.
        mode:   0       = normal
                bit0: 1 = flip
                bit1: 1 = mirror
        width:  width of picture
        height: height of picture
        gb12:    pointer to raw picture data array
        x_m..: rectangle to set the image region to be used for calculation
        """

        image_mode = 0
        image_height, image_width = image.shape

        if roi is None:
            roi = (1, 1, image_width, image_height)

        if (roi[2] - roi[0] + 1 > image_width or roi[3] - roi[1] + 1 > image_height):
            raise ValueError("Roi is too large")


        pstrDisplay = PCO_Display()
        pstrDisplay.wSize = C.sizeof(PCO_Display)
        p_image_input = image.ctypes.data_as(C.POINTER(C.c_ushort))
        mode = C.c_int(image_mode)
        width = C.c_int(image_width)
        height = C.c_int(image_height)
        x_min = C.c_int(roi[0])
        y_min = C.c_int(roi[1])
        x_max = C.c_int(roi[2])
        y_max = C.c_int(roi[3])

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_WhiteBalanceToDisplayStruct(
            self.convert_handle, pstrDisplay, mode, width, height, p_image_input, x_min, y_min, x_max, y_max)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update(
                {
                    "scale_minmax": pstrDisplay.wScale_minmax,
                    "scale_maxmax": pstrDisplay.iScale_maxmax,
                    "scale_min": pstrDisplay.iScale_min,
                    "scale_max": pstrDisplay.iScale_max,
                    "color_temp": pstrDisplay.iColor_temp,
                    "color_tint": pstrDisplay.iColor_tint,
                    "color_saturation": pstrDisplay.iColor_saturation,
                    "color_vibrance": pstrDisplay.iColor_vibrance,
                    "contrast": pstrDisplay.iContrast,
                    "gamma": pstrDisplay.iGamma,
                    "is_rgb": pstrDisplay.iSRGB,
                    "processing_flags": pstrDisplay.dwProcessingFlags,
                    "proz_value_4_min": pstrDisplay.wProzValue4Min,
                    "proz_value_4_max": pstrDisplay.wProzValue4Max,
                }
            )

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.15 PCO_GetVersionInfoPCO_CONV
    # -------------------------------------------------------------------------

    def get_version_info_pco_conv(self):
        """
        Returns the version info about the convert dll
        """

        iMajor = C.c_int()
        iMinor = C.c_int()

        iBuild = C.c_int()

        pszName = C.c_char_p(0)
        iNameLength = C.c_int(0)
        pszPath = C.c_char_p(0)
        iPathLength = C.c_int(0)

        time_start = time.perf_counter()
        error = self.PCO_Convert.PCO_GetVersionInfoPCO_CONV(
            pszName, iNameLength, pszPath, iPathLength, iMajor, iMinor, iBuild)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update(
                {
                    "name": self.__dll_name,
                    "major": iMajor.value,
                    "minor": iMinor.value,
                    "patch": 0,
                    "build": iBuild.value,
                }
            )

        logger.info("[{:5.3f} s] [cnv:{}] {}: {}".format(
            duration, str(self), sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    def __check_minmax_scale(self):
        """
        Sets limit values for color channels. "BGR8" and colored cameras only.

        """
        
        rgb_max = self.get_max_limit(self.bit_resolution)
        col_max = max(rgb_max.values())
        col_min = min(rgb_max.values())

        self._conv_maxmax = int(float(((1 << self.bit_resolution) - 1) / col_max))
        self._conv_maxmin = int(float(self.convert_ctrl["max_limit"]) * col_min)
        self._conv_minmax = self._conv_maxmin

        self._conv_maxmin = self.convert_ctrl["max_limit"] - self._conv_maxmin + self.convert_ctrl["min_limit"]
        if self._conv_minmax < self.convert_ctrl["min_limit"]:
            self._conv_minmax = self.convert_ctrl["min_limit"] + 1
        

        needs_update = False
        if self.convert_ctrl["max_limit"] > self._conv_maxmax:
            self.convert_ctrl["max_limit"] = self._conv_maxmax
            needs_update = True
        if self.convert_ctrl["max_limit"] < self._conv_maxmin:
            self.convert_ctrl["max_limit"] = self._conv_maxmin
            needs_update = True
        if self.convert_ctrl["min_limit"] > self._conv_minmax:
            self.convert_ctrl["min_limit"] = self._conv_minmax
            needs_update = True
        
        return needs_update

    def __update_display_settings(self):
        """
        Update the convert settings of the specified data format

        """
        logger.info("[---.- s] [cam] {}".format(sys._getframe().f_code.co_name))

        display_dict = self.get_display()

        conv_ctrl = self.convert_ctrl

        display_dict["gamma"] = conv_ctrl["gamma"]
        display_dict["contrast"] = conv_ctrl["contrast"]
        if conv_ctrl["auto_minmax"]:
            display_dict["scale_min"] = conv_ctrl["min_limit"]
            display_dict["scale_max"] = conv_ctrl["max_limit"]

        if self.convert_type != "bw":
            display_dict["color_temp"] = conv_ctrl["color_temperature"]
            display_dict["color_saturation"] = conv_ctrl["color_saturation"]
            display_dict["color_vibrance"] = conv_ctrl["color_vibrance"]
            display_dict["color_tint"] = conv_ctrl["color_tint"]

        self.set_display(
            display_dict["scale_min"],
            display_dict["scale_max"],
            display_dict["color_temp"],
            display_dict["color_tint"],
            display_dict["color_saturation"],
            display_dict["color_vibrance"],
            display_dict["contrast"],
            display_dict["gamma"],
            display_dict["is_rgb"],
            display_dict["processing_flags"],
            display_dict["proz_value_4_min"],
            display_dict["proz_value_4_max"]
        )

    def __set_auto_minmax(self, np_image):
        display_dict = self.get_display()
        iMax = np_image.max()
        iMin = np_image.min()

        if (iMin == iMax and iMin != 0):
            iMin -= 1
        display_dict["scale_max"] = iMax
        display_dict["scale_min"] = iMin

        self.set_display(
            display_dict["scale_min"],
            display_dict["scale_max"],
            display_dict["color_temp"],
            display_dict["color_tint"],
            display_dict["color_saturation"],
            display_dict["color_vibrance"],
            display_dict["contrast"],
            display_dict["gamma"],
            display_dict["is_rgb"],
            display_dict["processing_flags"],
            display_dict["proz_value_4_min"],
            display_dict["proz_value_4_max"]
        )
