# Copyright Euresys 2021

"""Symbols and types used by the C API."""

import ctypes

# RECORDER_STATUS
RECORDER_STATUS_OK = 0
RECORDER_STATUS_NOT_INITIALIZED = -1
RECORDER_STATUS_UNKNOWN_ERROR = -2
RECORDER_STATUS_UNKNOWN_PARAMETER = -3
RECORDER_STATUS_INVALID_PARAMETER_TYPE = -4
RECORDER_STATUS_INVALID_PARAMETER_VALUE = -5
RECORDER_STATUS_BUFFER_TOO_SMALL = -6
RECORDER_STATUS_PARAMETER_IS_READ_ONLY = -7
RECORDER_STATUS_SYSTEM_ERROR = -8
RECORDER_STATUS_INVALID_CONTAINER_PATH = -9
RECORDER_STATUS_IO_TIMEOUT = -10
RECORDER_STATUS_DATA_FILE_FULL = -11
RECORDER_STATUS_OPERATION_NOT_ALLOWED = -12
RECORDER_STATUS_INDEX_OUT_OF_RANGE = -13
RECORDER_STATUS_INVALID_INDEX_DATA = -14
RECORDER_STATUS_INVALID_INDEX_SIZE = -15
RECORDER_STATUS_UNSUPPORTED_DATABASE_VERSION = -16
RECORDER_STATUS_INVALID_INDEX_HEADER = -17
RECORDER_STATUS_INVALID_LENGTH_WRITTEN = -18
RECORDER_STATUS_INVALID_HANDLE = -19
RECORDER_STATUS_RESOURCE_IN_USE = -20
RECORDER_STATUS_END_OF_DATA = -21
RECORDER_STATUS_NO_CONTAINER = -22
RECORDER_STATUS_INVALID_ARGUMENT = -23
RECORDER_STATUS_LICENSE_MANAGER_ERROR = -24
RECORDER_STATUS_NO_LICENSE = -25
RECORDER_STATUS_IMAGE_CONVERSION_ERROR = -26
RECORDER_STATUS_UNSUPPORTED_IMAGE_FORMAT = -27
RECORDER_STATUS_ABORTED = -28
RECORDER_STATUS_INVALID_DATA_SIZE = -29
RECORDER_STATUS_INVALID_CHAPTER_CHARACTER = -30
RECORDER_STATUS_RESERVED_CHAPTER_NAME = -31
RECORDER_STATUS_CHAPTER_NAME_ALREADY_USED = -32
RECORDER_STATUS_CHAPTER_NAME_TOO_LONG = -33


# RECORDER_BUFFER_INFO
class RECORDER_BUFFER_INFO(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint64),
        ("pitch", ctypes.c_uint64),
        ("width", ctypes.c_uint64),
        ("height", ctypes.c_uint64),
        ("pixelformat", ctypes.c_uint32),
        ("partCount", ctypes.c_uint32),
        ("timestamp", ctypes.c_uint64),
        ("userdata", ctypes.c_uint64),
        ("utc", ctypes.c_uint64),
        ("chapterIndex", ctypes.c_uint64),
        ("partSize", ctypes.c_uint64),
        ("reserved", ctypes.c_uint64 * 13),
    ]


# RECORDER_PARAMETER
RECORDER_PARAMETER_VERSION = 0
RECORDER_PARAMETER_CONTAINER_SIZE = 1
RECORDER_PARAMETER_RECORD_INDEX = 2
RECORDER_PARAMETER_RECORD_COUNT = 3
RECORDER_PARAMETER_REMAINING_SPACE_ON_DEVICE = 4
RECORDER_PARAMETER_BUFFER_OPTIMAL_ALIGNMENT = 5
RECORDER_PARAMETER_DATABASE_VERSION = 7
RECORDER_PARAMETER_REMAINING_SPACE_IN_CONTAINER = 8
RECORDER_PARAMETER_CHAPTER_COUNT = 10
RECORDER_PARAMETER_CHAPTER_INDEX = 11
RECORDER_PARAMETER_CHAPTER_RECORD_INDEX = 12
RECORDER_PARAMETER_CHAPTER_RECORD_COUNT = 13
RECORDER_PARAMETER_CHAPTER_UTC = 14
RECORDER_PARAMETER_CHAPTER_TIMESTAMP = 15
RECORDER_PARAMETER_CHAPTER_NAME = 16
RECORDER_PARAMETER_CHAPTER_USER_INFO = 17
RECORDER_PARAMETER_BAYER_DECODING_METHOD = 18


# RECORDER_OPEN_MODE
RECORDER_OPEN_MODE_WRITE = 0
RECORDER_OPEN_MODE_READ = 1
RECORDER_OPEN_MODE_APPEND = 2

# RECORDER_CLOSE_MODE
RECORDER_CLOSE_MODE_TRIM = 0
RECORDER_CLOSE_MODE_KEEP = 1
RECORDER_CLOSE_MODE_DONT_TRIM_CHAPTERS = 0x100