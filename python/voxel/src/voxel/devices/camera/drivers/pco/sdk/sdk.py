# -*- coding: utf-8 -*-

"""
This module wraps the pco.sdk to python data structures.

Copyright @ Excelitas PCO GmbH 2005-2023

The a instance of the Sdk class is part of pco.Camera
"""
import ctypes as C
import logging
import math
import os
import platform
import sys
import time
import warnings

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class PCO_OpenStruct(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wInterfaceType", C.c_uint16),
        ("wCameraNumber", C.c_uint16),
        ("wCameraNumAtInterface", C.c_uint16),
        ("wOpenFlags", C.c_uint16 * 10),
        ("dwOpenFlags", C.c_uint32 * 5),
        ("wOpenPtr", C.c_void_p * 6),
        ("zzwDummy", C.c_uint16 * 8),
    ]


class PCO_Description(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wSensorTypeDESC", C.c_uint16),
        ("wSensorSubTypeDESC", C.c_uint16),
        ("wMaxHorzResStdDESC", C.c_uint16),
        ("wMaxVertResStdDESC", C.c_uint16),
        ("wMaxHorzResExtDESC", C.c_uint16),
        ("wMaxVertResExtDESC", C.c_uint16),
        ("wDynResDESC", C.c_uint16),
        ("wMaxBinHorzDESC", C.c_uint16),
        ("wBinHorzSteppingDESC", C.c_uint16),
        ("wMaxBinVertDESC", C.c_uint16),
        ("wBinVertSteppingDESC", C.c_uint16),
        ("wRoiHorStepsDESC", C.c_uint16),
        ("wRoiVertStepsDESC", C.c_uint16),
        ("wNumADCsDESC", C.c_uint16),
        ("wMinSizeHorzDESC", C.c_uint16),
        ("dwPixelRateDESC", C.c_uint32 * 4),
        ("ZZdwDummypr", C.c_uint32 * 20),
        ("wConvFactDESC", C.c_uint16 * 4),
        ("sCoolingSetpoints", C.c_short * 10),
        ("ZZdwDummycv", C.c_uint16 * 8),
        ("wSoftRoiHorStepsDESC", C.c_uint16),
        ("wSoftRoiVertStepsDESC", C.c_uint16),
        ("wIRDESC", C.c_uint16),
        ("wMinSizeVertDESC", C.c_uint16),
        ("dwMinDelayDESC", C.c_uint32),
        ("dwMaxDelayDESC", C.c_uint32),
        ("dwMinDelayStepDESC", C.c_uint32),
        ("dwMinExposDESC", C.c_uint32),
        ("dwMaxExposDESC", C.c_uint32),
        ("dwMinExposStepDESC", C.c_uint32),
        ("dwMinDelayIRDESC", C.c_uint32),
        ("dwMaxDelayIRDESC", C.c_uint32),
        ("dwMinExposIRDESC", C.c_uint32),
        ("dwMaxExposIRDESC", C.c_uint32),
        ("wTimeTableDESC", C.c_uint16),
        ("wDoubleImageDESC", C.c_uint16),
        ("sMinCoolSetDESC", C.c_short),
        ("sMaxCoolSetDESC", C.c_short),
        ("sDefaultCoolSetDESC", C.c_short),
        ("wPowerDownModeDESC", C.c_uint16),
        ("wOffsetRegulationDESC", C.c_uint16),
        ("wColorPatternDESC", C.c_uint16),
        ("wPatternTypeDESC", C.c_uint16),
        ("wDummy1", C.c_uint16),
        ("wDummy2", C.c_uint16),
        ("wNumCoolingSetpoints", C.c_uint16),
        ("dwGeneralCapsDESC1", C.c_uint32),
        ("dwGeneralCapsDESC2", C.c_uint32),
        ("dwExtSyncFrequency", C.c_uint32 * 4),
        ("dwGeneralCapsDESC3", C.c_uint32),
        ("dwGeneralCapsDESC4", C.c_uint32),
        ("ZzdwDummy", C.c_uint32),
    ]


class PCO_Description2(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("ZZwAlignDummy1", C.c_uint16),
        ("dwMinPeriodicalTimeDESC2", C.c_uint32),
        ("dwMaxPeriodicalTimeDESC2", C.c_uint32),
        ("dwMinPeriodicalConditionDESC2", C.c_uint32),
        ("dwMaxNumberOfExposuresDESC2", C.c_uint32),
        ("lMinMonitorSignalOffsetDESC2", C.c_long),
        ("dwMaxMonitorSignalOffsetDESC2", C.c_uint32),
        ("dwMinPeriodicalStepDESC2", C.c_uint32),
        ("dwStartTimeDelayDESC2", C.c_uint32),
        ("dwMinMonitorStepDESC2", C.c_uint32),
        ("dwMinDelayModDESC2", C.c_uint32),
        ("dwMaxDelayModDESC2", C.c_uint32),
        ("dwMinDelayStepModDESC2", C.c_uint32),
        ("dwMinExposureModDESC2", C.c_uint32),
        ("dwMaxExposureModDESC2", C.c_uint32),
        ("dwMinExposureStepModDESC2", C.c_uint32),
        ("dwModulateCapsDESC2", C.c_uint32),
        ("dwReserved", C.c_uint32 * 16),
        ("ZZdwDummy", C.c_uint32 * 41),
    ]


class PCO_Description_Intensified(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wChannelNumberIntensifiedDESC", C.c_uint16),
        ("wNumberOfChannelsIntensifiedDESC", C.c_uint16),
        ("wMinVoltageIntensifiedDESC", C.c_uint16),
        ("wMaxVoltageIntensifiedDESC", C.c_uint16),
        ("wVoltageStepIntensifiedDESC", C.c_uint16),
        ("wExtendedMinVoltageIntensifiedDESC", C.c_uint16),
        ("wMaxLoopCountIntensifiedDESC", C.c_uint16),
        ("dwMinPhosphorDecayIntensified_ns_DESC", C.c_uint32),
        ("dwMaxPhosphorDecayIntensified_ms_DESC", C.c_uint32),
        ("dwFlagsIntensifiedDESC", C.c_uint32),
        ("szIntensifierTypeDESC", C.c_char * 24),
        ("dwMCP_RectangleXL_DESC", C.c_uint32),
        ("dwMCP_RectangleXR_DESC", C.c_uint32),
        ("dwMCP_RectangleYT_DESC", C.c_uint32),
        ("dwMCP_RectangleYB_DESC", C.c_uint32),
        ("ZZdwDummy", C.c_uint32 * 23),
    ]


class PCO_Description3(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wDarkOffsetDESC3", C.c_uint16),
        ("dwGeneralCapsDESC5", C.c_uint32),
        ("dwGeneralCapsDESC6", C.c_uint32),
        ("dwGeneralCapsDESC7", C.c_uint32),
        ("dwGeneralCapsDESC8", C.c_uint32),
        ("wMinHorzResStdDESC3", C.c_uint16),
        ("wMinVertResStdDESC3", C.c_uint16),
        ("wMinHorzResExtDESC3", C.c_uint16),
        ("wMinVertResExtDESC3", C.c_uint16),
        ("wPixelsize_horzDESC3", C.c_uint16),
        ("wPixelsize_vertDESC3", C.c_uint16),
        ("sMinSensorTempWarningDESC3", C.c_short),
        ("sMaxSensorTempWarningDESC3", C.c_short),
        ("sMinCameraTempWarningDESC3", C.c_short),
        ("sMaxCameraTempWarningDESC3", C.c_short),
        ("sMinPowerTempWarningDESC3", C.c_short),
        ("sMaxPowerTempWarningDESC3", C.c_short),
        ("wMinPowerVoltageWarningDESC3", C.c_uint16),
        ("wMaxPowerVoltageWarningDESC3", C.c_uint16),
        ("sMinSensorTempErrorDESC3", C.c_short),
        ("sMaxSensorTempErrorDESC3", C.c_short),
        ("sMinCameraTempErrorDESC3", C.c_short),
        ("sMaxCameraTempErrorDESC3", C.c_short),
        ("sMinPowerTempErrorDESC3", C.c_short),
        ("sMaxPowerTempErrorDESC3", C.c_short),
        ("wMinPowerVoltageErrorDESC3", C.c_uint16),
        ("wMaxPowerVoltageErrorDESC3", C.c_uint16),
        ("dwReserved", C.c_uint32 * 32),
    ]


class PCO_SC2_Hardware_DESC(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("szName", C.c_char * 16),
        ("wBatchNo", C.c_uint16),
        ("wRevision", C.c_uint16),
        ("wVariant", C.c_uint16),
        ("ZZwDummy", C.c_uint16 * 20),
    ]


class PCO_SC2_Firmware_DESC(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("szName", C.c_char * 16),
        ("bMinorRev", C.c_uint8),
        ("bMajorRev", C.c_uint8),
        ("wVariant", C.c_uint16),
        ("ZZwDummy", C.c_uint16 * 22),
    ]


class PCO_HW_Vers(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("BoardNum", C.c_uint16),
        ("Board", PCO_SC2_Hardware_DESC * 10),
    ]


class PCO_FW_Vers(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("DeviceNum", C.c_uint16),
        ("Device", PCO_SC2_Firmware_DESC * 10),
    ]


class PCO_CameraType(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wCamType", C.c_uint16),
        ("wCamSubType", C.c_uint16),
        ("ZZwAlignDummy1", C.c_uint16),
        ("dwSerialNumber", C.c_uint32),
        ("dwHWVersion", C.c_uint32),
        ("dwFWVersion", C.c_uint32),
        ("wInterfaceType", C.c_uint16),
        ("strHardwareVersion", PCO_HW_Vers),
        ("strFirmwareVersion", PCO_FW_Vers),
        ("ZZwDummy", C.c_uint16 * 39),
    ]


class PCO_General(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("ZZwAlignDummy1", C.c_uint16),
        ("strCamType", PCO_CameraType),
        ("dwCamHealthWarnings", C.c_uint32),
        ("dwCamHealthErrors", C.c_uint32),
        ("dwCamHealthStatus", C.c_uint32),
        ("sCCDTemperature", C.c_short),
        ("sCamTemperature", C.c_short),
        ("sPowerSupplyTemperature", C.c_short),
        ("ZZwDummy", C.c_uint16 * 37),
    ]


class PCO_Single_Signal_Desc(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("ZZwAlignDummy1", C.c_uint16),
        ("strSignalName", C.c_uint8 * 100),
        ("wSignalDefinitions", C.c_uint16),
        ("wSignalTypes", C.c_uint16),
        ("wSignalPolarity", C.c_uint16),
        ("wSignalFilter", C.c_uint16),
        ("dwDummy", C.c_uint32 * 22),
    ]


class PCO_Signal_Description(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wNumOfSignals", C.c_uint16),
        ("strSingeSignalDesc", PCO_Single_Signal_Desc * 20),
        ("dwDummy", C.c_uint32 * 524),
    ]


class PCO_Sensor(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("ZZwAlignDummy1", C.c_uint16),
        ("strDescription", PCO_Description),
        ("strDescription2", PCO_Description2),
        ("strDescriptionIntensified", PCO_Description_Intensified),
        ("strDescription3", PCO_Description3),
        ("ZZdwDummy2", C.c_uint32 * 168),
        ("wSensorformat", C.c_uint16),
        ("wRoiX0", C.c_uint16),
        ("wRoiY0", C.c_uint16),
        ("wRoiX1", C.c_uint16),
        ("wRoiY1", C.c_uint16),
        ("wBinHorz", C.c_uint16),
        ("wBinVert", C.c_uint16),
        ("wIntensifiedFlags", C.c_uint16),
        ("dwPixelRate", C.c_uint32),
        ("wConvFact", C.c_uint16),
        ("wDoubleImage", C.c_uint16),
        ("wADCOperation", C.c_uint16),
        ("wIR", C.c_uint16),
        ("sCoolSet", C.c_short),
        ("wOffsetRegulation", C.c_uint16),
        ("wNoiseFilterMode", C.c_uint16),
        ("wFastReadoutMode", C.c_uint16),
        ("wDSNUAdjustMode", C.c_uint16),
        ("wCDIMode", C.c_uint16),
        ("wIntensifiedVoltage", C.c_uint16),
        ("wIntensifiedGatingMode", C.c_uint16),
        ("dwIntensifiedPhosphorDecay_us", C.c_uint32),
        ("ZZwDummy", C.c_uint16 * 32),
    ]


class PCO_Signal(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wSignalNum", C.c_uint16),
        ("wEnabled", C.c_uint16),
        ("wType", C.c_uint16),
        ("wPolarity", C.c_uint16),
        ("wFilter", C.c_uint16),
        ("wSelected", C.c_uint16),
        ("ZzwReserved", C.c_uint16),
        ("dwParameter", C.c_uint32 * 4),
        ("dwSignalFunctionality", C.c_uint32 * 4),
        ("ZzdwReserved", C.c_uint32 * 3),
    ]


class PCO_ImageTiming(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wDummy", C.c_uint16),
        ("FrameTime_ns", C.c_uint32),
        ("FrameTime_s", C.c_uint32),
        ("ExposureTime_ns", C.c_uint32),
        ("ExposureTime_s", C.c_uint32),
        ("TriggerSystemDelay_ns", C.c_uint32),
        ("TriggerSystemJitter_ns", C.c_uint32),
        ("TriggerDelay_ns", C.c_uint32),
        ("TriggerDelay_s", C.c_uint32),
        ("ZZdwDummy", C.c_uint32 * 11),
    ]


class PCO_Timing(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wTimeBaseDelay", C.c_uint16),
        ("wTimeBaseExposure", C.c_uint16),
        ("wCMOSParameter", C.c_uint16),
        ("dwCMOSDelayLines", C.c_uint32),
        ("dwCMOSExposureLines", C.c_uint32),
        ("dwDelayTable", C.c_uint32 * 16),
        ("ZZdwDummy1", C.c_uint32 * 110),
        ("dwCMOSLineTimeMin", C.c_uint32),
        ("dwCMOSLineTimeMax", C.c_uint32),
        ("dwCMOSLineTime", C.c_uint32),
        ("wCMOSTimeBase", C.c_uint16),
        ("wIntensifiedLoopCount", C.c_uint16),
        ("dwExposureTable", C.c_uint32 * 16),
        ("ZZdwDummy2", C.c_uint32 * 110),
        ("dwCMOSFlags", C.c_uint32),
        ("ZZdwDummy3", C.c_uint32),
        ("wTriggerMode", C.c_uint16),
        ("wForceTrigger", C.c_uint16),
        ("wCameraBusyStatus", C.c_uint16),
        ("wPowerDownMode", C.c_uint16),
        ("dwPowerDownTime", C.c_uint32),
        ("wExpTrgSignal", C.c_uint16),
        ("wFPSExposureMode", C.c_uint16),
        ("dwFPSExposureTime", C.c_uint32),
        ("wModulationMode", C.c_uint16),
        ("wCameraSynchMode", C.c_uint16),
        ("dwPeriodicalTime", C.c_uint32),
        ("wTimeBasePeriodical", C.c_uint16),
        ("ZZwDummy3", C.c_uint16),
        ("dwNumberOfExposures", C.c_uint32),
        ("lMonitorOffset", C.c_long),
        ("strSignal", PCO_Signal * 20),
        ("wStatusFrameRate", C.c_uint16),
        ("wFrameRateMode", C.c_uint16),
        ("dwFrameRate", C.c_uint32),
        ("dwFrameRateExposure", C.c_uint32),
        ("wTimingControlMode", C.c_uint16),
        ("wFastTimingMode", C.c_uint16),
        ("ZZwDummy", C.c_uint16 * 24),
    ]


class PCO_Storage(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("ZZwAlignDummy1", C.c_uint16),
        ("dwRamSize", C.c_uint32),
        ("wPageSize", C.c_uint16),
        ("dwRamSegSize", C.c_uint32 * 4),
        ("ZZdwDummyrs", C.c_uint32 * 20),
        ("wActSeg", C.c_uint16),
        ("wCompressionMode", C.c_uint16),
        ("ZZwDummy", C.c_uint16 * 38),
    ]


class PCO_Recording(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wStorageMode", C.c_uint16),
        ("wRecSubmode", C.c_uint16),
        ("wRecState", C.c_uint16),
        ("wAcquMode", C.c_uint16),
        ("wAcquEnableStatus", C.c_uint16),
        ("ucDay", C.c_byte),
        ("ucMonth", C.c_byte),
        ("wYear", C.c_uint16),
        ("wHour", C.c_uint16),
        ("ucMin", C.c_byte),
        ("ucSec", C.c_byte),
        ("wTimeStampMode", C.c_uint16),
        ("wRecordStopEventMode", C.c_uint16),
        ("dwRecordStopDelayImages", C.c_uint32),
        ("wMetaDataMode", C.c_uint16),
        ("wMetaDataSize", C.c_uint16),
        ("wMetaDataMode", C.c_uint16),
        ("wMetaDataVersion", C.c_uint16),
        ("ZZwDummy1", C.c_uint16),
        ("dwAcquModeExNumberImages", C.c_uint32),
        ("dwAcquModeExReserved", C.c_uint32 * 4),
        ("ZZwDummy", C.c_uint16 * 22),
    ]


class PCO_Segment(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("wXRes", C.c_uint16),
        ("wYRes", C.c_uint16),
        ("wBinHorz", C.c_uint16),
        ("wBinVert", C.c_uint16),
        ("wRoiX0", C.c_uint16),
        ("wRoiY0", C.c_uint16),
        ("wRoiX1", C.c_uint16),
        ("wRoiY1", C.c_uint16),
        ("ZZwAlignDummy1", C.c_uint16),
        ("dwValidImageCnt", C.c_uint32),
        ("dwMaxImageCnt", C.c_uint32),
        ("wRoiSoftX0", C.c_uint16),
        ("wRoiSoftY0", C.c_uint16),
        ("wRoiSoftX1", C.c_uint16),
        ("wRoiSoftY1", C.c_uint16),
        ("wRoiSoftXRes", C.c_uint16),
        ("wRoiSoftYRes", C.c_uint16),
        ("wRoiSoftDouble", C.c_uint16),
        ("ZZwDummy", C.c_uint16 * 33),
    ]


class PCO_Image_ColorSet(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("sSaturation", C.c_short),
        ("sVibrance", C.c_short),
        ("wColorTemp", C.c_uint16),
        ("sTint", C.c_short),
        ("wMulNormR", C.c_uint16),
        ("wMulNormG", C.c_uint16),
        ("wMulNormB", C.c_uint16),
        ("sContrast", C.c_short),
        ("wGamma", C.c_uint16),
        ("wSharpFixed", C.c_uint16),
        ("wSharpAdaptive", C.c_uint16),
        ("wScaleMin", C.c_uint16),
        ("wScaleMax", C.c_uint16),
        ("wProcOptions", C.c_uint16),
        ("ZZwDummy", C.c_uint16 * 93),
    ]


class PCO_Image(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wSize", C.c_uint16),
        ("ZZwAlignDummy1", C.c_uint16),
        ("strSegment", PCO_Segment * 4),
        ("ZZstrDummySeg", PCO_Segment * 14),
        ("strColorSet", PCO_Image_ColorSet),
        ("wBitAlignment", C.c_uint16),
        ("wHotPixelCorrectionMode", C.c_uint16),
        ("ZZwDummy", C.c_uint16 * 38),
    ]


class Birger_Array(C.Union):
    _fields_ = [
        ("bArray", C.c_byte * 128),
        ("wArray", C.c_uint16 * 64),
        ("sArray", C.c_short * 64),
        ("dwArray", C.c_uint32 * 32),
        ("lArray", C.c_long * 32),
    ]


class PCO_Birger(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("wCommand", C.c_uint16),
        ("wResult", C.c_uint16),
        ("wType", C.c_uint16),
        ("array", Birger_Array),
    ]


class PCO_Device(C.Structure):
    _pack_ = 1
    _fields_ = [
        ("struct_version", C.c_uint16),
        ("processid", C.c_int),
        ("status", C.c_uint32),
        ("id", C.c_uint32),
        ("SerialNumber", C.c_uint32),
        ("ExtendedInfo", C.c_uint64),
        ("CameraType", C.c_uint16),
        ("CameraSubType", C.c_uint16),
        ("PCO_InterfaceType", C.c_uint16),
        ("CameraName", C.c_char * 64),
        ("PCO_InterfaceName", C.c_char * 64),
    ]


class Sdk:
    """
    This class provides the basic methods for using pco cameras.
    """

    # -------------------------------------------------------------------------
    class exception(Exception):
        def __str__(self):
            return "Exception: {0} {1:08x}".format(self.args[0], self.args[1] & (2**32 - 1))

    # -------------------------------------------------------------------------
    def __init__(self, name=""):

        if platform.architecture()[0] != "64bit":
            logger.error("Python Interpreter not x64")
            raise OSError

        if sys.platform.startswith("win32"):
            self.__dll_name = "sc2_cam.dll"
        elif sys.platform.startswith("linux"):
            self.__dll_name = "libpco_sc2cam.so.1"
        else:
            print("Package not supported on platform " + sys.platform)
            raise SystemError

        dll_path = os.path.dirname(__file__).replace("\\", "/")

        try:
            if sys.platform.startswith("win32"):
                self.SC2_Cam = C.windll.LoadLibrary(dll_path + "/" + self.__dll_name)
            else:  # if sys.platform.startswith('linux'):
                self.SC2_Cam = C.cdll.LoadLibrary(dll_path + "/" + self.__dll_name)
        except OSError:
            logger.error('Error: "' + self.__dll_name + '" not found in directory "' + dll_path + '".')
            raise

        self.camera_handle = C.c_void_p(0)
        self.lens_control = C.c_void_p(0)

        self.name = name

        ########################### win32 only functions ############################
        if sys.platform.startswith("win32"):
            self.SC2_Cam.PCO_GetVersionInfoSC2_Cam.argtypes = [
                C.c_char_p,
                C.c_int,
                C.c_char_p,
                C.c_int,
                C.POINTER(C.c_int),
                C.POINTER(C.c_int),
                C.POINTER(C.c_int),
            ]

        ##############################################################################

        ########################### linux only functions ############################
        if sys.platform.startswith("linux"):
            self.SC2_Cam.PCO_ScanCameras.argtypes = [
                C.c_uint16,
                C.POINTER(PCO_Device),
                C.c_size_t,
            ]

            self.SC2_Cam.PCO_GetCameraDeviceStruct.argtypes = [
                C.c_uint16,
                C.POINTER(PCO_Device),
                C.c_size_t,
            ]

            self.SC2_Cam.PCO_OpenNextCamera.argtypes = [
                C.POINTER(C.c_void_p),
            ]

            self.SC2_Cam.PCO_OpenCameraDevice.argtypes = [
                C.POINTER(C.c_void_p),
                C.c_uint16,
            ]
        ##############################################################################

        self.SC2_Cam.PCO_GetErrorTextSDK.argtypes = [
            C.c_uint32,
            C.POINTER(C.c_char),
            C.c_uint32,
        ]

        self.SC2_Cam.PCO_OpenCamera.argtypes = [
            C.POINTER(C.c_void_p),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_OpenCameraEx.argtypes = [
            C.POINTER(C.c_void_p),
            C.POINTER(PCO_OpenStruct),
        ]

        self.SC2_Cam.PCO_CloseCamera.argtypes = [
            C.c_void_p,
        ]

        self.SC2_Cam.PCO_ResetLib.argtypes = [
            C.POINTER(C.c_void_p),
        ]

        self.SC2_Cam.PCO_GetSensorStruct.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Sensor),
        ]

        self.SC2_Cam.PCO_SetSensorStruct.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Sensor),
        ]

        self.SC2_Cam.PCO_GetCameraDescription.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Description),
        ]

        self.SC2_Cam.PCO_GetCameraDescriptionEx.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_void_p),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetGeneral.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_General),
        ]

        self.SC2_Cam.PCO_GetCameraType.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_CameraType),
        ]

        self.SC2_Cam.PCO_GetCameraHealthStatus.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_GetTemperature.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_short),
            C.POINTER(C.c_short),
            C.POINTER(C.c_short),
        ]

        self.SC2_Cam.PCO_GetInfoString.argtypes = [
            C.c_void_p,
            C.c_uint32,
            C.POINTER(C.c_char),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetCameraName.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_char),
            C.c_uint32,
        ]

        self.SC2_Cam.PCO_GetFirmwareInfo.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(PCO_FW_Vers),
        ]

        self.SC2_Cam.PCO_GetColorCorrectionMatrix.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_double),
        ]

        self.SC2_Cam.PCO_GetDSNUAdjustMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetDSNUAdjustMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_InitDSNUAdjustment.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetImageTransferMode.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_int,
        ]

        self.SC2_Cam.PCO_SetImageTransferMode.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_int,
        ]

        self.SC2_Cam.PCO_GetCDIMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_GetCDIMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetCDIMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetLookupTableInfo.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(C.c_uint16),
            C.c_char_p,
            C.c_uint16,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_byte),
            C.POINTER(C.c_byte),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_GetActiveLookupTable.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetActiveLookupTable.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_ArmCamera.argtypes = [
            C.c_void_p,
        ]

        self.SC2_Cam.PCO_SetImageParameters.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
            C.c_uint32,
            C.c_void_p,
            C.c_int,
        ]

        self.SC2_Cam.PCO_CamLinkSetImageParameters.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_ResetSettingsToDefault.argtypes = [
            C.c_void_p,
        ]

        self.SC2_Cam.PCO_SetTimeouts.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_uint32,
        ]

        self.SC2_Cam.PCO_RebootCamera.argtypes = [
            C.c_void_p,
        ]

        self.SC2_Cam.PCO_GetPowerSaveMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_GetCameraSetup.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetCameraSetup.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(C.c_uint32),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_CheckDeviceAvailability.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetDeviceStatus.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(C.c_uint32),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_ControlCommandCall.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_uint,
            C.c_void_p,
            C.c_uint,
        ]

        self.SC2_Cam.PCO_GetFanControlParameters.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_SetFanControlParameters.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetSizes.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_GetSensorFormat.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetSensorFormat.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetROI.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetROI.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetBinning.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetBinning.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetPixelRate.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetPixelRate.argtypes = [
            C.c_void_p,
            C.c_uint32,
        ]

        self.SC2_Cam.PCO_GetConversionFactor.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetConversionFactor.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetDoubleImageMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetDoubleImageMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetADCOperation.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetADCOperation.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetIRSensitivity.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetIRSensitivity.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetCoolingSetpointTemperature.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_short),
        ]

        self.SC2_Cam.PCO_SetCoolingSetpointTemperature.argtypes = [
            C.c_void_p,
            C.c_short,
        ]

        self.SC2_Cam.PCO_GetCoolingSetpoints.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_short),
        ]

        self.SC2_Cam.PCO_GetOffsetMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetOffsetMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetNoiseFilterMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetNoiseFilterMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetSensorDarkOffset.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_GetTimingStruct.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Timing),
        ]

        self.SC2_Cam.PCO_SetTimingStruct.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Timing),
        ]

        self.SC2_Cam.PCO_GetCOCRuntime.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_GetDelayExposureTime.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetDelayExposureTime.argtypes = [
            C.c_void_p,
            C.c_uint32,
            C.c_uint32,
            C.c_uint16,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetDelayExposureTimeTable.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_SetDelayExposureTimeTable.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetFrameRate.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetFrameRate.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.c_uint16,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_GetFPSExposureMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetFPSExposureMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_GetTriggerMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetTriggerMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_ForceTrigger.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_GetCameraBusyStatus.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_GetPowerDownMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetPowerDownMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetUserPowerDownTime.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetUserPowerDownTime.argtypes = [
            C.c_void_p,
            C.c_uint32,
        ]

        self.SC2_Cam.PCO_GetModulationMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_long),
        ]

        self.SC2_Cam.PCO_SetModulationMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint32,
            C.c_uint16,
            C.c_uint32,
            C.c_long,
        ]

        self.SC2_Cam.PCO_GetHWIOSignalCount.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_GetHWIOSignalDescriptor.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(PCO_Single_Signal_Desc),
        ]

        self.SC2_Cam.PCO_GetHWIOSignal.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(PCO_Signal),
        ]

        self.SC2_Cam.PCO_SetHWIOSignal.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(PCO_Signal),
        ]

        self.SC2_Cam.PCO_GetHWIOSignalTiming.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetHWIOSignalTiming.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
            C.c_uint32,
        ]

        self.SC2_Cam.PCO_GetImageTiming.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_ImageTiming),
        ]

        self.SC2_Cam.PCO_GetCameraSynchMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetCameraSynchMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetExpTrigSignalStatus.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_GetFastTimingMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetFastTimingMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetRecordingState.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetRecordingState.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetStorageMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetStorageMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetRecorderSubmode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetRecorderSubmode.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetAcquireMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetAcquireMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetAcquireModeEx.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetAcquireModeEx.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint32,
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_GetAcquireControl.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_SetAcquireControl.argtypes = [
            C.c_void_p,
            C.c_uint32,
            C.POINTER(C.c_uint32),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetAcqEnblSignalStatus.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_GetMetaDataMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetMetaDataMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_GetColorSettings.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Image_ColorSet),
        ]

        self.SC2_Cam.PCO_SetColorSettings.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Image_ColorSet),
        ]

        self.SC2_Cam.PCO_DoWhiteBalance.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(C.c_uint16),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetRecordStopEvent.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetRecordStopEvent.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint32,
        ]

        self.SC2_Cam.PCO_StopRecord.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetDateTime.argtypes = [
            C.c_void_p,
            C.c_uint8,
            C.c_uint8,
            C.c_uint16,
            C.c_uint16,
            C.c_uint8,
            C.c_uint8,
        ]

        self.SC2_Cam.PCO_GetTimestampMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetTimestampMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetStorageStruct.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Storage),
        ]

        self.SC2_Cam.PCO_SetStorageStruct.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Storage),
        ]

        self.SC2_Cam.PCO_GetCameraRamSize.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_GetCameraRamSegmentSize.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetCameraRamSegmentSize.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_ClearRamSegment.argtypes = [
            C.c_void_p,
        ]

        self.SC2_Cam.PCO_GetActiveRamSegment.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetActiveRamSegment.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetCompressionMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_SetCompressionMode.argtypes = [C.c_void_p, C.c_uint16, C.POINTER(C.c_uint32), C.c_uint16]

        self.SC2_Cam.PCO_GetMaxNumberOfImagesInSegment.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_GetRecordingStruct.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Recording),
        ]

        self.SC2_Cam.PCO_SetRecordingStruct.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Recording),
        ]

        self.SC2_Cam.PCO_GetSegmentStruct.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(PCO_Segment),
        ]

        self.SC2_Cam.PCO_GetImageStruct.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Image),
        ]

        self.SC2_Cam.PCO_GetSegmentImageSettings.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_GetNumberOfImagesInSegment.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_GetBitAlignment.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetBitAlignment.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetHotPixelCorrectionMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetHotPixelCorrectionMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_PlayImagesFromSegmentHDSDI.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint32,
            C.c_uint32,
            C.c_uint32,
        ]

        self.SC2_Cam.PCO_GetPlayPositionHDSDI.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_GetTransferParameter.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_int,
        ]

        self.SC2_Cam.PCO_GetSensorSignalStatus.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_GetCmosLineTiming.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_SetCmosLineTiming.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
            C.c_uint32,
            C.c_uint32,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetCmosLineExposureDelay.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_SetCmosLineExposureDelay.argtypes = [
            C.c_void_p,
            C.c_uint32,
            C.c_uint32,
            C.POINTER(C.c_uint32),
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_SetTransferParametersAuto.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_int,
        ]

        self.SC2_Cam.PCO_SetTransferParameter.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_int,
        ]

        self.SC2_Cam.PCO_GetInterfaceOutputFormat.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetInterfaceOutputFormat.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetFlimModulationParameter.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetFlimModulationParameter.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetFlimMasterModulationFrequency.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetFlimMasterModulationFrequency.argtypes = [
            C.c_void_p,
            C.c_uint32,
        ]

        self.SC2_Cam.PCO_GetFlimPhaseSequenceParameter.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetFlimPhaseSequenceParameter.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetFlimRelativePhase.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetFlimRelativePhase.argtypes = [
            C.c_void_p,
            C.c_uint32,
        ]

        self.SC2_Cam.PCO_GetFlimImageProcessingFlow.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetFlimImageProcessingFlow.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_InitLensControl.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_void_p),
        ]

        self.SC2_Cam.PCO_CleanupLensControl.argtypes = []

        self.SC2_Cam.PCO_CloseLensControl.argtypes = [
            C.c_void_p,
        ]

        self.SC2_Cam.PCO_GetLensFocus.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_long),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetLensFocus.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_long),
            C.c_uint32,
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_GetAperture.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetAperture.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.c_uint32,
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_GetApertureF.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetApertureF.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint32),
            C.c_uint32,
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SendBirgerCommand.argtypes = [
            C.c_void_p,
            C.POINTER(PCO_Birger),
            C.c_char_p,
            C.c_int,
        ]

        # --------------------------------------------------------------------
        # 2.18 SPECIAL COMMANDS PCO.DICAM
        # --------------------------------------------------------------------
        self.SC2_Cam.PCO_GetIntensifiedGatingMode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetIntensifiedGatingMode.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
        ]

        self.SC2_Cam.PCO_GetIntensifiedMCP.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.c_uint16,
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32),
        ]

        self.SC2_Cam.PCO_SetIntensifiedMCP.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
            C.c_uint16,
            C.c_uint32,
            C.c_uint32,
            C.c_uint32,
        ]

        self.SC2_Cam.PCO_GetIntensifiedLoopCount.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_uint16),
            C.POINTER(C.c_uint16),
        ]

        self.SC2_Cam.PCO_SetIntensifiedLoopCount.argtypes = [
            C.c_void_p,
            C.c_uint16,
            C.c_uint16,
        ]

    # -------------------------------------------------------------------------
    """def log(self, name, error, data=None, start_time=0.0):

        if self.timestamp == "on" and self.debuglevel != "off":
            curr_time = datetime.now()
            formatted_time = curr_time.strftime("%Y-%m-%d %H:%M:%S.%f")
            ts = "[{0} /{1:6.3f} s] ".format(formatted_time, time.time() - start_time)
        else:
            ts = ""

        if self.debuglevel == "error" and error != 0:
            print(
                ts + "[" + self.name + "]" + "[sdk] " + name + ":",
                self.get_error_text(error),
            )
        elif self.debuglevel == "verbose":
            print(
                ts + "[" + self.name + "]" + "[sdk] " + name + ":",
                self.get_error_text(error),
            )
        elif self.debuglevel == "extra verbose":
            print(
                ts + "[" + self.name + "]" + "[sdk] " + name + ":",
                self.get_error_text(error),
            )
            if data is not None:
                for key, value in data.items():
                    print("   -", key + ":", value)"""

    # ---------------------------------------------------------------------
    def get_error_text(self, errorcode):
        """"""

        buffer = (C.c_char * 500)()
        p_buffer = C.cast(buffer, C.POINTER(C.c_char))

        self.SC2_Cam.PCO_GetErrorTextSDK(errorcode, p_buffer, 500)

        temp_list = []
        for i in range(100):
            temp_list.append(buffer[i])
        output_string = bytes.join(b"", temp_list).decode("ascii")

        return output_string.strip("\0")

    # ---------------------------------------------------------------------
    def get_camera_handle(self):
        return self.camera_handle

    ########################### linux only functions ############################

    def scan_cameras(self, if_type=0):
        """
        Scan any or explicit interface for any or unused cameras
        """
        if not sys.platform.startswith("linux"):
            raise NotImplementedError

        wIfType = C.c_uint16(if_type)
        wDeviceCount = C.c_uint16()

        # first get number of avail devices
        error = self.SC2_Cam.PCO_ScanCameras(wIfType, wDeviceCount, 0, 0)
        error_msg = self.get_error_text(error)

        logger.info(error_msg)

        if error:
            raise ValueError("{}: {}".format(error, error_msg))
        elif wDeviceCount.value == 0:
            raise ValueError("-1: No devices available")

        # Now get devices
        device_arr = (PCO_Device * wDeviceCount.value)()
        array_size = C.sizeof(PCO_Device) * wDeviceCount.value

        error = self.SC2_Cam.PCO_ScanCameras(wIfType, wDeviceCount, device_arr, array_size)
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            ret.update({"device_count": wDeviceCount.value})
            ret["devices"] = []
            for device in device_arr:
                device_dict = {}
                device_dict.update({"struct version": device.struct_version})
                device_dict.update({"process id": device.processid})
                device_dict.update({"status": device.status})
                device_dict.update({"id": device.id})
                device_dict.update({"serial number": device.SerialNumber})
                device_dict.update({"extended info": device.ExtendedInfo})
                device_dict.update({"camera type": device.CameraType})
                device_dict.update({"camera subtype": device.CameraSubType})
                device_dict.update({"interface type": device.PCO_InterfaceType})

                temp_list = []
                for i in range(64):
                    temp_list.append(device.CameraName[i])
                output_string = bytes.join(b"", temp_list).decode("ascii")
                device_dict.update({"camera name": output_string.strip("\0")})
                temp_list.clear()
                for i in range(64):
                    temp_list.append(device.PCO_InterfaceName[i])
                output_string = bytes.join(b"", temp_list).decode("ascii")
                device_dict.update({"interface name": output_string.strip("\0")})

                ret["devices"].append(device_dict)

        logger.info(error_msg)

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    def get_camera_device_struct(self, id):
        """
        get PCO_Device structure with id
        """
        if not sys.platform.startswith("linux"):
            raise NotImplementedError

        # function definition changed to pointer
        raise NotImplementedError

        wId = C.c_uint16(id)
        device = PCO_Device

        error = self.SC2_Cam.PCO_GetCameraDeviceStruct(device, wId)
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            ret.update({"struct version": device.struct_version})
            ret.update({"process id": device.processid})
            ret.update({"status": device.status})
            ret.update({"id": device.id})
            ret.update({"serial number": device.SerialNumber})
            ret.update({"extended info": device.ExtendedInfo})
            ret.update({"camera type": device.CameraType})
            ret.update({"camera subtype": device.CameraSubType})
            ret.update({"interface type": device.PCO_InterfaceType})

            temp_list = []
            for i in range(64):
                temp_list.append(device.CameraName[i])
            output_string = bytes.join(b"", temp_list).decode("ascii")
            ret.update({"camera name": output_string.strip("\0")})
            temp_list.clear()
            for i in range(64):
                temp_list.append(device.PCO_InterfaceName[i])
            output_string = bytes.join(b"", temp_list).decode("ascii")
            ret.update({"interface name": output_string.strip("\0")})

        logger.info(error_msg)

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    def open_next_camera(self):
        """
        Open camera object

        Initialize camera
        - camhandle must be NULL on input to open next vacant camera
        - if camhandle is a valid handle reinitialize this camera
        """
        if not sys.platform.startswith("linux"):
            raise NotImplementedError

        error = self.SC2_Cam.PCO_OpenNextCamera(self.camera_handle)
        error_msg = self.get_error_text(error)

        ret = {}
        ret.update({"camera handle": self.camera_handle})

        logger.info(error_msg)

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    def open_camera_device(self, id):
        """
        Open camera object

        Initialize camera
        - camhandle must be NULL on input to open next vacant camera
        - if camhandle is a valid handle reinitialize this camera
        """
        if not sys.platform.startswith("linux"):
            raise NotImplementedError

        wId = C.c_uint16(id)

        error = self.SC2_Cam.PCO_OpenCameraDevice(self.camera_handle, wId)
        error_msg = self.get_error_text(error)

        ret = {}
        ret.update({"camera handle": self.camera_handle})

        logger.info(error_msg)

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    #############################################################################

    # ---------------------------------------------------------------------
    # 2.1.1 PCO_OpenCamera
    # ---------------------------------------------------------------------
    def open_camera(self):
        """
        This function is used to get a connection to a camera. This function
        scans through all available interfaces and tries to connect to the next
        available camera.
        """
        error = self.SC2_Cam.PCO_OpenCamera(self.camera_handle, 0)
        error_msg = self.get_error_text(error)

        ret = {}
        ret.update({"camera handle": self.camera_handle})

        logger.info(error_msg)

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.1.2 PCO_OpenCameraEx
    # -------------------------------------------------------------------------
    def open_camera_ex(self, interface, camera_number=0):
        """
        This function is used to get a connection to a specific camera.
        """

        interface_dict = {
            "FireWire": 1,
            "GenICam": 3,
            "GigE": 5,
            "USB 2.0": 6,
            "Camera Link Silicon Software": 7,
            "USB 3.0": 8,
            "CLHS": 11,
        }
        w_flags = [0] * 10
        dw_flags = [0] * 5
        void_ptr = [0] * 6
        w_dummy = [0] * 8

        strOpenStruct = PCO_OpenStruct()
        strOpenStruct.wSize = C.c_uint16(C.sizeof(PCO_OpenStruct))
        strOpenStruct.wInterfaceType = C.c_uint16(interface_dict[interface])
        strOpenStruct.wCameraNumber = C.c_uint16(camera_number)
        strOpenStruct.wCameraNumAtInterface = C.c_uint16(camera_number)
        strOpenStruct.wOpenFlags = (C.c_uint16 * 10)(*w_flags)
        strOpenStruct.dwOpenFlags = (C.c_uint32 * 5)(*dw_flags)
        strOpenStruct.wOpenPtr = (C.c_void_p * 6)(*void_ptr)
        strOpenStruct.zzwDummy = (C.c_uint16 * 8)(*w_dummy)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_OpenCameraEx(self.camera_handle, strOpenStruct)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        return {"error": error}
        # ret = {}
        # ret.update({"camera handle": self.camera_handle})

        # logger.info(error_msg)

        # if error:
        #     raise ValueError("{}: {}".format(error, error_msg))

        # return ret

    # -------------------------------------------------------------------------
    # 2.1.3 PCO_CloseCamera
    # -------------------------------------------------------------------------
    def close_camera(self):
        """
        This function is used to close the connection to a previously opened
        camera.
        """

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_CloseCamera(self.camera_handle)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        self.camera_handle = C.c_void_p(0)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.1.4 PCO_ResetLib
    # -------------------------------------------------------------------------
    def reset_lib(self):
        """
        This function is used to set the sc2_cam library to an initial state.
        All camera handles have to be closed with close_camera before this
        function is called.
        """

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_ResetLib(self.camera_handle)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.1.5 PCO_CheckDeviceAvailability (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------
    def check_device_availability(self, device_number=0):
        """"""
        wNum = C.c_uint16(device_number)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_CheckDeviceAvailability(self.camera_handle, wNum)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    def get_device_status(self, device_number=0):
        """"""
        wNum = C.c_uint16(device_number)
        dwStatus = C.c_uint32()
        wStatusLen = C.c_uint16(1)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetDeviceStatus(self.camera_handle, wNum, dwStatus, wStatusLen)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        avail_dict = {0: "not available", 0x80000000: "available"}
        ret = {}
        if error == 0:
            ret.update({"device availability": avail_dict[dwStatus.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.2.1 PCO_GetCameraDescription(Ex)
    # -------------------------------------------------------------------------

    def get_camera_description(self):
        """
        Sensor and camera specific description is queried.

        :return: camera description
        :rtype: dict
        """

        strDescription = PCO_Description()
        strDescription.wSize = C.sizeof(PCO_Description)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCameraDescription(self.camera_handle, strDescription)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        ret.update({"wSensorTypeDESC": strDescription.wSensorTypeDESC})
        ret.update({"sensor type": strDescription.wSensorTypeDESC})
        ret.update({"sensor subtype": strDescription.wSensorSubTypeDESC})
        ret.update({"max. horizontal resolution standard": strDescription.wMaxHorzResStdDESC})
        ret.update({"max. vertical resolution standard": strDescription.wMaxVertResStdDESC})
        ret.update({"max. horizontal resolution extended": strDescription.wMaxHorzResExtDESC})
        ret.update({"max. vertical resolution extended": strDescription.wMaxVertResExtDESC})
        ret.update({"bit resolution": strDescription.wDynResDESC})
        ret.update({"max. binning horizontal": strDescription.wMaxBinHorzDESC})
        ret.update({"binning horizontal stepping": strDescription.wBinHorzSteppingDESC})
        ret.update({"max. binning vert": strDescription.wMaxBinVertDESC})
        ret.update({"binning vert stepping": strDescription.wBinVertSteppingDESC})
        ret.update({"roi hor steps": strDescription.wRoiHorStepsDESC})
        ret.update({"roi vert steps": strDescription.wRoiVertStepsDESC})
        ret.update({"number adcs": strDescription.wNumADCsDESC})
        ret.update({"min size horz": strDescription.wMinSizeHorzDESC})

        prtuple = (
            strDescription.dwPixelRateDESC[0],
            strDescription.dwPixelRateDESC[1],
            strDescription.dwPixelRateDESC[2],
            strDescription.dwPixelRateDESC[3],
        )

        ret.update({"pixel rate": list(prtuple)})

        cftuple = (
            strDescription.wConvFactDESC[0],
            strDescription.wConvFactDESC[1],
            strDescription.wConvFactDESC[2],
            strDescription.wConvFactDESC[3],
        )

        ret.update({"conversion factor": list(cftuple)})

        cstuple = (
            strDescription.sCoolingSetpoints[0],
            strDescription.sCoolingSetpoints[1],
            strDescription.sCoolingSetpoints[2],
            strDescription.sCoolingSetpoints[3],
            strDescription.sCoolingSetpoints[4],
            strDescription.sCoolingSetpoints[5],
            strDescription.sCoolingSetpoints[6],
            strDescription.sCoolingSetpoints[7],
            strDescription.sCoolingSetpoints[8],
            strDescription.sCoolingSetpoints[9],
        )

        ret.update({"cooling setpoints": list(cstuple)})

        ret.update({"soft roi hor steps": strDescription.wSoftRoiHorStepsDESC})
        ret.update({"soft roi vert steps": strDescription.wSoftRoiVertStepsDESC})
        ret.update({"ir": strDescription.wIRDESC})
        ret.update({"min size vert": strDescription.wMinSizeVertDESC})
        ret.update({"Min Delay DESC": strDescription.dwMinDelayDESC})
        ret.update({"Max Delay DESC": strDescription.dwMaxDelayDESC})
        ret.update({"Min Delay Step DESC": strDescription.dwMinDelayStepDESC})
        ret.update({"Min Expos DESC": strDescription.dwMinExposDESC})
        ret.update({"Max Expos DESC": strDescription.dwMaxExposDESC})
        ret.update({"Min Expos Step DESC": strDescription.dwMinExposStepDESC})
        ret.update({"Min Delay IR DESC": strDescription.dwMinDelayIRDESC})
        ret.update({"Max Delay IR DESC": strDescription.dwMaxDelayIRDESC})
        ret.update({"Min Expos IR DESC": strDescription.dwMinExposIRDESC})
        ret.update({"Max Expos IR DESC": strDescription.dwMaxExposIRDESC})
        ret.update({"Time Table DESC": strDescription.wTimeTableDESC})
        ret.update({"wDoubleImageDESC": strDescription.wDoubleImageDESC})
        ret.update({"Min Cool Set DESC": strDescription.sMinCoolSetDESC})
        ret.update({"Max Cool Set DESC": strDescription.sMaxCoolSetDESC})
        ret.update({"Default Cool Set DESC": strDescription.sDefaultCoolSetDESC})
        ret.update({"Power Down Mode DESC": strDescription.wPowerDownModeDESC})
        ret.update({"Offset Regulation DESC": strDescription.wOffsetRegulationDESC})
        ret.update({"Color Pattern DESC": strDescription.wColorPatternDESC})
        ret.update({"Pattern Type DESC": strDescription.wPatternTypeDESC})
        ret.update({"Num Cooling Setpoints": strDescription.wNumCoolingSetpoints})
        ret.update({"dwGeneralCapsDESC1": strDescription.dwGeneralCapsDESC1})
        ret.update({"dwGeneralCapsDESC2": strDescription.dwGeneralCapsDESC2})

        efstuple = (
            strDescription.dwExtSyncFrequency[0],
            strDescription.dwExtSyncFrequency[1],
            strDescription.dwExtSyncFrequency[2],
            strDescription.dwExtSyncFrequency[3],
        )

        ret.update({"ext sync frequency": list(efstuple)})

        ret.update({"dwGeneralCapsDESC3": strDescription.dwGeneralCapsDESC3})
        ret.update({"dwGeneralCapsDESC4": strDescription.dwGeneralCapsDESC4})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    def get_camera_description_2(self):
        """
        Get descriptor 2
        """

        wType = C.c_uint16(1)

        strDescEx = PCO_Description2()
        strDescEx.wSize = C.sizeof(PCO_Description2)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCameraDescriptionEx(self.camera_handle, strDescEx, wType)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        ret.update({"min_periodical_time_ns": strDescEx.dwMinPeriodicalTimeDESC2})
        ret.update({"max_periodical_time_ms": strDescEx.dwMaxPeriodicalTimeDESC2})
        ret.update({"min_periodical_condition_ns": strDescEx.dwMinPeriodicalConditionDESC2})
        ret.update({"max_number_of_exposures": strDescEx.dwMaxNumberOfExposuresDESC2})
        ret.update({"min_monitoring_signal_offset": strDescEx.lMinMonitorSignalOffsetDESC2})
        ret.update({"max_monitoring_signal_offset": strDescEx.dwMaxMonitorSignalOffsetDESC2})
        ret.update({"min_periodical_step_ns": strDescEx.dwMinPeriodicalStepDESC2})
        ret.update({"start_time_delay_ns": strDescEx.dwStartTimeDelayDESC2})
        ret.update({"min_monitor_step_ns": strDescEx.dwMinMonitorStepDESC2})
        ret.update({"min_delay_modulate_ns": strDescEx.dwMinDelayModDESC2})
        ret.update({"max_delay_modulate_ms": strDescEx.dwMaxDelayModDESC2})
        ret.update({"min_delay_modulate_step_ns": strDescEx.dwMinDelayStepModDESC2})
        ret.update({"min_exposure_modulate_ns": strDescEx.dwMinExposureModDESC2})
        ret.update({"max_exposure_modulate_ms": strDescEx.dwMaxExposureModDESC2})
        ret.update({"min_exposure_modulate_step_ns": strDescEx.dwMinExposureStepModDESC2})
        ret.update({"modulate_caps_descriptor": strDescEx.dwModulateCapsDESC2})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------

    def get_camera_description_intensified(self):
        """
        Get intensified descriptor
        """

        wType = C.c_uint16(2)

        strDescEx = PCO_Description_Intensified()
        strDescEx.wSize = C.sizeof(PCO_Description_Intensified)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCameraDescriptionEx(self.camera_handle, strDescEx, wType)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        ret.update({"channel_number": strDescEx.wChannelNumberIntensifiedDESC})
        ret.update({"number_of_channels": strDescEx.wNumberOfChannelsIntensifiedDESC})
        ret.update({"min_voltage_intensified": strDescEx.wMinVoltageIntensifiedDESC})
        ret.update({"max_voltage_intensified": strDescEx.wMaxVoltageIntensifiedDESC})
        ret.update({"voltage_step_intensified": strDescEx.wVoltageStepIntensifiedDESC})
        ret.update({"extended_min_voltage_intensified": strDescEx.wExtendedMinVoltageIntensifiedDESC})
        ret.update({"max_loop_count_intensified": strDescEx.wMaxLoopCountIntensifiedDESC})
        ret.update({"min_phosphor_decay_ns": strDescEx.dwMinPhosphorDecayIntensified_ns_DESC})
        ret.update({"max_phosphor_decay_ms": strDescEx.dwMaxPhosphorDecayIntensified_ms_DESC})
        ret.update({"flags_intensified": strDescEx.dwFlagsIntensifiedDESC})
        ret.update({"intensifier_type": strDescEx.szIntensifierTypeDESC})
        ret.update({"mcp_rect_x_left": strDescEx.dwMCP_RectangleXL_DESC})
        ret.update({"mcp_rect_x_right": strDescEx.dwMCP_RectangleXR_DESC})
        ret.update({"mcp_rect_y_top": strDescEx.dwMCP_RectangleYT_DESC})
        ret.update({"mcp_rect_y_bottom": strDescEx.dwMCP_RectangleYB_DESC})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------

    def get_camera_description_3(self):
        """
        Get descriptor 3
        """

        wType = C.c_uint16(3)

        strDescEx = PCO_Description3()
        strDescEx.wSize = C.sizeof(PCO_Description3)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCameraDescriptionEx(self.camera_handle, strDescEx, wType)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        ret.update({"dark_offset": strDescEx.wDarkOffsetDESC3})
        ret.update({"dwGeneralCapsDESC5": strDescEx.dwGeneralCapsDESC5})
        ret.update({"dwGeneralCapsDESC6": strDescEx.dwGeneralCapsDESC6})
        ret.update({"dwGeneralCapsDESC7": strDescEx.dwGeneralCapsDESC7})
        ret.update({"dwGeneralCapsDESC8": strDescEx.dwGeneralCapsDESC8})
        ret.update({"min_horz_res_std": strDescEx.wMinHorzResStdDESC3})
        ret.update({"min_vert_res_std": strDescEx.wMinVertResStdDESC3})
        ret.update({"min_horz_res_ext": strDescEx.wMinHorzResExtDESC3})
        ret.update({"min_vert_res_ext": strDescEx.wMinVertResExtDESC3})
        ret.update({"pixelsize_horz": strDescEx.wPixelsize_horzDESC3})
        ret.update({"pixelsize_vert": strDescEx.wPixelsize_vertDESC3})
        ret.update({"min_sensor_temp_warning": strDescEx.sMinSensorTempWarningDESC3})
        ret.update({"max_sensor_temp_warning": strDescEx.sMaxSensorTempWarningDESC3})
        ret.update({"min_camera_temp_warning": strDescEx.sMinCameraTempWarningDESC3})
        ret.update({"max_camera_temp_warning": strDescEx.sMaxCameraTempWarningDESC3})
        ret.update({"min_power_temp_warning": strDescEx.sMinPowerTempWarningDESC3})
        ret.update({"max_power_temp_warning": strDescEx.sMaxPowerTempWarningDESC3})
        ret.update({"min_power_voltage_warning": strDescEx.wMinPowerVoltageWarningDESC3})
        ret.update({"max_power_voltage_warning": strDescEx.wMaxPowerVoltageWarningDESC3})
        ret.update({"min_sensor_temp_error": strDescEx.sMinSensorTempErrorDESC3})
        ret.update({"max_sensor_temp_error": strDescEx.sMaxSensorTempErrorDESC3})
        ret.update({"min_camera_temp_error": strDescEx.sMinCameraTempErrorDESC3})
        ret.update({"max_camera_temp_error": strDescEx.sMaxCameraTempErrorDESC3})
        ret.update({"min_power_temp_error": strDescEx.sMinPowerTempErrorDESC3})
        ret.update({"max_power_temp_error": strDescEx.sMaxPowerTempErrorDESC3})
        ret.update({"min_power_voltage_error": strDescEx.wMinPowerVoltageErrorDESC3})
        ret.update({"max_power_voltage_error": strDescEx.wMaxPowerVoltageErrorDESC3})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    def get_camera_description_ex(self, description_type):
        """
        Get descriptor based on type
        """

        if description_type == "PCO_DESCRIPTION":
            return self.get_camera_description()
        elif description_type == "PCO_DESCRIPTION_2":
            return self.get_camera_description_2()
        elif description_type == "PCO_DESCRIPTION_INTENSIFIED":
            return self.get_camera_description_intensified()
        elif description_type == "PCO_DESCRIPTION_3":
            return self.get_camera_description_3()
        else:
            raise ValueError

    # -------------------------------------------------------------------------
    # 2.3.1 PCO_GetGeneral (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------
    def get_general(self):
        """
        Get general struct
        """

        strGeneral = PCO_General()
        strGeneral.wSize = C.sizeof(PCO_General)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetGeneral(self.camera_handle, strGeneral)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            camera_type = {
                0x0100: "pco.1200HS",
                0x0200: "pco.1300",
                0x0220: "pco.1600",
                0x0240: "pco.2000",
                0x0260: "pco.4000",
                0x0830: "pco.1400",
                0x1000: "pco.dimax",
                0x1010: "pco.dimax_TV",
                0x1020: "pco.dimax CS",
                0x1400: "pco.flim",
                0x1600: "pco.panda",
                0x0800: "pco.pixelfly usb",
                0x1300: "pco.edge 5.5 CL",
                0x1302: "pco.edge 4.2 CL",
                0x1310: "pco.edge GL",
                0x1320: "pco.edge USB3",
                0x1340: "pco.edge CLHS",
                0x1304: "pco.edge MT",
                0x1800: "pco.edge family",
            }

            interface_type = {
                0x0001: "FireWire",
                0x0002: "Camera Link",
                0x0003: "USB 2.0",
                0x0004: "GigE",
                0x0005: "Serial Interface",
                0x0006: "USB 3.0",
                0x0007: "CLHS",
                0x0009: "USB 3.1 Gen 1",
            }

            ret.update({"camera type": camera_type.get(strGeneral.strCamType.wCamType, strGeneral.strCamType.wCamType)})
            ret.update({"camera subtype": strGeneral.strCamType.wCamSubType})
            ret.update({"serial number": strGeneral.strCamType.dwSerialNumber})
            ret.update(
                {
                    "interface type": interface_type.get(
                        strGeneral.strCamType.wInterfaceType, strGeneral.strCamType.wInterfaceType
                    )
                }
            )
            ret.update({"camera health warning": strGeneral.dwCamHealthWarnings})
            ret.update({"camera health error": strGeneral.dwCamHealthErrors})
            ret.update({"camera health status": strGeneral.dwCamHealthStatus})
            ret.update({"ccd temperature": strGeneral.sCCDTemperature})
            ret.update({"camera temperature": strGeneral.sCamTemperature})
            ret.update({"power temperature": strGeneral.sPowerSupplyTemperature})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.3.2 PCO_GetCameraType
    # -------------------------------------------------------------------------
    def get_camera_type(self):
        """
        This function retrieves the camera type code, hardware/firmware
        version, serial number and interface type of the camera.

        :return: {'camera type': str,
                'camera subtype': str,
                'serial number': int,
                'interface type': str}
        :rtype: dict
        """

        strCamType = PCO_CameraType()
        strCamType.wSize = C.sizeof(PCO_CameraType)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCameraType(self.camera_handle, strCamType)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            camera_type = {
                0x0100: "pco.1200HS",
                0x0200: "pco.1300",
                0x0220: "pco.1600",
                0x0240: "pco.2000",
                0x0260: "pco.4000",
                0x0830: "pco.1400",
                0x1000: "pco.dimax",
                0x1010: "pco.dimax_TV",
                0x1020: "pco.dimax CS",
                0x1400: "pco.flim",
                0x1600: "pco.panda",
                0x0800: "pco.pixelfly usb",
                0x1300: "pco.edge 5.5 CL",
                0x1302: "pco.edge 4.2 CL",
                0x1310: "pco.edge GL",
                0x1320: "pco.edge USB3",
                0x1340: "pco.edge CLHS",
                0x1304: "pco.edge MT",
                0x1800: "pco.edge family",
            }

            interface_type = {
                0x0001: "FireWire",
                0x0002: "Camera Link",
                0x0003: "USB 2.0",
                0x0004: "GigE",
                0x0005: "Serial Interface",
                0x0006: "USB 3.0",
                0x0007: "CLHS",
                0x0009: "USB 3.1 Gen 1",
            }

            ret.update({"camera type": camera_type.get(strCamType.wCamType, strCamType.wCamType)})
            ret.update({"camera subtype": strCamType.wCamSubType})
            ret.update({"serial number": strCamType.dwSerialNumber})
            ret.update({"interface type": interface_type.get(strCamType.wInterfaceType, strCamType.wInterfaceType)})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.3.3 PCO_GetCameraHealthStatus
    # -------------------------------------------------------------------------
    def get_camera_health_status(self):
        """
        This function retrieves information about the current camera status.
        It is recommended to call this function frequently (e.g. every 5s or
        after calling arm_camera()) in order to recognize camera internal
        problems. This helps to prevent camera hardware from damage.

        :return: {'warning': int,
                'error': int,
                'status': int}
        :rtype: dict
        """

        dwWarning = C.c_uint32()
        dwError = C.c_uint32()
        dwStatus = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCameraHealthStatus(self.camera_handle, dwWarning, dwError, dwStatus)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            ret.update({"warning": dwWarning.value})
            ret.update({"error": dwError.value})
            ret.update({"status": dwStatus.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.3.4 PCO_GetTemperature
    # -------------------------------------------------------------------------
    def get_temperature(self):
        """
        This function retrieves the current temperatures in °C of the imaging
        sensor, camera and additional devices e.g. power supply.

        Note:
        Not all of the temperature sensors are available in every camera
        model.

        :return: {'sensor temperature': float,
                  'camera temperature': float,
                  'power temperature': float}

        :rtype: dict
        """

        sCCDTemp = C.c_short()
        sCamTemp = C.c_short()
        sPowTemp = C.c_short()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetTemperature(self.camera_handle, sCCDTemp, sCamTemp, sPowTemp)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            if sCCDTemp.value != 0x8000:
                ret.update({"sensor temperature": float((sCCDTemp.value) / 10.0)})
            if sCamTemp.value != 0x8000:
                ret.update({"camera temperature": float(sCamTemp.value)})
            if sPowTemp.value != 0x8000:
                ret.update({"power temperature": float(sPowTemp.value)})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.3.5 PCO_GetInfoString
    # -------------------------------------------------------------------------
    def get_info_string(self, info_type):
        """
        This function retrieves some information about the camera, e.g. sensor
        name.

        :param info_type:
            * INFO_STRING_PCO_INTERFACE, camera name & interface information
            * INFO_STRING_CAMERA, camera name
            * INFO_STRING_SENSOR, sensor name
            * INFO_STRING_PCO_MATERIALNUMBER, production number
            * INFO_STRING_BUILD, firmware build number and date
            * INFO_STRING_PCO_INCLUDE, firmware build include revision

        :return: {'info string': str}
        :rtype: dict

        """

        info = {
            "INFO_STRING_PCO_INTERFACE": 0,
            "INFO_STRING_CAMERA": 1,
            "INFO_STRING_SENSOR": 2,
            "INFO_STRING_PCO_MATERIALNUMBER": 3,
            "INFO_STRING_BUILD": 4,
            "INFO_STRING_PCO_INCLUDE": 5,
            "INFO_STRING_DEVICE_0": 0x00020000,
            "INFO_STRING_DEVICE_1": 0x00020001,
            "INFO_STRING_DEVICE_2": 0x00020002,
            "INFO_STRING_DEVICE_3": 0x00020003,
            "INFO_STRING_DEVICE_4": 0x00020004,
            "INFO_STRING_DEVICE_5": 0x00020005,
            "INFO_STRING_DEVICE_6": 0x00020006,
            "INFO_STRING_DEVICE_7": 0x00020007,
            "INFO_STRING_DEVICE_8": 0x00020008,
        }

        buffer = (C.c_char * 500)()
        p_buffer = C.cast(buffer, C.POINTER(C.c_char))

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetInfoString(self.camera_handle, info[info_type], p_buffer, 500)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            temp_list = []
            for i in range(500):
                temp_list.append(buffer[i])
            output_string = bytes.join(b"", temp_list).decode("ascii")
            ret.update({"info string": output_string.strip("\0")})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.3.6 PCO_GetCameraName
    # -------------------------------------------------------------------------
    def get_camera_name(self):
        """
        This function retrieves the name of the camera.

        :return: {'camera name': str}
        :rtype: dict

        >>> get_camera_name()
        {'camera name': 'pco.edge 5.5 M CLHS'}

        """

        buffer = (C.c_char * 40)()
        p_buffer = C.cast(buffer, C.POINTER(C.c_char))

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCameraName(self.camera_handle, p_buffer, 40)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            temp_list = []
            for i in range(40):
                temp_list.append(buffer[i])
            output_string = bytes.join(b"", temp_list).decode("ascii")
            ret.update({"camera name": output_string.strip("\0")})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.3.7 PCO_GetFirmwareInfo
    # -------------------------------------------------------------------------
    def get_firmware_info(self, device=None):
        """
        Query firmware versions of all devices in the camera such as main
        microprocessor, main FPGA and coprocessors of the interface boards.

        :return: {'devices': [list of devices]}
        :rtype: dict
        """

        if device is not None:
            warnings.warn('sdk.get_firmware_info: "device" parameter is deprecated and will be removed.')

        pstrFirmWareVersion = PCO_FW_Vers()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetFirmwareInfo(self.camera_handle, 0, pstrFirmWareVersion)
        error_msg = self.get_error_text(error)

        num = pstrFirmWareVersion.DeviceNum
        blocks = math.ceil(num / 10)

        infos = []
        for i in range(blocks):

            error = self.SC2_Cam.PCO_GetFirmwareInfo(self.camera_handle, i, pstrFirmWareVersion)
            error_msg = self.get_error_text(error)
            if num >= ((i + 1) * 10):
                length = 10
            else:
                length = num - (i * 10)

            for devs in range(length):
                infos.append(
                    {
                        "name": pstrFirmWareVersion.Device[devs].szName.decode("ascii"),
                        "major": pstrFirmWareVersion.Device[devs].bMajorRev,
                        "minor": pstrFirmWareVersion.Device[devs].bMinorRev,
                        "variant": pstrFirmWareVersion.Device[devs].wVariant,
                    }
                )

        duration = time.perf_counter() - time_start

        ret = {}
        if error == 0:
            ret.update({"devices": infos})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.3.8 PCO_GetColorCorrectionMatrix
    # -------------------------------------------------------------------------
    def get_color_correction_matrix(self):
        """
        This function returns the color multiplier matrix from the camera. The
        color multiplier matrix can be used to normalize the color values of a
        color camera to a color temperature of 6500 K. The color multiplier
        matrix is specific for each camera and is determined through a special
        calibration procedure.

        :return: {'ccm': tuple}
        :rtype: dict
        """

        Matrix = (C.c_double * 9)()
        pdMatrix = C.cast(Matrix, C.POINTER(C.c_double))

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetColorCorrectionMatrix(self.camera_handle, pdMatrix)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            mtuple = (
                Matrix[0],
                Matrix[1],
                Matrix[2],
                Matrix[3],
                Matrix[4],
                Matrix[5],
                Matrix[6],
                Matrix[7],
                Matrix[8],
            )
            ret.update({"ccm": list(mtuple)})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.3.9 PCO_GetDSNUAdjustMode
    # -------------------------------------------------------------------------

    def get_dsnu_adjust_mode(self):
        """"""

        wDSNUAdjustMode = C.c_uint16()
        wReserved = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetDSNUAdjustMode(self.camera_handle, wDSNUAdjustMode, wReserved)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            dsnu_adjust_modes = {0: "none", 1: "auto", 2: "manual"}
            ret.update({"dsnu adjust mode": dsnu_adjust_modes[wDSNUAdjustMode.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.3.10 PCO_SetDSNUAdjustMode
    # -------------------------------------------------------------------------

    def set_dsnu_adjust_mode(self, adjust_mode):
        """"""

        double_image_mode = {"none": 0, "auto": 1, "manual": 2}
        wDSNUAdjustMode = C.c_uint16(double_image_mode[adjust_mode])
        wReserved = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetDSNUAdjustMode(self.camera_handle, wDSNUAdjustMode, wReserved)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.3.10 PCO_SetDSNUAdjustMode
    # -------------------------------------------------------------------------

    def init_dsnu_adjustment(self, adjust_mode):
        """"""

        double_image_mode = {"none": 0, "auto": 1, "manual": 2}
        wDSNUAdjustMode = C.c_uint16(double_image_mode[adjust_mode])
        wReserved = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_InitDSNUAdjustment(self.camera_handle, wDSNUAdjustMode, wReserved)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.4.1 PCO_ArmCamera
    # -------------------------------------------------------------------------
    def arm_camera(self):
        """
        This function arms, this means prepare the camera for a following
        recording. All configurations and settings made up to this moment are
        accepted, validated and the internal settings of the camera are
        prepared. If the arm was successful the camera state is changed to
        [armed] and the camera is able to start image recording immediately,
        when Recording State is set to [run].
        """

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_ArmCamera(self.camera_handle)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.4.2 PCO_CamLinkSetImageParameters
    # -------------------------------------------------------------------------
    def camlink_set_image_parameters(self, image_width, image_height):
        """"""
        wxres = C.c_uint16(image_width)
        wyres = C.c_uint16(image_height)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_CamLinkSetImageParameters(self.camera_handle, wxres, wyres)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.4.3 PCO_SetImageParameter
    # -------------------------------------------------------------------------

    def set_image_parameters(self, image_width, image_height):
        """
        This function sets the image parameters for internal allocated
        resources.
        """

        wxres = C.c_uint16(image_width)
        wyres = C.c_uint16(image_height)
        dwFlags = C.c_uint32(2)
        param = C.c_void_p(0)
        ilen = C.c_int(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetImageParameters(self.camera_handle, wxres, wyres, dwFlags, param, ilen)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.4.4 PCO_ResetSettingsToDefault
    # -------------------------------------------------------------------------
    def reset_settings_to_default(self):
        """
        This function can be used to reset all camera settings to its default
        values. This function is also executed during a power-up sequence. The
        camera must be stopped before calling this command. Default settings
        are slightly different for all cameras.
        """

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_ResetSettingsToDefault(self.camera_handle)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.4.5 PCO_SetTimeouts
    # -------------------------------------------------------------------------
    def set_timeouts(self, command_timeout=200, image_timeout=3000, transfer_timeout=200):
        """
        This function does set the internal timeout values for  different tasks.
        Usually there is no need to change these values.

        Command timeout in ms:
        A command sequence will be aborted and a timout error returned,
        if there is no response from the camera within the command timeout
        value.

        Image timeout in ms:
        An image request will be aborted and a timout error returned,
        if no image is transferred from the camera within the image timeout
        value. Only valid for the PCO_GetImageEx command.

        Transfer timeout in ms:
        Specifies the time to hold transfer resources. While image
        sequences are running transfer resources are allocated in some of
        the driver layer. To enable faster start time for the next image
        sequence these resources are held the set ‘transfer  timeout’
        time, after the last image of the sequence is transferred.
        PCO_CancelImages always deallocates the hold resources.

        >>> set_timeouts()  # sets default values

        >>> set_timeouts(200, 3000, 200)

        """

        buffer = (C.c_uint32 * 3)()
        buffer[0] = command_timeout  # 4
        buffer[1] = image_timeout  # 8
        buffer[2] = transfer_timeout  # 12
        p_buf_in = C.cast(buffer, C.POINTER(C.c_void_p))

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetTimeouts(self.camera_handle, p_buf_in, 12)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.4.6 PCO_RebootCamera
    # -------------------------------------------------------------------------
    def reboot_camera(self):
        """
        This function will reboot the camera. The function will return
        immediately and the reboot process in the camera is started. After
        calling this command the handle to this camera should be closed with
        close_camera().
        """

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_RebootCamera(self.camera_handle)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.4.7 PCO_GetCameraSetup
    # -------------------------------------------------------------------------
    def get_camera_setup(self):
        """
        This command returns the shutter mode of a pco.edge. This function
        is used to query the current operation mode of the camera. Some cameras
        can work at different operation modes with different descriptor
        settings.

        :rtype: dict
        """

        wType = C.c_uint16(0)
        dwSetup = (C.c_uint32 * 4)()
        pdwSetup = C.cast(dwSetup, C.POINTER(C.c_uint32))
        wLen = C.c_uint16(4)

        dwSetup[0] = 99
        dwSetup[1] = 99
        dwSetup[2] = 99
        dwSetup[3] = 99

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCameraSetup(self.camera_handle, wType, pdwSetup, wLen)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            ret.update(
                {
                    "type": wType.value,
                    "setup": (dwSetup[0], dwSetup[1], dwSetup[2], dwSetup[3]),
                    "length": wLen.value,
                }
            )

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.4.8 PCO_SetCameraSetup
    # -------------------------------------------------------------------------
    def set_camera_setup(self, setup):
        """
        Command can be used to set the shutter mode of a pco.edge.This function
        is used to set the operation mode of the camera. If operation mode is
        changed, reboot_camera() must be called afterwards. It is recommended
        to set the command timeout to 2000 ms by calling set_timeouts() before
        changing the setup.

        :param setup: str

            * 'rolling shutter'
            * 'global shutter'
            * 'global reset'
        """

        shutter_mode = {
            "rolling shutter": 0x00000001,
            "global shutter": 0x00000002,
            "global reset": 0x00000004,
        }

        wType = C.c_uint16(0)
        dwSetup = (C.c_uint32 * 4)()
        dwSetup[0] = shutter_mode[setup]

        wLen = C.c_uint16(4)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetCameraSetup(self.camera_handle, wType, dwSetup, wLen)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.4.9 PCO_ControlCommandCall
    # -------------------------------------------------------------------------

    def control_command_call(self, data):
        """
        This function issues a low level command to the camera. This call is
        part of most of the other calls. Normally calling this function is not
        needed. It can be used to cover those camera commands, which are not
        implemented in regular SDK functions.

        :param data: bytes
        """

        size_in = C.c_uint(len(data))
        p_data_in = C.cast(data, C.POINTER(C.c_void_p))

        data_out = (C.c_uint8 * 300)()
        size_out = C.c_uint(300)
        p_data_out = C.cast(data_out, C.POINTER(C.c_void_p))

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_ControlCommandCall(self.camera_handle, p_data_in, size_in, p_data_out, size_out)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            length = int.from_bytes(bytes(data_out)[2:4], byteorder="little")
            ret.update({"response telegram": bytes(data_out)[0:length]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.4.10 PCO_GetFanControlParameters
    # -------------------------------------------------------------------------
    def get_fan_control_parameters(self):

        wMode = C.c_uint16()
        wValue = C.c_uint16()
        wReserved = C.c_uint16()
        wNumReserved = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetFanControlParameters(self.camera_handle, wMode, wValue, wReserved, wNumReserved)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        mode_dict = {0: "auto", 1: "user"}
        ret = {}
        if error == 0:
            ret.update({"mode": mode_dict[wMode.value]})
            ret.update({"value": wValue.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.4.11 PCO_SetFanControlParameters
    # -------------------------------------------------------------------------
    def set_fan_control_parameters(self, mode, value=100):

        if value not in range(0, 101, 1):
            raise ValueError

        if mode not in ["auto", "user"]:
            raise ValueError

        mode_dict = {"auto": 0x0000, "user": 0x0001}

        wMode = C.c_uint16(mode_dict[mode])
        wValue = C.c_uint16(value)
        wReserved = C.c_uint16()
        wNumReserved = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetFanControlParameters(self.camera_handle, wMode, wValue, wReserved, wNumReserved)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5.1 PCO_GetSensorStruct (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------
    def get_sensor_struct(self):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.5.2 PCO_SetSensorStruct (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------

    def set_sensor_struct(self):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.5.3 PCO_GetSizes
    # -------------------------------------------------------------------------
    def get_sizes(self):
        """
        This function returns the current armed image size of the camera. If
        the user recently changed the size influencing values without
        issuing a arm_camera(), the get_sizes() function will return the
        sizes from the last recording. If no recording occurred, it will return
        the last ROI settings.

        :return: {'wXResAct': int,
                  'wYResAct': int,
                  'wXResMax': int,
                  'wYResMax': int}
        :rtype: dict
        """

        wXResAct = C.c_uint16()
        wYResAct = C.c_uint16()
        wXResMax = C.c_uint16()
        wYResMax = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetSizes(self.camera_handle, wXResAct, wYResAct, wXResMax, wYResMax)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:

            ret.update({"wXResAct": wXResAct.value})
            ret.update({"wYResAct": wYResAct.value})
            ret.update({"wXResMax": wXResMax.value})
            ret.update({"wYResMax": wYResMax.value})

            ret.update({"x": wXResAct.value})
            ret.update({"y": wYResAct.value})
            ret.update({"x max": wXResMax.value})
            ret.update({"y max": wYResMax.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.4 PCO_GetSensorFormat
    # -------------------------------------------------------------------------
    def get_sensor_format(self):
        """
        This function retrieves the current sensor format. In the format
        [standard] only effective pixels are readout from the sensor. The
        readout in the format [extended] is camera dependent. Either a distinct
        region of the sensor is selected or the full sensor including
        effective, dark, reference and dummy pixels.

        :return: {'sensor format': int}
        :rtype: dict
        """

        wSensor = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetSensorFormat(self.camera_handle, wSensor)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            sensor_formats = {0: "standard", 1: "extended"}
            ret.update({"sensor format": sensor_formats[wSensor.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.5 PCO_SetSensorFormat
    # -------------------------------------------------------------------------
    def set_sensor_format(self, sensor_format):
        """
        This function sets the sensor format. In the format [standard] only
        effective pixels are readout from the sensor. The readout in the format
        [extended] is camera dependent. Either a distinct region of the sensor
        is selected or the full sensor including effective, dark, reference and
        dummy pixels.

        :param sensor_format: str

            * 'standard'
            * 'extended'

        >>> set_sensor_format()
        {'sensor format': 'standard'}

        >>> set_sensor_format()
        {'sensor format': 'extended'}

        """

        sensor_format_types = {"standard": 0x0000, "extended": 0x0001}
        wSensor = C.c_uint16(sensor_format_types[sensor_format])

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetSensorFormat(self.camera_handle, wSensor)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"sensor format": sensor_format})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5.6 PCO_GetROI
    # -------------------------------------------------------------------------
    def get_roi(self):
        """
        :return: {'x0': int,
                  'y0': int,
                  'x1': int,
                  'y1': int}
        :rtype: dict

        >>> get_roi()
        {'x0': 1, 'y0': 1, 'x1': 512, 'y1': 512}

        """

        wRoiX0 = C.c_uint16()
        wRoiY0 = C.c_uint16()
        wRoiX1 = C.c_uint16()
        wRoiY1 = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetROI(self.camera_handle, wRoiX0, wRoiY0, wRoiX1, wRoiY1)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            ret.update(
                {
                    "x0": wRoiX0.value,
                    "y0": wRoiY0.value,
                    "x1": wRoiX1.value,
                    "y1": wRoiY1.value,
                }
            )

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.7 PCO_SetROI
    # -------------------------------------------------------------------------
    def set_roi(self, x0, y0, x1, y1):
        """
        :param x0: int
        :param y0: int
        :param x1: int
        :param y1: int

        >>> set_roi(1, 1, 512, 512)

        """

        wRoiX0 = C.c_uint16(x0)
        wRoiY0 = C.c_uint16(y0)
        wRoiX1 = C.c_uint16(x1)
        wRoiY1 = C.c_uint16(y1)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetROI(self.camera_handle, wRoiX0, wRoiY0, wRoiX1, wRoiY1)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"x0": x0, "y0": y0, "x1": x1, "y1": y1})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5.8 PCO_GetBinning
    # -------------------------------------------------------------------------
    def get_binning(self):
        """
        Returns the binning values for x and y.

        :return: {'binning x': int
                'binning y': int}
        :rtype: dict

        >>> get_binning()
        {'binning x': 2, 'binning y': 2}

        """

        wBinHorz = C.c_uint16()
        wBinVert = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetBinning(self.camera_handle, wBinHorz, wBinVert)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            ret.update({"binning x": wBinHorz.value, "binning y": wBinVert.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.9 PCO_SetBinning
    # -------------------------------------------------------------------------
    def set_binning(self, x, y):
        """"""

        wBinHorz = C.c_uint16(x)
        wBinVert = C.c_uint16(y)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetBinning(self.camera_handle, wBinHorz, wBinVert)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"binning x": x, "binning y": y})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5.10 PCO_GetPixelRate
    # -------------------------------------------------------------------------
    def get_pixel_rate(self):
        """
        Returns the currently active pixel rate.

        :return: {'pixel rate': int}
        :rtype: dict

        >>> get_pixel_rate()
        {'pixel rate': 286000000}

        """

        dwPixelRate = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetPixelRate(self.camera_handle, dwPixelRate)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"pixel rate": dwPixelRate.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.11 PCO_SetPixelRate
    # -------------------------------------------------------------------------
    def set_pixel_rate(self, pixel_rate):
        """
        Set the pixel rate.

        :param pixel_rate: int

        >>> set_pixel_rate(286_000_000)

        """

        dwPixelRate = C.c_uint32(pixel_rate)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetPixelRate(self.camera_handle, dwPixelRate)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"pixel rate": pixel_rate})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5.12 PCO_GetConversionFactor
    # -------------------------------------------------------------------------
    def get_conversion_factor(self):
        """
        Get conversion factor (value x 10)

        :return: {'conversion factor': int}
        :rtype: dict

        >>> get_conversion_factor()
        {'conversion factor': 46}

        """

        wConvFact = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetConversionFactor(self.camera_handle, wConvFact)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"conversion factor": wConvFact.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.13 PCO_SetConversionFactor
    # -------------------------------------------------------------------------
    def set_conversion_factor(self, conversion_factor):
        """
        Set conversion factor

        :param conversion_factor: int
        """

        wConvFact = C.c_uint16(conversion_factor)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetConversionFactor(self.camera_handle, wConvFact)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"conversion factor": conversion_factor})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5.14 PCO_GetDoubleImageMode
    # -------------------------------------------------------------------------
    def get_double_image_mode(self):
        """
        Returns the double image mode.

        :return: {'double image': str}
        :rtype: dict

        >>> get_double_image_mode()
        {'double image': 'on'}

        >>> get_double_image_mode()
        {'double image': 'off'}

        """

        wDoubleImage = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetDoubleImageMode(self.camera_handle, wDoubleImage)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            double_image_mode = {0: "off", 1: "on"}
            ret.update({"double image": double_image_mode[wDoubleImage.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.15 PCO_SetDoubleImageMode
    # -------------------------------------------------------------------------
    def set_double_image_mode(self, mode):
        """
        Enables or disables the double image mode.

        >>> set_double_image_mode('on')

        >>> set_double_image_mode('off')

        """

        double_image_mode = {"off": 0, "on": 1}

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetDoubleImageMode(self.camera_handle, double_image_mode[mode])
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"double image mode": mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5.16 PCO_GetADCOperation
    # -------------------------------------------------------------------------
    def get_adc_operation(self):
        """"""

        wADCOperation = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetADCOperation(self.camera_handle, wADCOperation)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            adc_operation = {1: "single adc", 2: "dual adc", 16: "panda"}
            ret.update({"adc operation": adc_operation[wADCOperation.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.17 PCO_SetADCOperation
    # -------------------------------------------------------------------------
    def set_adc_operation(self, mode):
        """

        >>> set_adc_operation('single adc')

        >>> set_adc_operation('dual adc')

        """

        adc_operation = {"single adc": 1, "dual adc": 2, "panda": 16}
        wADCOperation = C.c_uint16(adc_operation[mode])

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetADCOperation(self.camera_handle, wADCOperation)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"adc operation": mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5.18 PCO_GetIRSensitivity
    # -------------------------------------------------------------------------
    def get_ir_sensitivity(self):
        """
        This function returns the IR sensitivity operating mode currently used
        from the camera.

        >>> get_ir_sensitivity()
        {'ir sensitivity': 'off'}

        >>> get_ir_sensitivity()
        {'ir sensitivity': 'on'}

        """

        wIR = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetIRSensitivity(self.camera_handle, wIR)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ir_sensitivity = {0: "off", 1: "on"}
            ret.update({"ir sensitivity": ir_sensitivity[wIR.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.19 PCO_SetIRSensitivity
    # -------------------------------------------------------------------------
    def set_ir_sensitivity(self, mode):
        """
        >>> set_ir_sensitivity('off')

        >>> set_ir_sensitivity('on')

        """

        ir_sensitivity = {"off": 0, "on": 1}
        wIR = C.c_uint16(ir_sensitivity[mode])

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetIRSensitivity(self.camera_handle, wIR)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"ir sensitivity": mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5.20 PCO_GetCoolingSetpointTemperature
    # -------------------------------------------------------------------------
    def get_cooling_setpoint_temperature(self):
        """

        >>> get_cooling_setpoint_temperature()
        {'cooling setpoint temperature': 7.0}

        """

        sCoolSet = C.c_short()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCoolingSetpointTemperature(self.camera_handle, sCoolSet)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"cooling setpoint temperature": float(sCoolSet.value)})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.21 PCO_SetCoolingSetpointTemperature
    # -------------------------------------------------------------------------
    def set_cooling_setpoint_temperature(self, cooling_setpoint):
        """"""

        sCoolSet = C.c_short(int(cooling_setpoint))

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetCoolingSetpointTemperature(self.camera_handle, sCoolSet)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"cooling setpoint temperature": cooling_setpoint})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5.22 PCO_GetCoolingSetpoints
    # -------------------------------------------------------------------------
    def get_cooling_setpoints(self):
        """"""

        wNumSetPoints = C.c_uint16(100)
        sCoolSetpoints = (C.c_short * 100)()
        psCoolSetpoints = C.cast(sCoolSetpoints, C.POINTER(C.c_short))

        cooling_setpoints_list = []

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCoolingSetpoints(self.camera_handle, 0, wNumSetPoints, psCoolSetpoints)
        error_msg = self.get_error_text(error)

        if error == 0:
            cooling_setpoints_list.append(float(sCoolSetpoints[0]))

        for i in range(1, wNumSetPoints.value):

            error = self.SC2_Cam.PCO_GetCoolingSetpoints(self.camera_handle, i, wNumSetPoints, psCoolSetpoints)
            error_msg = self.get_error_text(error)
            if error == 0:
                cooling_setpoints_list.append(sCoolSetpoints[i])

        duration = time.perf_counter() - time_start
        ret = {}
        ret.update({"cooling setpoints": cooling_setpoints_list})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.23 PCO_GetOffsetMode
    # -------------------------------------------------------------------------
    def get_offset_mode(self):
        """


        :return: {'offset mode': str ['auto', 'off']}
        :rtype: dict

        >>> get_offset_mode()
        {'offset mode': 'auto'}

        >>> get_offset_mode()
        {'offset mode': 'off'}

        """

        wOffsetRegulation = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetOffsetMode(self.camera_handle, wOffsetRegulation)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            offest_regulation = {0: "auto", 1: "off"}
            ret.update({"offset mode": offest_regulation[wOffsetRegulation.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.24 PCO_SetOffsetMode
    # -------------------------------------------------------------------------
    def set_offset_mode(self, mode):
        """


        :param mode: str

            * 'auto'
            * 'off'

        >>> set_offse_mode('auto')

        >>> set_offse_mode('off')

        """

        offset_regulation = {"auto": 0, "off": 1}

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetOffsetMode(self.camera_handle, offset_regulation[mode])
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"offset mode": mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5.25 PCO_GetNoiseFilterMode
    # -------------------------------------------------------------------------
    def get_noise_filter_mode(self):
        """


        :return: {'noise filter mode': str}
        :rtype: dict
        """

        wNoiseFilterMode = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetNoiseFilterMode(self.camera_handle, wNoiseFilterMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            noise_filter_mode = {0: "off", 1: "on", 5: "on & hot pixel correction"}
            ret.update({"noise filter mode": noise_filter_mode[wNoiseFilterMode.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.26 PCO_SetNoiseFilterMode
    # -------------------------------------------------------------------------
    def set_noise_filter_mode(self, mode):
        """


        :param mode: str

            * 'off'
            * 'on'
            * 'on & hot pixel correction'
        """

        noise_filter_mode = {"off": 0, "on": 1, "on & hot pixel correction": 5}

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetNoiseFilterMode(self.camera_handle, noise_filter_mode[mode])
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {"noise filter mode": mode}

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5.27 PCO_GetLookuptableInfo (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------
    def get_lookuptable_info(self, lut_nbr, description):
        """"""

        wLUTNum = C.c_uint16(lut_nbr)
        cDescription = C.c_char_p(description.encode("utf-8"))
        wDescLen = C.c_uint16(len(description.encode("utf-8")))
        wNumberOfLuts = C.c_uint16()
        wIdentifier = C.c_uint16()
        bInputWidth = C.c_uint16()
        bOutputWidth = C.c_byte()
        wFormat = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetLookupTableInfo(
            self.camera_handle,
            wLUTNum,
            wNumberOfLuts,
            cDescription,
            wDescLen,
            wIdentifier,
            bInputWidth,
            bOutputWidth,
            wFormat,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"number of luts": wNumberOfLuts.value})
            ret.update({"identifier": wIdentifier.value})
            ret.update({"input width": bInputWidth.value})
            ret.update({"output width": bOutputWidth.value})
            ret.update({"format": wFormat.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.28 PCO_GetActiveLookuptable (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------
    def get_active_lookup_table(self):
        """"""

        wIdentifier = C.c_uint16()
        wParameter = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetActiveLookupTable(self.camera_handle, wIdentifier, wParameter)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"identifier": wIdentifier.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.5.29 PCO_SetActiveLookuptable (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------
    def set_active_lookup_table(self, identifier):
        """"""

        wIdentifier = C.c_uint16(identifier)
        wParameter = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetActiveLookupTable(self.camera_handle, wIdentifier, wParameter)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.5.30 PCO_GetSensorDarkOffset
    # -------------------------------------------------------------------------

    def get_sensor_dark_offset(self):
        """ """

        wDarkOffset = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetSensorDarkOffset(self.camera_handle, wDarkOffset)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"dark offset": int(wDarkOffset.value)})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.1 PCO_GetTimingStruct (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------

    def get_timing_struct(self):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.6.2 PCO_SetTimingStruct (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------
    def set_timing_struct(self):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.6.3 PCO_GetCOCRunTime
    # -------------------------------------------------------------------------
    def get_coc_runtime(self):
        """


        :return: {'time second': int
                'time nanosecond': int}
        :rtype: dict
        """

        dwTime_s = C.c_uint32()
        dwTime_ns = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCOCRuntime(self.camera_handle, dwTime_s, dwTime_ns)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"time second": float(dwTime_s.value)})
            ret.update({"time nanosecond": float(dwTime_ns.value)})
            ret.update({"coc runtime": dwTime_s.value + dwTime_ns.value * 1e-9})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.4 PCO_GetDelayExposureTime
    # -------------------------------------------------------------------------
    def get_delay_exposure_time(self):
        """


        :return: {'delay': int,
                'delay timebase': str,
                'exposure': int,
                'exposure timebase': str}
        :rtype: dict


        >>> get_delay_exposure_timeime()
        {'delay': 0, 'exposure': 10,
         'delay timebase': 'ms', 'exposure timebase': 'ms'}

        """

        dwDelay = C.c_uint32()
        dwExposure = C.c_uint32()
        wTimeBaseDelay = C.c_uint16()
        wTimeBaseExposure = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetDelayExposureTime(
            self.camera_handle, dwDelay, dwExposure, wTimeBaseDelay, wTimeBaseExposure
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            timebase = {0: "ns", 1: "us", 2: "ms"}
            ret.update({"delay": dwDelay.value})
            ret.update({"exposure": dwExposure.value})
            ret.update({"delay timebase": timebase[wTimeBaseDelay.value]})
            ret.update({"exposure timebase": timebase[wTimeBaseExposure.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.5 PCO_SetDelayExposureTime
    # -------------------------------------------------------------------------
    def set_delay_exposure_time(self, delay, delay_timebase, exposure, exposure_timebase):
        """
        :param delay: int
        :param delay_timebase: str ['ms', 'us', 'ns']
        :param exposure: int
        :param exposure_timebase: str ['ms', 'us', 'ns']

        >>> set_delay_exposure_time(0, 'ms', 10, 'ms')

        """

        timebase = {"ns": 0, "us": 1, "ms": 2}

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetDelayExposureTime(
            self.camera_handle,
            delay,
            exposure,
            timebase[delay_timebase],
            timebase[exposure_timebase],
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update(
            {
                "delay": delay,
                "delay timebase": delay_timebase,
                "exposure": exposure,
                "exposure timebase": exposure_timebase,
            }
        )

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.6.6 PCO_GetDelayExposureTimeTable
    # -------------------------------------------------------------------------
    def get_delay_exposure_time_table(self, count):
        """
        This function returns the current setting of the delay and exposure
        time table values and the associated time base values.
        Maximum size of each array is 16 DWORD entries. Returned values are
        only valid if the last timing command was
        PCO_SetDelayExposureTimeTable.
        See PCO_SetDelayExposureTimeTable for a more detailed description of
        the delay / exposure time table usage.
        """

        dwDelay = (C.c_uint32 * 16)()
        dwExposure = (C.c_uint32 * 16)()
        wTimeBaseDelay = C.c_uint16()
        wTimeBaseExposure = C.c_uint16()
        wCount = C.c_uint16(count)

        p_delay = C.cast(dwDelay, C.POINTER(C.c_uint32))
        p_exposure = C.cast(dwExposure, C.POINTER(C.c_uint32))

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetDelayExposureTimeTable(
            self.camera_handle, p_delay, p_exposure, wTimeBaseDelay, wTimeBaseExposure, wCount
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            timebase = {0: "ns", 1: "us", 2: "ms"}

            count2 = wCount.value
            delays = []
            exposures = []
            for i in range(count2):
                delays.append(dwDelay[i])
                exposures.append(dwExposure[i])

            ret.update({"delay": delays})
            ret.update({"exposure": exposures})
            ret.update({"delay timebase": timebase[wTimeBaseDelay.value]})
            ret.update({"exposure timebase": timebase[wTimeBaseExposure.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.7 PCO_SetDelayExposureTimeTable
    # -------------------------------------------------------------------------
    def set_delay_exposure_time_table(self, delay, exposure, timebase_delay, timebase_exposure, count):
        """
        This function does set the delay and exposure time pairs in the time
        tables and the associated time base values. Maximum size of each
        table array is 16 DWORD entries. Delay / exposure time table operation
        is supported, if wTimeTableDESC in the camera description is set.
        After  the  camera is started  it will take a series of consecutive
        images with delay and exposure times, as defined in the table. The
        first found exposure time entry with value zero does break the sequence
        and operation starts again from the beginning of the table.
        This results in a sequence of 1 to 16 images with different delay
        and exposure time settings. External or automatic image triggering
        is fully functional for every image in the sequence. If the user wants
        maximum speed (at CCDs overlapping exposure and read out is taken),
        [auto  trigger] should be selected and the sequence should be
        controlled with the <acq enbl> input. The commands
        PCO_SetDelayExposureTime and PCO_SetDelayExposureTimeTable can only
        be used alternatively. Using PCO_SetDelayExposureTime has the same
        effect as using the PCO_SetDelayExposureTimeTable command and
        setting all but the first delay / exposure entry to zero.

        Restrictions for the parameter values are defined through the
        following values in the camera description PCO_Description structure:
        dwMinDelayDESC, dwMaxDelayDESC, dwMinDelayStepDESC, dwMinExposDESC,
        dwMaxExposDESC, dwMinExposStepDESC
        """

        timebase = {"ns": 0, "us": 1, "ms": 2}

        dwDelay = (C.c_uint32 * 16)()
        dwExposure = (C.c_uint32 * 16)()
        wTimeBaseDelay = C.c_uint16(timebase[timebase_delay])
        wTimeBaseExposure = C.c_uint16(timebase[timebase_exposure])
        wCount = C.c_uint16(count)

        for c in range(count):
            dwDelay[c] = delay[c]
            dwExposure[c] = exposure[c]

        p_delay = C.cast(dwDelay, C.POINTER(C.c_uint32))
        p_exposure = C.cast(dwExposure, C.POINTER(C.c_uint32))

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetDelayExposureTimeTable(
            self.camera_handle, p_delay, p_exposure, wTimeBaseDelay, wTimeBaseExposure, wCount
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update(
            {
                "delay": delay,
                "timebase_delay": timebase_delay,
                "exposure": exposure,
                "timebase_exposure ": timebase_exposure,
                "count": count,
            }
        )

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.6.8 PCO_GetFrameRate
    # -------------------------------------------------------------------------
    def get_frame_rate(self):
        """


        :return: {'status': int,
                  'frame rate mHz': int,
                  'exposure time ns': int,}
        :rtype: dict
        """

        wFrameRateStatus = C.c_uint16()
        dwFrameRate = C.c_uint32()
        dwFrameRateExposure = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetFrameRate(self.camera_handle, wFrameRateStatus, dwFrameRate, dwFrameRateExposure)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update(
                {
                    "status": wFrameRateStatus.value,
                    "frame rate mHz": dwFrameRate.value,
                    "exposure time ns": dwFrameRateExposure.value,
                }
            )

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.9 PCO_SetFrameRate
    # -------------------------------------------------------------------------
    def set_frame_rate(self, frame_rate_mhz, exposure_time_ns):
        """"""

        wFrameRateStatus = C.c_uint16()
        wFrameRateMode = C.c_uint16()
        dwFrameRate = C.c_uint32(frame_rate_mhz)
        dwFrameRateExposure = C.c_uint32(exposure_time_ns)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetFrameRate(
            self.camera_handle,
            wFrameRateStatus,
            wFrameRateMode,
            dwFrameRate,
            dwFrameRateExposure,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update(
                {
                    "status": wFrameRateStatus.value,
                    "mode": wFrameRateMode.value,
                    "frame rate mHz": dwFrameRate.value,
                    "exposure time ns": dwFrameRateExposure.value,
                }
            )

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.10 PCO_GetFPSExposureMode
    # -------------------------------------------------------------------------
    def get_fps_exposure_mode(self):
        """
        This function returns the status of FPS exposure mode setting and
        according exposure time information.
        """

        wFPSExposureMode = C.c_uint16()
        dwFPSExposureTime = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetFPSExposureMode(self.camera_handle, wFPSExposureMode, dwFPSExposureTime)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            fps_exposure_mode = {0: "off", 1: "on"}
            ret.update(
                {
                    "fps exposure mode": fps_exposure_mode[wFPSExposureMode.value],
                    "fps exposure time": fps_exposure_mode[dwFPSExposureTime.value],
                }
            )

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.11 PCO_SetFPSExposureMode
    # -------------------------------------------------------------------------
    def set_fps_exposure_mode(self, fps_exposure_mode):
        """
        This function does set the image timing of the camera so that the
        maximum frame rate and the maximum exposure time for this frame rate is
        achieved. The maximum image frame rate (FPS = frames per second)
        depends on the pixel rate and the image area selection.
        """

        mode = {"off": 0, "on": 1}
        wFPSExposureMode = C.c_uint16(mode[fps_exposure_mode])
        dwFPSExposureTime = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetFPSExposureMode(self.camera_handle, wFPSExposureMode, dwFPSExposureTime)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"fps exposure time [ns]": dwFPSExposureTime.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.12 PCO_GetTriggerMode
    # -------------------------------------------------------------------------
    def get_trigger_mode(self):
        """

        :return: {'trigger mode': str}
        :rtype: dict
        """

        wTriggerMode = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetTriggerMode(self.camera_handle, wTriggerMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            trigger_mode = {
                0: "auto sequence",
                1: "software trigger",
                2: "external exposure start & software trigger",
                3: "external exposure control",
                4: "external synchronized",
                5: "fast external exposure control",
                6: "external CDS control",
                7: "slow external exposure control",
                258: "external synchronized HDSDI",
            }
            ret.update({"trigger mode": trigger_mode[wTriggerMode.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.13 PCO_SetTriggerMode
    # -------------------------------------------------------------------------
    def set_trigger_mode(self, mode):
        """


        :param mode: str

            * 'auto sequence'
            * 'software trigger'
            * 'external exposure start & software trigger'
            * 'external exposure control'
            * 'external synchronized'
            * 'fast external exposure control'
            * 'external CDS control'
            * 'slow external exposure control'
            * 'external synchronized HDSDI'
        """

        trigger_mode = {
            "auto sequence": 0,
            "software trigger": 1,
            "external exposure start & software trigger": 2,
            "external exposure control": 3,
            "external synchronized": 4,
            "fast external exposure control": 5,
            "external CDS control": 6,
            "slow external exposure control": 7,
            "external synchronized HDSDI": 258,
        }

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetTriggerMode(self.camera_handle, trigger_mode[mode])
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"trigger mode": mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.6.14 PCO_ForceTrigger
    # -------------------------------------------------------------------------
    def force_trigger(self):
        """
        Force software trigger

        >>> force_trigger()
        {'triggered': unsuccessful}

        >>> force_trigger()
        {'triggered': successful}

        """

        wTriggered = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_ForceTrigger(self.camera_handle, wTriggered)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            state = {0: "unsuccessful", 1: "successful"}
            ret.update({"triggered": state[wTriggered.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.15 PCO_GetCameraBusyStatus
    # -------------------------------------------------------------------------
    def get_camera_busy_status(self):
        """


        :return: {'busy status': int}
        :rtype: dict

        >>> get_camera_busy_status()
        {'busy status': ready}

        >>> get_camera_busy_status()
        {'busy status': busy}

        """

        wCameraBusyState = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCameraBusyStatus(self.camera_handle, wCameraBusyState)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            busy_status = {0: "ready", 1: "busy"}
            ret.update({"busy status": busy_status[wCameraBusyState.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.16 PCO_GetPowerDownMode (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------
    def get_power_down_mode(self):
        """
        Gets the power down mode of the camera.
        """

        wPowerDownMode = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetPowerDownMode(self.camera_handle, wPowerDownMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            ret.update({"power down mode": wPowerDownMode.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.17 PCO_SetPowerDownMode (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------
    def set_power_down_mode(self, power_down_mode):
        """
        Sets the power down mode of the camera.
        """

        wPowerDownMode = C.c_uint16(power_down_mode)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetPowerDownMode(self.camera_handle, wPowerDownMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.6.18 PCO_GetUserPowerDownTime (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------
    def get_user_power_down_time(self):
        """
        Gets the power down time of the camera.
        """

        dwPowerDownTime = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetUserPowerDownTime(self.camera_handle, dwPowerDownTime)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            ret.update({"power down time": dwPowerDownTime.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.19 PCO_SetUserPowerDownTime (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------

    def set_user_power_down_time(self, power_down_time):
        """
        Sets the power down time of the camera.
        """

        dwPowerDownTime = C.c_uint32(power_down_time)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetUserPowerDownTime(self.camera_handle, dwPowerDownTime)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.6.20 PCO_GetModulationMode (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------

    def get_modulation_mode(self):
        """
        Gets the modulation mode and necessary parameters
        """

        wModulationMode = C.c_uint16()
        dwPeriodicalTime = C.c_uint32()
        wTimebasePeriodical = C.c_uint16()
        dwNumberOfExposures = C.c_uint32()
        lMonitorOffset = C.c_long()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetModulationMode(
            self.camera_handle,
            wModulationMode,
            dwPeriodicalTime,
            wTimebasePeriodical,
            dwNumberOfExposures,
            lMonitorOffset,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"modulation mode": wModulationMode.value})
            ret.update({"periodical time": dwPeriodicalTime.value})
            ret.update({"periodical timebase": wTimebasePeriodical.value})
            ret.update({"number of exposures": dwNumberOfExposures.value})
            ret.update({"monitor offset": lMonitorOffset.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.21 PCO_SetModulationMode (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------
    def set_modulation_mode(
        self, modulation_mode, periodical_time, periodical_timebase, number_of_exposures, monitor_offset
    ):
        """
        Gets the modulation mode and necessary parameters
        """

        wModulationMode = C.c_uint16(modulation_mode)
        dwPeriodicalTime = C.c_uint32(periodical_time)
        wTimebasePeriodical = C.c_uint16(periodical_timebase)
        dwNumberOfExposures = C.c_uint32(number_of_exposures)
        lMonitorOffset = C.c_long(monitor_offset)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetModulationMode(
            self.camera_handle,
            wModulationMode,
            dwPeriodicalTime,
            wTimebasePeriodical,
            dwNumberOfExposures,
            lMonitorOffset,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.6.22 PCO_GetHWIOSignalCount
    # -------------------------------------------------------------------------

    def get_hwio_signal_count(self):
        """
        This function returns the number of hardware I/O signal lines, which
        are available at the camera.
        """

        wNumSignals = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetHWIOSignalCount(self.camera_handle, wNumSignals)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"hwio signal count": wNumSignals.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.23 PCO_GetHWIOSignalDescriptor
    # -------------------------------------------------------------------------
    def get_hwio_signal_descriptor(self, signal_number):
        """
        This function does retrieve the description of a distinct hardware
        I/O signal line.
        """

        wSignalNum = C.c_uint16(signal_number)
        pstrSignal = PCO_Single_Signal_Desc()
        pstrSignal.wSize = C.sizeof(PCO_Single_Signal_Desc)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetHWIOSignalDescriptor(self.camera_handle, wSignalNum, pstrSignal)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            temp_list = []
            for n in range(4):
                for i in range(0 + n * 25, 25 + n * 25):
                    temp_list.append(pstrSignal.strSignalName[i])

            signal_names = [
                bytes(temp_list[0:25]).decode("ascii").strip("\0"),
                bytes(temp_list[25:50]).decode("ascii").strip("\0"),
                bytes(temp_list[50:75]).decode("ascii").strip("\0"),
                bytes(temp_list[75:100]).decode("ascii").strip("\0"),
            ]

            ret.update(
                {
                    "signal name": signal_names,
                    "signal definition": pstrSignal.wSignalDefinitions,
                    "signal types": pstrSignal.wSignalTypes,
                    "signal polarity": pstrSignal.wSignalPolarity,
                    "signal filter": pstrSignal.wSignalFilter,
                }
            )

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.24 PCO_GetHWIOSignal
    # -------------------------------------------------------------------------
    def get_hwio_signal(self, index):
        """
        This function returns the current settings of a distinct hardware input/output (IO) signal line.
        """

        wSignalNum = C.c_uint16(index)

        strHWIOSignal = PCO_Signal()
        strHWIOSignal.wSize = C.sizeof(PCO_Signal)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetHWIOSignal(self.camera_handle, wSignalNum, strHWIOSignal)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            wEnabled_states = {0x0000: "off", 0x0001: "on"}

            wType_states = {
                0x0001: "TTL",
                0x0002: "high level TTL",
                0x0004: "contact mode",
                0x0008: "RS485 differential",
                0x0080: "two pin differential",
            }

            wPolarity_states = {
                0x0001: "high level",
                0x0002: "low level",
                0x0004: "rising edge",
                0x0008: "falling edge",
            }

            wFilter_state = {
                0x0000: "error",
                0x0001: "off",
                0x0002: "medium",
                0x0004: "high",
            }

            parameter = [
                strHWIOSignal.dwParameter[0],
                strHWIOSignal.dwParameter[1],
                strHWIOSignal.dwParameter[2],
                strHWIOSignal.dwParameter[3],
            ]

            functionality = [
                strHWIOSignal.dwSignalFunctionality[0],
                strHWIOSignal.dwSignalFunctionality[1],
                strHWIOSignal.dwSignalFunctionality[2],
                strHWIOSignal.dwSignalFunctionality[3],
            ]

            ret.update({"enabled": wEnabled_states[strHWIOSignal.wEnabled]})
            ret.update({"type": wType_states[strHWIOSignal.wType]})
            ret.update({"polarity": wPolarity_states[strHWIOSignal.wPolarity]})
            ret.update({"filter": wFilter_state[strHWIOSignal.wFilter]})
            ret.update({"selected": strHWIOSignal.wSelected})
            ret.update({"parameter": parameter})
            ret.update({"signal functionality": functionality})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.25 PCO_SetHWIOSignal
    # -------------------------------------------------------------------------
    def set_hwio_signal(self, index, enabled, signal_type, polarity, filter_type, selected, parameter):
        """
        This function does select the settings of a distinct hardware IO signal line.
        """

        wEnabled_states = {"off": 0x0000, "on": 0x0001}

        wType_states = {
            "TTL": 0x0001,
            "high level TTL": 0x0002,
            "contact mode": 0x0004,
            "RS485 differential": 0x0008,
            "two pin differential": 0x0080,
        }

        wPolarity_states = {
            "high level": 0x0001,
            "low level": 0x0002,
            "rising edge": 0x0004,
            "falling edge": 0x0008,
        }

        wFilter_state = {"off": 0x0001, "medium": 0x0002, "high": 0x0004}

        wSignalNum = C.c_uint16(index)
        strHWIOSignal = PCO_Signal()
        strHWIOSignal.wSize = C.sizeof(PCO_Signal)

        strHWIOSignal.wEnabled = wEnabled_states[enabled]
        strHWIOSignal.wType = wType_states[signal_type]
        strHWIOSignal.wPolarity = wPolarity_states[polarity]
        strHWIOSignal.wFilter = wFilter_state[filter_type]

        strHWIOSignal.wSelected = selected

        strHWIOSignal.dwParameter[0] = parameter[0]
        strHWIOSignal.dwParameter[1] = parameter[1]
        strHWIOSignal.dwParameter[2] = parameter[2]
        strHWIOSignal.dwParameter[3] = parameter[3]

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetHWIOSignal(self.camera_handle, wSignalNum, strHWIOSignal)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update(
            {
                "index": index,
                "enabled": enabled,
                "signal type": signal_type,
                "polarity": polarity,
                "filter type": filter_type,
            }
        )

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.6.26 PCO_GetHWIOSignalTiming
    # -------------------------------------------------------------------------
    def get_hwio_signal_timing(self):
        """
        Gets the signal timing and selected signal functionality of the requested signal number
        """

        pwSignalNum = C.c_uint16()
        pwSelect = C.c_uint16()
        pdwSignalTiming = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetHWIOSignalTiming(self.camera_handle, pwSignalNum, pwSelect, pdwSignalTiming)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"signal number": pwSignalNum.value})
            ret.update({"signal functionality": pwSelect.value})
            ret.update({"signal timing": pdwSignalTiming.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.27 PCO_SetHWIOSignalTiming
    # -------------------------------------------------------------------------

    def set_hwio_signal_timing(self, signal_number, signal_functionality, signal_timing):
        """
        Sets the signal timing and selected signal functionality of the requested signal number
        """

        pwSignalNum = C.c_uint16(signal_number)
        pwSelect = C.c_uint16(signal_functionality)
        pdwSignalTiming = C.c_uint32(signal_timing)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetHWIOSignalTiming(self.camera_handle, pwSignalNum, pwSelect, pdwSignalTiming)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.6.28 PCO_GetImageTiming
    # -------------------------------------------------------------------------

    def get_image_timing(self):
        """
        This function returns the current image timing in nanosecond resolution
        and additional trigger system information.
        """

        pstrImageTiming = PCO_ImageTiming()
        pstrImageTiming.wSize = C.sizeof(PCO_ImageTiming)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetImageTiming(self.camera_handle, pstrImageTiming)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"frame time ns": pstrImageTiming.FrameTime_ns})
            ret.update({"frame time s": pstrImageTiming.FrameTime_s})
            ret.update({"exposure time ns": pstrImageTiming.ExposureTime_ns})
            ret.update({"exposure time s": pstrImageTiming.ExposureTime_s})
            ret.update({"trigger system delay ns": pstrImageTiming.TriggerSystemDelay_ns})
            ret.update({"trigger system jitter ns": pstrImageTiming.TriggerSystemJitter_ns})
            ret.update({"trigger delay ns": pstrImageTiming.TriggerDelay_ns})
            ret.update({"trigger delay s": pstrImageTiming.TriggerDelay_s})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.29 PCO_GetCameraSynchMode
    # -------------------------------------------------------------------------
    def get_camera_synch_mode(self):
        """"""

        wCameraSynchMode = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCameraSynchMode(self.camera_handle, wCameraSynchMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            mode = {0: "off", 1: "master", 2: "slave"}
            ret.update({"camera sync mode": mode[wCameraSynchMode.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.30 PCO_SetCameraSynchMode
    # -------------------------------------------------------------------------
    def set_camera_synch_mode(self, synch_mode):
        """"""

        mode = {"off": 0, "master": 1, "slave": 2}
        wCameraSynchMode = C.c_uint16(mode[synch_mode])

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetCameraSynchMode(self.camera_handle, wCameraSynchMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"synch mode": synch_mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.6.31 PCO_GetExpTrigSignalStatus
    # -------------------------------------------------------------------------
    def get_exp_trig_signal_status(self):
        """
        Get exposure trigger signal status

        :return: {'exposure trigger signal status': str}
        :rtype: dict
        """

        wExposureTriggerSignalStatus = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetExpTrigSignalStatus(self.camera_handle, wExposureTriggerSignalStatus)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            status = {0: "off", 1: "on"}
            ret.update({"exposure trigger signal status": status[wExposureTriggerSignalStatus.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.32 PCO_GetFastTimingMode
    # -------------------------------------------------------------------------
    def get_fast_timing_mode(self):
        """"""

        wFastTimingMode = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetFastTimingMode(self.camera_handle, wFastTimingMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            mode = {0: "off", 1: "on"}
            ret.update({"fast timing mode": mode[wFastTimingMode.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.6.33 PCO_SetFastTimingMode
    # -------------------------------------------------------------------------
    def set_fast_timing_mode(self, fast_timing_mode):
        """"""

        mode = {"off": 0, "on": 1}
        wFastTimingMode = C.c_uint16(mode[fast_timing_mode])

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetFastTimingMode(self.camera_handle, wFastTimingMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"fast timing mode": fast_timing_mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.7.1 PCO_GetRecordingStruct (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------
    def get_recording_struct(self):
        """
        Gets all of the recording data in one structure.
        """

        strRecording = PCO_Recording()
        strRecording.wSize = C.sizeof(PCO_Recording)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetRecordingStruct(self.camera_handle, strRecording)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        storage_mode = {0: "recorder", 1: "fifo"}
        rec_submode = {0: "sequence", 1: "ringbuffer"}
        rec_state = {0: "off", 1: "on"}
        acquire_mode = {0: "internal auto", 1: "external"}
        acquire_status = {0: "disabled", 1: "enabled"}
        timestamp_mode = {0: "off", 1: "binary", 2: "binary & ascii", 3: "ascii"}
        record_stop_mode = {0: "no stop event", 1: "stop with event"}
        metadata_mode = {0: "off", 1: "on"}

        if error == 0:
            ret.update({"storage mode": storage_mode[strRecording.wStorageMode]})
            ret.update({"recorder submode": rec_submode[strRecording.wRecSubmode]})
            ret.update({"recorder state": rec_state[strRecording.wRecState]})
            ret.update({"acquire mode": acquire_mode[strRecording.wAcquMode]})
            ret.update({"acquire enable status": acquire_status[strRecording.wAcquEnableStatus]})
            ret.update({"day": strRecording.ucDay})
            ret.update({"month": strRecording.ucMonth})
            ret.update({"year": strRecording.wYear})
            ret.update({"hour": strRecording.wHour})
            ret.update({"minute": strRecording.ucMin})
            ret.update({"second": strRecording.ucSec})
            ret.update({"timestamp mode": timestamp_mode[strRecording.wTimeStampMode]})
            ret.update({"record stopevent mode": record_stop_mode[strRecording.wRecordStopEventMode]})
            ret.update({"metadata mode": metadata_mode[strRecording.wMetaDataMode]})
            ret.update({"metadata size": strRecording.wMetaDataSize})
            ret.update({"metadata version": strRecording.wMetaDataVersion})
            ret.update({"acquire mode extended number of images": strRecording.dwAcquModeExNumberImages})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.7.2 PCO_SetRecordingStruct (for the moment intentionally not implemented)
    # -------------------------------------------------------------------------

    def set_recording_struct(self):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.7.3 PCO_GetRecordingState
    # -------------------------------------------------------------------------
    def get_recording_state(self):
        """
        Returns the current recording state of the camera.

        :return: {'recording state': str}
        :rtype: dict

        >>> get_recording_state()
        {'recording state': 'off'}

        >>> get_recording_state()
        {'recording state': 'on'}

        """

        wRecState = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetRecordingState(self.camera_handle, wRecState)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            recording_state = {0: "off", 1: "on"}
            ret.update({"recording state": recording_state[wRecState.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.7.4 PCO_SetRecordingState
    # -------------------------------------------------------------------------
    def set_recording_state(self, state):
        """
        Set recording state

        :param state: str

            * 'on'
            * 'off'

        """

        recording_state = {"off": 0, "on": 1}

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetRecordingState(self.camera_handle, recording_state[state])
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"recording state": state})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.7.5 PCO_GetStorageMode
    # -------------------------------------------------------------------------
    def get_storage_mode(self):
        """
        This function returns the current storage mode of the camera. Storage
        mode is either [recorder] or [FIFO buffer].
        """

        wStorageMode = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetStorageMode(self.camera_handle, wStorageMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            storage_mode = {0: "recorder", 1: "fifo"}
            ret.update({"storage mode": storage_mode[wStorageMode.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.7.6 PCO_SetStorageMode
    # -------------------------------------------------------------------------
    def set_storage_mode(self, mode):
        """
        This function does set the storage mode of the camera. Storage mode can
        be set to either [recorder] or [FIFO buffer] mode.
        """

        storage_mode = {"recorder": 0, "fifo": 1}
        wStorageMode = C.c_uint16(storage_mode[mode])

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetStorageMode(self.camera_handle, wStorageMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"storage mode": mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.7.7 PCO_GetRecorderSubmode
    # -------------------------------------------------------------------------
    def get_recorder_submode(self):
        """
        This function returns the current recorder submode of the camera.
        Recorder submode is only available if the storage mode is set to
        [recorder]. Recorder submode is either [sequence] or [ring buffer].
        """

        wRecSubmode = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetRecorderSubmode(self.camera_handle, wRecSubmode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            submode = {0: "sequence", 1: "ring buffer"}
            ret.update({"recorder submode": submode[wRecSubmode.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.7.8 PCO_SetRecorderSubmode
    # -------------------------------------------------------------------------
    def set_recorder_submode(self, submode):
        """
        This function sets the recorder submode of the camera. Recorder submode
        is only available if PCO_SetStorageMode is set to [recorder]. Recorder
        submode can be set to [sequence] or [ring buffer].
        """

        recorder_submode = {"sequence": 0, "ring buffer": 1}
        wRecSubmode = C.c_uint16(recorder_submode[submode])

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetRecorderSubmode(self.camera_handle, wRecSubmode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"recorder submode": submode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.7.9 PCO_GetAcquireMode
    # -------------------------------------------------------------------------
    def get_acquire_mode(self):
        """
        This function returns the current acquire mode of the camera. Acquire
        mode can be either [auto], [external] or [external modulate].
        """

        wAcquMode = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetAcquireMode(self.camera_handle, wAcquMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            mode = {0: "auto", 1: "external", 2: "external modulated"}
            ret.update({"acquire mode": mode[wAcquMode.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.7.10 PCO_SetAcquireMode
    # -------------------------------------------------------------------------
    def set_acquire_mode(self, mode):
        """
        This function sets the acquire mode of the camera. Acquire mode can be
        either [auto], [external] or [external modulate].

        :param state: str

            * 'auto'
            * 'external'
            * 'external modulated'

        >>> set_acquire_mode('auto')

        >>> set_acquire_mode('external')

        >>> set_acquire_mode('external modulated')

        """

        acquire_mode = {"auto": 0, "external": 1, "external modulated": 2}
        wAcquMode = C.c_uint16(acquire_mode[mode])

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetAcquireMode(self.camera_handle, wAcquMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"acquire mode": mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.7.11 PCO_GetAcquireModeEx
    # -------------------------------------------------------------------------
    def get_acquire_mode_ex(self):
        """
        This function returns the current acquire mode of the camera. Acquire
        mode can be either [auto], [external], [external modulate] or
        [sequence trigger]. This function is an extended version of the
        PCO_GetAcquireMode function with an additional parameter
        dwNumberImages, which is needed for the [sequence trigger] mode.

        >>> get_acquire_mode_ex()
        {'acquire mode ex': 'auto', 'number of images': 0}

        >>> get_acquire_mode_ex()
        {'acquire mode ex': 'external', 'number of images': 0}

        >>> get_acquire_mode_ex()
        {'acquire mode ex': 'external modulated', 'number of images': 0}

        >>> get_acquire_mode_ex()
        {'acquire mode ex': 'sequence trigger', 'number of images': 100}


        """

        wAcquMode = C.c_uint16()
        dwNumberImages = C.c_uint32()
        dwReserved = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetAcquireModeEx(self.camera_handle, wAcquMode, dwNumberImages, dwReserved)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            acquire_mode_ex = {
                0: "auto",
                1: "external",
                2: "external modulated",
                4: "sequence trigger",
            }
            ret.update({"acquire mode ex": acquire_mode_ex[wAcquMode.value]})
            ret.update({"number of images": dwNumberImages.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.7.12 PCO_SetAcquireModeEx
    # -------------------------------------------------------------------------
    def set_acquire_mode_ex(self, mode, number_of_images=0):
        """
        This function sets the acquire mode of the camera. Acquire mode can be
        either [auto], [external], [external modulate] or [sequence trigger].
        This function is an extended version of the PCO_SetAcquireMode
        function with an additional parameter dwNumberImages, which is needed
        for the [sequence trigger] mode.

        >>> set_acquire_mode_ex('auto')

        >>> set_acquire_mode_ex('auto', 0)

        >>> set_acquire_mode_ex('external')

        >>> set_acquire_mode_ex('external modulated')

        >>> set_acquire_mode_ex('sequence trigger', 100)

        """

        acquire_mode_ex = {
            "auto": 0,
            "external": 1,
            "external modulated": 2,
            "sequence trigger": 4,
        }
        wAcquMode = C.c_uint16(acquire_mode_ex[mode])
        dwNumberImages = C.c_uint32(number_of_images)
        dwReserved = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetAcquireModeEx(self.camera_handle, wAcquMode, dwNumberImages, dwReserved)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"acquire mode": mode})
        inp.update({"number of images": number_of_images})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.7.13 PCO_GetAcqEnblSignalStatus
    # -------------------------------------------------------------------------
    def get_acq_enbl_signal_status(self):
        """

        :return: {'acquire enable signal status': str}
        :rtype: dict
        """

        wAcquireEnableSignalStatus = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetAcqEnblSignalStatus(self.camera_handle, wAcquireEnableSignalStatus)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            acquire_enable_signal_status = {0: "false", 1: "true"}
            ret.update({"acquire enable signal status": acquire_enable_signal_status[wAcquireEnableSignalStatus.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.7.14 PCO_GetAcquireControl
    # -------------------------------------------------------------------------
    def get_acquire_control(self):
        """
        Gets the acquire control flags of the camera.
        """

        dwAcquCtrlFlags = C.c_uint32()
        dwReserved = C.c_uint32(0)
        wNumReserved = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetAcquireControl(self.camera_handle, dwAcquCtrlFlags, dwReserved, wNumReserved)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"acquire control flags": dwAcquCtrlFlags.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.7.15 PCO_SetAcquireControl
    # -------------------------------------------------------------------------
    def set_acquire_control(self, acquire_control_flags):
        """
        Sets the acquire control flags of the camera.
        """

        dwAcquCtrlFlags = C.c_uint32(acquire_control_flags)
        dwReserved = C.c_uint32(0)
        wNumReserved = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetAcquireControl(self.camera_handle, dwAcquCtrlFlags, dwReserved, wNumReserved)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.7.16 PCO_GetMetaDataMode
    # -------------------------------------------------------------------------
    def get_metadata_mode(self):
        """
        Get metadata mode

        :return: {'metadata mode': str}
        :rtype: dict
        """

        wMetaDataMode = C.c_uint16()
        wMetaDataSize = C.c_uint16()
        wMetaDataVersion = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetMetaDataMode(self.camera_handle, wMetaDataMode, wMetaDataSize, wMetaDataVersion)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            metadata_mode = {0: "off", 1: "on"}
            ret.update({"metadata mode": metadata_mode[wMetaDataMode.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.7.17 PCO_SetMetaDataMode
    # -------------------------------------------------------------------------
    def set_metadata_mode(self, mode):
        """
        :param mode: str

            * 'on'
            * 'off'
        """

        metadata_mode = {"off": 0, "on": 1}
        wMetaDataSize = C.c_uint16()
        wMetaDataVersion = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetMetaDataMode(
            self.camera_handle, metadata_mode[mode], wMetaDataSize, wMetaDataVersion
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"meta data mode": mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.7.18 PCO_GetRecordStopEvent
    # -------------------------------------------------------------------------
    def get_record_stop_event(self):
        """
        This function returns the current record stop event mode and the number
        of images, which will be recorded after a recorder stop event is
        triggered. The record stop event mode is only valid, if storage mode is
        [recorder] and recorder submode is [ring buffer].
        """

        wRecordStopEventMode = C.c_uint16()
        dwRecordStopDelayImages = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetRecordStopEvent(self.camera_handle, wRecordStopEventMode, dwRecordStopDelayImages)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            mode = {0: "off", 1: "software", 2: "extern"}
            ret.update({"record stop event  mode": mode[wRecordStopEventMode.value]})
            ret.update({"record stop delay images": dwRecordStopDelayImages.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.7.19 PCO_SetRecordStopEvent
    # -------------------------------------------------------------------------
    def set_record_stop_event(self, record_stop_event_mode, record_stop_delay_images):
        """"""

        mode = {"off": 0, "software": 1, "extern": 2}
        wRecordStopEventMode = C.c_uint16(mode[record_stop_event_mode])
        dwRecordStopDelayImages = C.c_uint32(record_stop_delay_images)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetRecordStopEvent(self.camera_handle, wRecordStopEventMode, dwRecordStopDelayImages)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"record stop event  mode": record_stop_event_mode})
        inp.update({"record stop delay images": record_stop_delay_images})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.7.20 PCO_StopRecord
    # -------------------------------------------------------------------------
    def stop_record(self):
        """"""

        wReserved0 = C.c_uint16()
        dwReserved1 = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_StopRecord(self.camera_handle, wReserved0, dwReserved1)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.7.21 PCO_SetDateTime
    # -------------------------------------------------------------------------
    def set_date_time(self, year, month, day, hour, minute, second):
        """"""

        ucDay = C.c_uint8(day)
        ucMonth = C.c_uint8(month)
        wYear = C.c_uint16(year)
        wHour = C.c_uint16(hour)
        ucMin = C.c_uint8(minute)
        ucSec = C.c_uint8(second)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetDateTime(self.camera_handle, ucDay, ucMonth, wYear, wHour, ucMin, ucSec)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update(
            {
                "year": year,
                "month": month,
                "day": day,
                "hour": hour,
                "minute": minute,
                "second": second,
            }
        )

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.7.22 PCO_GetTimestampMode
    # -------------------------------------------------------------------------
    def get_timestamp_mode(self):
        """
        Returns the current timestamp mode of the camera.

        :return: {'timestamp mode': str}
        :rtype: dict

        >>> get_timestamp_mode()
        {'timestamp mode': 'off'}

        >>> get_timestamp_mode()
        {'timestamp mode': 'binary'}

        >>> get_timestamp_mode()
        {'timestamp mode': 'binary & ascii'}

        >>> get_timestamp_mode()
        {'timestamp mode': 'ascii'}

        """

        wTimeStampMode = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetTimestampMode(self.camera_handle, wTimeStampMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            timestamp_mode = {0: "off", 1: "binary", 2: "binary & ascii", 3: "ascii"}
            ret.update({"timestamp mode": timestamp_mode[wTimeStampMode.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.7.23 PCO_SetTimestampMode
    # -------------------------------------------------------------------------
    def set_timestamp_mode(self, mode):
        """
        Set timestamp mode


        :param mode: str

            * 'off'
            * 'binary'
            * 'binary & ascii'
            * 'ascii'
        """

        timestamp_mode = {"off": 0, "binary": 1, "binary & ascii": 2, "ascii": 3}

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetTimestampMode(self.camera_handle, timestamp_mode[mode])
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"timestamp mode": mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.8.1 PCO_GetStorageStruct
    # -------------------------------------------------------------------------
    def get_storage_struct(self):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.8.2 PCO_SetStorageStruct
    # -------------------------------------------------------------------------
    def set_storage_struct(self):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.8.3 PCO_GetCameraRamSize
    # -------------------------------------------------------------------------
    def get_camera_ram_size(self):
        """
        Gets the ram and page size of the camera.
        """

        dwRamSize = C.c_uint32()
        wPageSize = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCameraRamSize(self.camera_handle, dwRamSize, wPageSize)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"ram size": dwRamSize.value})
            ret.update({"page size": wPageSize.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.8.4 PCO_GetCameraRamSegmentSize
    # -------------------------------------------------------------------------

    def get_camera_ram_segment_size(self):
        """
        Gets the ram segment sizes of the camera.
        """
        ramSegSize = (C.c_uint32 * 4)()
        dwRamSegSize = C.cast(ramSegSize, C.POINTER(C.c_uint16))

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCameraRamSegmentSize(self.camera_handle, dwRamSegSize)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"ram segment size": ramSegSize})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.8.5 PCO_SetCameraRamSegmentSize
    # -------------------------------------------------------------------------
    def set_camera_ram_segment_size(self, ram_segment_sizes):
        """
        Sets the ram segment sizes of the camera.
        """

        dwRamSegSize = (C.c_uint16 * len(ram_segment_sizes))(*ram_segment_sizes)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetCameraRamSegmentSize(self.camera_handle, dwRamSegSize)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.8.6 PCO_ClearRamSegment
    # -------------------------------------------------------------------------

    def clear_ram_segment(self):
        """
        Clears (deletes all images) of the active ram segment of the camera.
        """
        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_ClearRamSegment(self.camera_handle)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.8.7 PCO_GetActiveRamSegment
    # -------------------------------------------------------------------------

    def get_active_ram_segment(self):
        """
        Gets active ram segment of the camera.
        """
        wActSeg = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetActiveRamSegment(self.camera_handle, wActSeg)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"active ram segment": wActSeg.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.8.8 PCO_SetActiveRamSegment
    # -------------------------------------------------------------------------

    def set_active_ram_segment(self, active_segment):
        """
        Sets active ram segment of the camera.
        """
        wActSeg = C.c_uint16(active_segment)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetActiveRamSegment(self.camera_handle, wActSeg)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.8.9 PCO_GetCompressionMode
    # -------------------------------------------------------------------------

    def get_compression_mode(self):
        """
        Gets the ram compression mode of the camera.
        """
        wCompressionMode = C.c_uint16()
        pdwReserved = C.c_uint32(0)
        wReservedLen = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCompressionMode(self.camera_handle, wCompressionMode, pdwReserved, wReservedLen)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"compression mode": wCompressionMode.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.8.10 PCO_SetCompressionMode
    # -------------------------------------------------------------------------

    def set_compression_mode(self, compression_mode):
        """
        Sets the ram compression mode of the camera.
        """
        wCompressionMode = C.c_uint16(compression_mode)
        pdwReserved = C.c_uint32(0)
        wReservedLen = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetCompressionMode(self.camera_handle, wCompressionMode, pdwReserved, wReservedLen)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.8.11 PCO_GetMaxNumberOfImagesInSegment
    # -------------------------------------------------------------------------

    def get_max_number_of_images_in_segment(self):
        """
        Gets the maximum number of images in active segment.
        """
        dwMaxNumberImages = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetMaxNumberOfImagesInSegment(self.camera_handle, dwMaxNumberImages)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"max images in segment": dwMaxNumberImages.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.9.1 PCO_GetImageStruct
    # -------------------------------------------------------------------------

    def get_image_struct(self):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.9.2 PCO_GetSegmentStruct
    # -------------------------------------------------------------------------
    def get_segment_struct(self, segment_index):
        """
        Gets all of the segment data in one structure.
        """
        wSegment = C.c_uint16(segment_index)
        strSegment = PCO_Segment()
        strSegment.wSize = C.sizeof(PCO_Segment)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetSegmentStruct(self.camera_handle, wSegment, strSegment)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"width": strSegment.wXRes})
            ret.update({"height": strSegment.wYRes})
            ret.update({"binning horz": strSegment.wBinHorz})
            ret.update({"binning vert": strSegment.wBinVert})
            ret.update({"roi x0": strSegment.wRoiX0})
            ret.update({"roi y0": strSegment.wRoiY0})
            ret.update({"roi x1": strSegment.wRoiX1})
            ret.update({"roi y1": strSegment.wRoiY1})
            ret.update({"images in segment": strSegment.dwValidImageCnt})
            ret.update({"max image count": strSegment.dwMaxImageCnt})
            ret.update({"soft roi x0": strSegment.wRoiSoftX0})
            ret.update({"soft roi y0": strSegment.wRoiSoftY0})
            ret.update({"soft roi x1": strSegment.wRoiSoftX1})
            ret.update({"soft roi y1": strSegment.wRoiSoftY1})
            ret.update({"soft roi width": strSegment.wRoiSoftXRes})
            ret.update({"soft roi height": strSegment.wRoiSoftYRes})
            ret.update({"soft roi double image": strSegment.wRoiSoftDouble})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.9.3 PCO_GetSegmentImageSettings
    # -------------------------------------------------------------------------

    def get_segment_image_settings(self, segment_index):
        """
        Gets the sizes information for one segment
        """
        wSegment = C.c_uint16(segment_index)
        wXRes = C.c_uint16()
        wYRes = C.c_uint16()
        wBinHorz = C.c_uint16()
        wBinVert = C.c_uint16()
        wRoiX0 = C.c_uint16()
        wRoiY0 = C.c_uint16()
        wRoiX1 = C.c_uint16()
        wRoiY1 = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetSegmentImageSettings(
            self.camera_handle, wSegment, wXRes, wYRes, wBinHorz, wBinVert, wRoiX0, wRoiY0, wRoiX1, wRoiY1
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"width": wXRes.value})
            ret.update({"height": wYRes.value})
            ret.update({"binning horz": wBinHorz.value})
            ret.update({"binning vert": wBinVert.value})
            ret.update({"roi x0": wRoiX0.value})
            ret.update({"roi y0": wRoiY0.value})
            ret.update({"roi x1": wRoiX1.value})
            ret.update({"roi y1": wRoiY1.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.9.4 PCO_GetNumberOfImagesInSegment
    # -------------------------------------------------------------------------

    def get_number_of_images_in_segment(self, segment_index):
        """
        Gets the number of images in the addressed segment.
        """
        wSegment = C.c_uint16(segment_index)
        dwValidImageCnt = C.c_uint32()
        dwMaxImageCnt = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetNumberOfImagesInSegment(
            self.camera_handle, wSegment, dwValidImageCnt, dwMaxImageCnt
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"images in segment": dwValidImageCnt.value})
            ret.update({"max image count": dwMaxImageCnt.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.9.5 PCO_GetBitAlignment
    # -------------------------------------------------------------------------
    def get_bit_alignment(self):
        """
        Returns the bit alignment of the camera: MSB, LSB

        :return: {'bit alignment': str}
        :rtype: dict

        >>> get_bit_alignment()
        {'bit alignment': 'MSB'}

        >>> get_bit_alignment()
        {'bit alignment': 'LSB'}

        """

        wBitAlignment = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetBitAlignment(self.camera_handle, wBitAlignment)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            bit_alignment = {0: "MSB", 1: "LSB"}
            ret.update({"bit alignment": bit_alignment[wBitAlignment.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.9.6 PCO_SetBitAlignment
    # -------------------------------------------------------------------------
    def set_bit_alignment(self, alignment):
        """
        Set bit alignment

        :param alignment: str

            * 'MSB'
            * 'LSB'

        >>> set_bit_alignment('MSB')

        >>> set_bit_alignment('LSB')

        """

        bit_alignment = {"MSB": 0, "LSB": 1}

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetBitAlignment(self.camera_handle, bit_alignment[alignment])
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"bit alignment": alignment})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.9.7 PCO_GetHotPixelCorrectionMode
    # -------------------------------------------------------------------------
    def get_hot_pixel_correction_mode(self):
        """
        Returns the current hot pixel correction mode of the camera.

        :return: {'hot pixel correction mode': str}
        :rtype: dict

        >>> get_hot_pixel_correction_mode()
        {'hot pixel correction mode': 'off'}

        >>> get_hot_pixel_correction_mode()
        {'hot pixel correction mode': 'on'}

        """

        wHotPixelCorrectionMode = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetHotPixelCorrectionMode(self.camera_handle, wHotPixelCorrectionMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            hot_pixel_correction_mode = {0: "off", 1: "on"}
            ret.update({"hot pixel correction mode": hot_pixel_correction_mode[wHotPixelCorrectionMode.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.9.8 PCO_SetHotPixelCorrectionMode
    # -------------------------------------------------------------------------
    def set_hot_pixel_correction_mode(self, mode):
        """
        Set the hot pixel correction mode.

        :param mode:
            * 'off': disables the hot pixel correction
            * 'on': enables the hot pixel correction

        >>> set_hot_pixel_correction_mode('on')

        >>> set_hot_pixel_correction_mode('off')

        """

        hot_pixel_correction_mode = {"off": 0, "on": 1}

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetHotPixelCorrectionMode(self.camera_handle, hot_pixel_correction_mode[mode])
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"hot pixel correction mode": mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.10.1 PCO_AllocateBuffer
    # 2.10.2 PCO_FreeBuffer
    # 2.10.3 PCO_GetBufferStatus
    # 2.10.4 PCO_GetBuffer
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # 2.11.1 PCO_GetImageEx
    # 2.11.2 PCO_GetImage                                            (obsolete)
    # 2.11.3 PCO_AddBufferEx
    # 2.11.4 PCO_AddBuffer                                           (obsolete)
    # 2.11.5 PCO_AddBufferExtern
    # 2.11.6 PCO_CancelImages
    # 2.11.7 PCO_RemoveBuffer                                        (obsolete)
    # 2.11.8 PCO_GetPendingBuffer
    # 2.11.9 PCO_WaitforBuffer
    # 2.11.10 PCO_EnableSoftROI               (not recommended for new designs)
    # 2.11.11 PCO_GetMetaData                 (not recommended for new designs)
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # 2.12.1 PCO_GetTransferParameter
    # -------------------------------------------------------------------------
    def get_transfer_parameter(self):
        """"""

        buffer = (C.c_uint8 * 80)(0)
        p_buffer = C.cast(buffer, C.POINTER(C.c_void_p))
        ilen = C.c_int(len(buffer))

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetTransferParameter(self.camera_handle, p_buffer, ilen)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"buffer": buffer})
            ret.update({"length": ilen})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.12.2 PCO_SetTransferParameter
    # -------------------------------------------------------------------------
    def set_transfer_parameter(self):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.13.1 PCO_GetSensorSignalStatus                               (pco.edge)
    # -------------------------------------------------------------------------
    def get_sensor_signal_status(self):
        """
        Get sensor signal status.

        :return: {'status': int,
                  'image count': int}
        :rtype: dict
        """

        dwStatus = C.c_uint32()
        dwImageCount = C.c_uint32()
        dwReserved1 = C.c_uint32()
        dwReserved2 = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetSensorSignalStatus(
            self.camera_handle, dwStatus, dwImageCount, dwReserved1, dwReserved2
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"status": dwStatus.value})
            ret.update({"image count": dwImageCount.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.13.2 PCO_GetCmosLineTiming                                   (pco.edge)
    # -------------------------------------------------------------------------
    def get_cmos_line_timing(self):

        wParameter = C.c_uint16()
        wTimebase = C.c_uint16()
        dwLineTime = C.c_uint32()
        dwReserved = C.c_uint32()
        wReservedLen = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCmosLineTiming(
            self.camera_handle,
            wParameter,
            wTimebase,
            dwLineTime,
            dwReserved,
            wReservedLen,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            parameter = {0: "off", 1: "on"}
            ret.update({"parameter": parameter[wParameter.value]})
            timebase = {0: 1e-9, 1: 1e-6, 2: 1e-3}
            line_time = timebase[wTimebase.value] * dwLineTime.value
            ret.update({"line time": line_time})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.13.3 PCO_SetCmosLineTiming                                   (pco.edge)
    # -------------------------------------------------------------------------
    def set_cmos_line_timing(self, parameter, line_time):
        """"""

        if line_time <= 4.0:
            linetime = int(line_time * 1e9)
            timebase = "ns"
        else:
            linetime = int(line_time * 1e6)
            timebase = "us"

        parameter_dict = {"off": 0, "on": 1}
        timebase_dict = {"ns": 0, "us": 1, "ms": 2}

        wParameter = C.c_uint16(parameter_dict[parameter])
        wTimebase = C.c_uint16(timebase_dict[timebase])
        dwLineTime = C.c_uint32(linetime)
        dwReserved = C.c_uint32(0)
        wReservedLen = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetCmosLineTiming(
            self.camera_handle,
            wParameter,
            wTimebase,
            dwLineTime,
            dwReserved,
            wReservedLen,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"parameter": parameter})
        inp.update({"timebase": timebase})
        inp.update({"line time": linetime})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.13.4 PCO_GetCmosLineExposureDelay                            (pco.edge)
    # -------------------------------------------------------------------------
    def get_cmos_line_exposure_delay(self):
        """"""

        dwExposureLines = C.c_uint32()
        dwDelayLines = C.c_uint32()
        dwReserved = C.c_uint32()
        wReservedLen = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCmosLineExposureDelay(
            self.camera_handle, dwExposureLines, dwDelayLines, dwReserved, wReservedLen
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"lines exposure": dwExposureLines.value})
            ret.update({"lines delay": dwDelayLines.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.13.5 PCO_SetCmosLineExposureDelay                            (pco.edge)
    # -------------------------------------------------------------------------
    def set_cmos_line_exposure_delay(self, lines_exposure, lines_delay):

        dwExposureLines = C.c_uint32(lines_exposure)
        dwDelayLines = C.c_uint32(lines_delay)
        dwReserved = C.c_uint32()
        wReservedLen = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetCmosLineExposureDelay(
            self.camera_handle, dwExposureLines, dwDelayLines, dwReserved, wReservedLen
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"lines exposure ": lines_exposure})
        inp.update({"lines delay": lines_delay})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.13.6 PCO_SetTransferParametersAuto                           (pco.edge)
    # -------------------------------------------------------------------------
    def set_transfer_parameters_auto(self, buffer):
        """"""

        p_buffer = C.cast(buffer, C.POINTER(C.c_void_p))
        ilen = C.c_int(len(buffer))

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetTransferParametersAuto(self.camera_handle, p_buffer, ilen)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.13.7 PCO_GetInterfaceOutputFormat                            (pco.edge)
    # -------------------------------------------------------------------------
    def get_interface_output_format(self, interface):
        """
        :param interface: str

            * 'edge'
        :return: {'format': int}
        :rtype: dict
        """

        interface_types = {"edge": 0x0002}

        wDestInterface = C.c_uint16(interface_types[interface])
        wFormat = C.c_uint16()
        wReserved1 = C.c_uint16()
        wReserved2 = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetInterfaceOutputFormat(
            self.camera_handle, wDestInterface, wFormat, wReserved1, wReserved2
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"format": wFormat.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.13.8 PCO_SetInterfaceOutputFormat                            (pco.edge)
    # -------------------------------------------------------------------------
    def set_interface_output_format(self, interface, format):
        """
        Set interface output format

        :param interface: set interfcae parameter to 'edge' for changing the
            readout direction of the SCMOS image sensor
        :param format:

            * 'top bottom'
            * 'top center bottom center'
            * 'center top center bottom'
            * 'center top bottom center'
            * 'top center center bottom'
        """

        interface_types = {"edge": 0x0002}
        output_format_types = {
            "top bottom": 0x0000,
            "top center bottom center": 0x0100,
            "center top center bottom": 0x0200,
            "center top bottom center": 0x0300,
            "top center center bottom": 0x0400,
            "inverse": 0x0500,
        }

        wDestInterface = C.c_uint16(interface_types[interface])
        wFormat = C.c_uint16(output_format_types[format])
        wReserved1 = C.c_uint16()
        wReserved2 = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetInterfaceOutputFormat(
            self.camera_handle, wDestInterface, wFormat, wReserved1, wReserved2
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"interface": interface, "output format": format})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.14.1 PCO_GetImageTransferMode                               (pco.dimax)
    def get_image_transfer_mode(self):
        raise NotImplementedError

    # 2.14.2 PCO_SetImageTransferMode                               (pco.dimax)
    def set_image_transfer_mode(self):
        raise NotImplementedError

    # 2.14.3 PCO_GetCDIMode                                         (pco.dimax)
    def get_cdi_mode(self):
        """"""

        wCDIMode = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetCDIMode(self.camera_handle, wCDIMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            ret.update({"cdi mode": wCDIMode.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # 2.14.4 PCO_SetCDIMode                                         (pco.dimax)
    def set_cdi_mode(self, cdi_mode):
        """"""

        wCDIMode = C.c_uint16(cdi_mode)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetCDIMode(self.camera_handle, wCDIMode)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # 2.14.5 PCO_GetPowerSaveMode                                   (pco.dimax)

    def get_power_save_mode(self):
        """"""

        wMode = C.c_uint16()
        wDelayMinutes = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetPowerSaveMode(
            self.camera_handle,
            wMode,
            wDelayMinutes,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            powersave_mode = {0: "off", 1: "on"}
            ret.update({"powersave mode": powersave_mode[wMode.value]})
            ret.update({"delay minutes": wDelayMinutes.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # 2.14.6 PCO_SetPowerSaveMode                                   (pco.dimax)
    def set_power_save_mode(self, mode, delay_minutes):
        """"""

        powersave_mode = {"off": 0, "on": 1}
        wMode = C.c_uint16(powersave_mode[mode])
        wDelayMinutes = C.c_uint16(delay_minutes)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetPowerSaveMode(
            self.camera_handle,
            wMode,
            wDelayMinutes,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # 2.14.7 PCO_GetBatteryStatus                                   (pco.dimax)

    def get_battery_status(self):
        """"""

        wBatteryType = C.c_uint16()
        wBatteryLevel = C.c_uint16()
        wPowerStatus = C.c_uint16()
        wReserved = C.c_uint16()
        wNumReserved = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetBatteryStatus(
            self.camera_handle, wBatteryType, wBatteryLevel, wPowerStatus, wReserved, wNumReserved
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            battery_types = {
                0: "none",
                1: "nickel metal hydride",
                2: "lithium ion",
                3: "lithium iron phosphate",
                65535: "unknown battery",
            }
            ret.update({"battery type": battery_types[wBatteryType.value]})
            ret.update({"battery level": wBatteryLevel.value})
            ret.update({"power status": wPowerStatus.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.15.1 PCO_GetInterfaceOutputFormat                (pco.dimax with HDSDI)
    # 2.15.2 PCO_SetInterfaceOutputFormat                (pco.dimax with HDSDI)
    # 2.15.3 PCO_PlayImagesFromSegmentHDSDI              (pco.dimax with HDSDI)

    def play_images_from_segment_hdsdi(
        self, segment_index, interface, mode, speed, range_low, range_high, start_pos=-1, repeat_last_image=True
    ):
        """
        Sets the actual play conditions for the HDSDI interface.
        """

        play_modes = {"stop play": 0, "fast forward": 1, "fast rewind": 2, "slow forward": 3, "slow rewind": 4}

        wSegment = C.c_uint16(segment_index)
        wInterface = C.c_uint16(interface)
        wMode = C.c_uint16(play_modes[mode])
        if repeat_last_image == True:
            wMode |= 0x100

        wSpeed = C.c_uint16(speed)
        dwRangeLow = C.c_uint32(range_low)
        dwRangeHigh = C.c_uint32(range_high)
        dwStartPos = C.c_uint32(start_pos)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_PlayImagesFromSegmentHDSDI(
            self.camera_handle, wSegment, wInterface, wMode, wSpeed, dwRangeLow, dwRangeHigh, dwStartPos
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # 2.15.4 PCO_GetPlayPositionHDSDI                    (pco.dimax with HDSDI)

    def get_play_position_hdsdi(self):
        """
        Gets the actual play pointer position for the HDSDI interface
        """

        wStatus = C.c_uint16()
        dwPlayPosition = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetPlayPositionHDSDI(self.camera_handle, wStatus, dwPlayPosition)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            status = {0: "inactive", 1: "active"}
            ret.update({"play status": status[wStatus.value]})
            ret.update({"play position": dwPlayPosition.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # 2.15.5 PCO_GetColorSettings                        (pco.dimax with HDSDI)

    def get_color_settings(self):
        """
        Gets the color convert settings inside the camera.
        """

        strColorSet = PCO_Image_ColorSet
        strColorSet.wSize = C.sizeof(PCO_Image_ColorSet)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetColorSettings(self.camera_handle, strColorSet)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"saturation": strColorSet.sSaturation})
            ret.update({"vibrance": strColorSet.sVibrance})
            ret.update({"color temp": strColorSet.wColorTemp})
            ret.update({"tint": strColorSet.sTint})
            ret.update({"mult norm red": strColorSet.wMulNormR})
            ret.update({"mult norm green": strColorSet.wMulNormG})
            ret.update({"mult norm blue": strColorSet.wMulNormB})
            ret.update({"fixed sharpen": strColorSet.wSharpFixed})
            ret.update({"adaptive sharpen": strColorSet.wSharpAdaptive})
            ret.update({"scale min": strColorSet.wScaleMin})
            ret.update({"scale max": strColorSet.wScaleMin})
            ret.update({"proc options": strColorSet.wProcOptions})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # 2.15.6 PCO_SetColorSettings                        (pco.dimax with HDSDI)
    def set_color_settings(
        self,
        saturation=0,
        vibrance=0,
        color_temp=6500,
        tint=0,
        contrast=0,
        gamma=1,
        mult_norm_red=0,
        mult_norm_green=0,
        mult_norm_blue=0,
        fixed_sharpen=0,
        adaptiv_sharpen=0,
        scale_min=0,
        scale_max=65535,
        proc_options=0,
    ):
        """
        Sets the color convert settings inside the camera.
        """

        strColorSet = PCO_Image_ColorSet
        strColorSet.wSize = C.sizeof(PCO_Image_ColorSet)
        strColorSet.sSaturation = saturation
        strColorSet.sVibrance = vibrance
        strColorSet.wColorTemp = color_temp
        strColorSet.sTint = tint
        strColorSet.wMulNormR = mult_norm_red
        strColorSet.wMulNormG = mult_norm_green
        strColorSet.wMulNormB = mult_norm_blue
        strColorSet.wSharpFixed = fixed_sharpen
        strColorSet.wSharpAdaptive = adaptiv_sharpen
        strColorSet.wScaleMin = scale_min
        strColorSet.wScaleMax = scale_max
        strColorSet.wProcOptions = proc_options

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetColorSettings(self.camera_handle, strColorSet)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # 2.15.7 PCO_DoWhiteBalance                          (pco.dimax with HDSDI)

    def do_white_balance(self):
        """
        Starts a white balancing calculation.
        """
        wMode = C.c_uint16(1)
        wParam = (C.c_uint16 * 4)(0)
        pwParam = C.cast(wParam, C.POINTER(C.c_uint16))
        wParamLen = C.c_uint16(4)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_DoWhiteBalance(self.camera_handle, wMode, pwParam, wParamLen)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.16.1 PCO_GetFlimModulationParameter
    # -------------------------------------------------------------------------

    def get_flim_modulation_parameter(self):
        """
        :return: {'source select': str,
                'output waveform': str}
        :rtype: dict

        >>> get_flim_modulation_parameter()
        {'source select': 'intern', 'output waveform': 'sinusoidal'}

        """

        wSourceSelect = C.c_uint16()
        wOutputWaveform = C.c_uint16()
        wReserved1 = C.c_uint16()
        wReserved2 = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetFlimModulationParameter(
            self.camera_handle, wSourceSelect, wOutputWaveform, wReserved1, wReserved2
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            source_select = {0: "intern", 1: "extern"}
            ret.update({"source select": source_select[wSourceSelect.value]})
            output_waveform = {0: "none", 1: "sinusoidal", 2: "rectangular"}
            ret.update({"output waveform": output_waveform[wOutputWaveform.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.16.2 PCO_SetFlimModulationParameter
    # -------------------------------------------------------------------------
    def set_flim_modulation_parameter(self, source_select_mode, output_waveform_mode):
        """
        :param source_select_mode: str

            * 'intern'
            * 'extern'
        :param output_waveform_mode: str

            * 'none'
            * 'sinusoidal'
            * 'rectangular'
        """

        source_select = {"intern": 0, "extern": 1}
        output_waveform = {"none": 0, "sinusoidal": 1, "rectangular": 2}
        wReserved1 = C.c_uint16(0)
        wReserved2 = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetFlimModulationParameter(
            self.camera_handle,
            source_select[source_select_mode],
            output_waveform[output_waveform_mode],
            wReserved1,
            wReserved2,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"source select mode": source_select_mode, "output waveform mode": output_waveform_mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.16.3 PCO_GetFlimMasterModulationFrequency
    # -------------------------------------------------------------------------
    def get_flim_master_modulation_frequency(self):
        """
        Get flim modulation frequency

        :return: {'frequency': int}
        :rtype: dict
        """

        dwFrequency = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetFlimMasterModulationFrequency(self.camera_handle, dwFrequency)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"frequency": dwFrequency.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.16.4 PCO_SetFlimMasterModulationFrequency
    # -------------------------------------------------------------------------
    def set_flim_master_modulation_frequency(self, frequency):
        """

        :param frequency: int
        """

        dwFrequency = C.c_uint32(frequency)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetFlimMasterModulationFrequency(self.camera_handle, dwFrequency)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {"frequency": frequency}

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.16.5 PCO_GetFlimPhaseSequenceParameter
    # -------------------------------------------------------------------------
    def get_flim_phase_sequence_parameter(self):
        """
        :return: {'phase number': str,
                'phase symmetry': str,
                'phase order': str,
                'tap select': str}
        :rtype: dict
        """

        wPhaseNumber = C.c_uint16()
        wPhaseSymmetry = C.c_uint16()
        wPhaseOrder = C.c_uint16()
        wTapSelect = C.c_uint16()
        wReserved1 = C.c_uint16()
        wReserved2 = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetFlimPhaseSequenceParameter(
            self.camera_handle,
            wPhaseNumber,
            wPhaseSymmetry,
            wPhaseOrder,
            wTapSelect,
            wReserved1,
            wReserved2,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            phase_number = {
                0: "manual shifting",
                1: "2 phases",
                2: "4 phases",
                3: "8 phases",
                4: "16 phases",
            }
            ret.update({"phase number": phase_number[wPhaseNumber.value]})
            phase_symmetry = {0: "singular", 1: "twice"}
            ret.update({"phase symmetry": phase_symmetry[wPhaseSymmetry.value]})
            phase_order = {0: "ascending", 1: "opposite"}
            ret.update({"phase order": phase_order[wPhaseOrder.value]})
            tap_select = {0: "both", 1: "tap A", 2: "tap B"}
            ret.update({"tap select": tap_select[wTapSelect.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.16.6 PCO_SetFlimPhaseSequenceParameter
    # -------------------------------------------------------------------------
    def set_flim_phase_sequence_parameter(
        self, phase_number_mode, phase_symmetry_mode, phase_order_mode, tap_select_mode
    ):
        """"""

        phase_number = {
            "manual shifting": 0,
            "2 phases": 1,
            "4 phases": 2,
            "8 phases": 3,
            "16 phases": 4,
        }
        phase_symmetry = {"singular": 0, "twice": 1}
        phase_order = {"ascending": 0, "opposite": 1}
        tap_select = {"both": 0, "tap A": 1, "tap B": 2}
        wReserved1 = C.c_uint16(0)
        wReserved2 = C.c_uint16(0)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetFlimPhaseSequenceParameter(
            self.camera_handle,
            phase_number[phase_number_mode],
            phase_symmetry[phase_symmetry_mode],
            phase_order[phase_order_mode],
            tap_select[tap_select_mode],
            wReserved1,
            wReserved2,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {
            "phase number mode": phase_number_mode,
            "phase symmetry mode": phase_symmetry_mode,
            "phase order mode": phase_order_mode,
            "tap select mode": tap_select_mode,
        }

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.16.7 PCO_GetFlimRelativePhase
    # -------------------------------------------------------------------------
    def get_flim_relative_phase(self):
        """"""

        dwPhaseMilliDeg = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetFlimRelativePhase(self.camera_handle, dwPhaseMilliDeg)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"phase millidegrees": dwPhaseMilliDeg.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.16.8 PCO_SetFlimRelativePhase
    # -------------------------------------------------------------------------
    def set_flim_relative_phase(self, phase_millidegrees):
        """"""

        dwPhaseMilliDeg = C.c_uint32(phase_millidegrees)

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetFlimRelativePhase(self.camera_handle, dwPhaseMilliDeg)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {"phase millidegrees": phase_millidegrees}

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.16.9 PCO_GetFlimImageProcessingFlow
    # -------------------------------------------------------------------------
    def get_flim_image_processing_flow(self):
        """"""

        wAsymmetryCorrection = C.c_uint16()
        wCalculationMode = C.c_uint16()
        wReferencingMode = C.c_uint16()
        wThresholdLow = C.c_uint16()
        wThresholdHigh = C.c_uint16()
        wOutputMode = C.c_uint16()
        wReserved1 = C.c_uint16()
        wReserved2 = C.c_uint16()
        wReserved3 = C.c_uint16()
        wReserved4 = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetFlimImageProcessingFlow(
            self.camera_handle,
            wAsymmetryCorrection,
            wCalculationMode,
            wReferencingMode,
            wThresholdLow,
            wThresholdHigh,
            wOutputMode,
            wReserved1,
            wReserved2,
            wReserved3,
            wReserved4,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            asymmetry_correction = {0: "off", 1: "average"}
            output_mode = {0: "default", 1: "multiply x2"}
            ret.update({"asymmetry correction": asymmetry_correction[wAsymmetryCorrection.value]})
            ret.update({"output mode": output_mode[wOutputMode.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.16.10 PCO_SetFlimImageProcessingFlow
    # -------------------------------------------------------------------------
    def set_flim_image_processing_flow(self, a_c_mode, o_m_mode):
        """"""

        asymmetry_correction = {"off": 0, "average": 1}
        output_mode = {"default": 0, "multiply x2": 1}

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetFlimImageProcessingFlow(
            self.camera_handle,
            asymmetry_correction[a_c_mode],
            0,
            0,
            0,
            0,
            output_mode[o_m_mode],
            0,
            0,
            0,
            0,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {"a c mode": a_c_mode, "o m mode": o_m_mode}

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.17.1 PCO_InitLensControl
    # -------------------------------------------------------------------------
    def init_lens_control(self):
        """"""

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_InitLensControl(self.camera_handle, self.lens_control)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.17.2 PCO_CleanupLensControl
    # -------------------------------------------------------------------------
    def cleanup_lens_control(self):
        """"""
        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_CleanupLensControl()
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.17.3 PCO_CloseLensControl
    # -------------------------------------------------------------------------

    def close_lens_control(self):
        """
        Closes and deletes a lens control object. The handle will be invalid
        afterwards.
        """

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_CloseLensControl(self.lens_control)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        self.lens_control = C.c_void_p(0)

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.17.4 PCO_GetLensFocus
    # -------------------------------------------------------------------------
    def get_lens_focus(self):
        """
        Gets the current focus of the lens control device as value between
        0...0x3FFF.
        """

        lFocusPos = C.c_long()
        dwflags = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetLensFocus(self.lens_control, lFocusPos, dwflags)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"lFocusPos": lFocusPos.value})
            ret.update({"dwflags": dwflags.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.17.5 PCO_SetLensFocus
    # -------------------------------------------------------------------------
    def set_lens_focus(self, focus_pos):
        """
        Sets the focus of the lens control device to a new position. Value must
        be between 0...0x3FFF.
        """

        lFocusPos = C.c_long(focus_pos)
        dwflagsin = C.c_uint32()
        dwflagsout = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetLensFocus(self.lens_control, lFocusPos, dwflagsin, dwflagsout)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"focus_pos": focus_pos})
        inp.update({"dwflagsin": dwflagsin})
        inp.update({"dwflagsout": dwflagsout.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.17.6 PCO_GetAperture
    # -------------------------------------------------------------------------
    def get_aperture(self):
        """"""

        wAperturePos = C.c_uint16()
        dwflags = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetAperture(self.lens_control, wAperturePos, dwflags)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"wAperturePos": wAperturePos.value})
            ret.update({"dwflags": dwflags.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.17.7 PCO_SetAperture
    # -------------------------------------------------------------------------
    def set_aperture(self, aperture_pos):
        """"""

        wAperturePos = C.c_uint16(aperture_pos)
        dwflagsin = C.c_uint32()
        dwflagsout = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetAperture(self.lens_control, wAperturePos, dwflagsin, dwflagsout)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"aperture_pos": aperture_pos})
        inp.update({"aperture_pos": aperture_pos})
        inp.update({"aperture_pos": aperture_pos})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.17.8 PCO_GetApertureF
    # -------------------------------------------------------------------------
    def get_aperture_f(self):
        """"""

        dwAperturePos = C.c_uint32()
        wAperturePos = C.c_uint16()
        dwflags = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetApertureF(self.lens_control, dwAperturePos, wAperturePos, dwflags)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"dwAperturePos f": (dwAperturePos.value / 10.0)})
            ret.update({"wAperturePos": wAperturePos.value})
            ret.update({"dwflags": dwflags.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.17.9 PCO_SetApertureF
    # -------------------------------------------------------------------------
    def set_aperture_f(self, aperture_pos):
        """"""

        aperture_pos_int = int(aperture_pos * 10)

        dwAperturePos = C.c_uint32(aperture_pos_int)
        dwflagsin = C.c_uint32()
        dwflagsout = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetApertureF(self.lens_control, dwAperturePos, dwflagsin, dwflagsout)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"aperture_pos f": aperture_pos})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.17.10 PCO_SendBirgerCommand
    # -------------------------------------------------------------------------
    def send_birger_command(self):
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # 2.18.1 PCO_GetIntensifiedGatingMode
    # -------------------------------------------------------------------------

    def get_intensified_gating_mode(self):
        """
        Gets the gating mode.

        >>> get_intensified_gating_mode()
        {'mode': 'on'}

        >>> get_intensified_gating_mode()
        {'mode': 'off'}

        """

        wIntensifiedGatingMode = C.c_uint16()
        wReserved = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetIntensifiedGatingMode(self.camera_handle, wIntensifiedGatingMode, wReserved)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            modes = {0: "off", 1: "on"}
            ret.update({"mode": modes[wIntensifiedGatingMode.value]})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.18.2 PCO_SetIntensifiedGatingMode
    # -------------------------------------------------------------------------
    def set_intensified_gating_mode(self, mode):
        """
        Sets the gating mode.

        Operating  mode  for  the  MCP  part  of  the  image  intensifier,
        which  controls  the  extinction  ratio  contribution (shutter ratio)
        of the MCP.

        Especially uv and blue light is blocked  less effectively outside  the
        selected  exposure  time  of  the image intensifier. This light
        leakage can negatively influence the image acquisition!  To  prevent
        this  negative  effect,  the  MCP  Intensifier  Voltage  can  be
        switched  off  outside  the photocathode exposure time window to
        increase the system overall extinction ratio.


        Off: MCP gating is disabled, Intensifier Voltage is continously on;
        no contribution of the MCP to the overall extinction ratio. Maximum
        fps can only be achieved with MCP gating Off

        On: MCP gating is enabled; MCP Intensifier  Voltage is switched off
        after the end of the photocathode  exposure  and  reactivated
        immediately  after  the  sCMOS  sensor  readout  is  done; additional
        contribution of the MCP to the overall extinction ratio. Reactivation
        of the Intensifier  Voltage takes an extra 4 ms; this mode slows down
        the maximum achievable framerate.


        >>> set_intensified_gating_mode('on')

        >>> set_intensified_gating_mode('off')

        """

        wIntensifiedGatingMode = C.c_uint16()
        wReserved = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetIntensifiedGatingMode(self.camera_handle, wIntensifiedGatingMode, wReserved)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"mode": mode})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.18.3 PCO_GetIntensifiedMCP
    # -------------------------------------------------------------------------
    def get_intensified_mcp(self):
        """
        Gets the intensified camera setup.

        >>> get_intensified_mcp()
        {'intensified voltage': 900, 'intensified phosphor decay us': value}

        """

        wIntensifiedVoltage = C.c_uint16()
        wReserved = C.c_uint16()
        dwIntensifiedPhosphorDecay_us = C.c_uint32()
        dwReserved1 = C.c_uint32()
        dwReserved2 = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetIntensifiedMCP(
            self.camera_handle, wIntensifiedVoltage, wReserved, dwIntensifiedPhosphorDecay_us, dwReserved1, dwReserved2
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}

        if error == 0:
            ret.update({"intensified voltage": wIntensifiedVoltage.value})
            ret.update({"intensified phosphor decay us": dwIntensifiedPhosphorDecay_us.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.18.4 PCO_SetIntensifiedMCP
    # -------------------------------------------------------------------------
    def set_intensified_mcp(self, intensified_voltage, intensified_phosphor_decay_us):
        """
        Sets the intensified camera setup.

        Select the amount of  the  MCP-Gain of  the  image intensifier.
        Adjustable is the  voltage applied  to the MCP (micro channel plate)
        in the range of 750 V to 1100 V for S20 image intensifiers and 750 V
        to 900 V for GaAs(P) intensifiers. The other two intensifier voltages
        for photocathode and phosphor screen are fixed.

        Note that there is no linear correspondence between the MCP voltage
        and the amount of Gain. The Gain is exponential and typically doubles
        every 50 V.
        Note: start with maximum Intensifier Voltage, closed aperture
        and very short exposure times at each experimental setup to protect the
        image intensifier.

        >>> set_intensified_mcp(900, value)

        """

        wIntensifiedVoltage = C.c_uint16(intensified_voltage)
        wFlags = C.c_uint16()
        wReserved = C.c_uint16()
        dwIntensifiedPhosphorDecay_us = C.c_uint32(intensified_phosphor_decay_us)
        dwReserved1 = C.c_uint32()
        dwReserved2 = C.c_uint32()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetIntensifiedMCP(
            self.camera_handle,
            wIntensifiedVoltage,
            wFlags,
            wReserved,
            dwIntensifiedPhosphorDecay_us,
            dwReserved1,
            dwReserved2,
        )
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"intensified_voltage": intensified_voltage})
        inp.update({"intensified_phosphor_decay_us": intensified_phosphor_decay_us})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # 2.18.5 PCO_GetIntensifiedLoopCount
    # -------------------------------------------------------------------------
    def get_intensified_loop_count(self):
        """
        Gets intensified camera loop count.

        >>> get_intensified_loop_count()
        {'loop count:' 10}

        """

        wIntensifiedLoopCount = C.c_uint16()
        wReserved = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_GetIntensifiedLoopCount(self.camera_handle, wIntensifiedLoopCount, wReserved)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        ret = {}
        if error == 0:
            ret.update({"loop count": wIntensifiedLoopCount.value})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret

    # -------------------------------------------------------------------------
    # 2.18.6 PCO_SetIntensifiedLoopCount
    # -------------------------------------------------------------------------

    def set_intensified_loop_count(self, loop_count):
        """
        Sets intensified camera loop count.

        >>> set_intensified_loop_count(10)

        """

        wIntensifiedLoopCount = C.c_uint16(loop_count)
        wReserved = C.c_uint16()

        time_start = time.perf_counter()
        error = self.SC2_Cam.PCO_SetIntensifiedLoopCount(self.camera_handle, wIntensifiedLoopCount, wReserved)
        duration = time.perf_counter() - time_start
        error_msg = self.get_error_text(error)

        inp = {}
        inp.update({"loop_count": loop_count})

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

    # -------------------------------------------------------------------------
    # -------------------------------------------------------------------------

    def get_version_info_sc2_cam(self):
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

        if sys.platform.startswith("win32"):
            error = self.SC2_Cam.PCO_GetVersionInfoSC2_Cam(
                pszName, iNameLength, pszPath, iPathLength, iMajor, iMinor, iBuild
            )
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

        logger.info("[{:5.3f} s] [sdk] {}: {}".format(duration, sys._getframe().f_code.co_name, error_msg))

        if error:
            raise ValueError("{}: {}".format(error, error_msg))

        return ret
