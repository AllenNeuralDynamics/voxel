# Copyright Euresys 2021

"""Exceptions that convert error codes returned by the library functions."""

from .api import *


class RecorderError(Exception):
    def __init__(self, message, status):
        super(RecorderError, self).__init__(message)
        self.status = status

    @staticmethod
    def check(status):
        if status != 0 and status in _RECORDER_ERRORS:
            raise _RECORDER_ERRORS[status]()
        elif status != 0:
            raise RecorderError("Recorder error %d" % status, status)
        return status


class NotInitialized(RecorderError):
    def __init__(self, message="RECORDER_STATUS_NOT_INITIALIZED"):
        super(NotInitialized, self).__init__(message, RECORDER_STATUS_NOT_INITIALIZED)


class UnknownError(RecorderError):
    def __init__(self, message="RECORDER_STATUS_UNKNOWN_ERROR"):
        super(UnknownError, self).__init__(message, RECORDER_STATUS_UNKNOWN_ERROR)


class UnknownParameter(RecorderError):
    def __init__(self, message="RECORDER_STATUS_UNKNOWN_PARAMETER"):
        super(UnknownParameter, self).__init__(message, RECORDER_STATUS_UNKNOWN_PARAMETER)


class InvalidParameterType(RecorderError):
    def __init__(self, message="RECORDER_STATUS_INVALID_PARAMETER_TYPE"):
        super(InvalidParameterType, self).__init__(message, RECORDER_STATUS_INVALID_PARAMETER_TYPE)


class InvalidParameterValue(RecorderError):
    def __init__(self, message="RECORDER_STATUS_INVALID_PARAMETER_VALUE"):
        super(InvalidParameterValue, self).__init__(message, RECORDER_STATUS_INVALID_PARAMETER_VALUE)


class BufferTooSmall(RecorderError):
    def __init__(self, message="RECORDER_STATUS_BUFFER_TOO_SMALL"):
        super(BufferTooSmall, self).__init__(message, RECORDER_STATUS_BUFFER_TOO_SMALL)


class ParameterIsReadOnly(RecorderError):
    def __init__(self, message="RECORDER_STATUS_PARAMETER_IS_READ_ONLY"):
        super(ParameterIsReadOnly, self).__init__(message, RECORDER_STATUS_PARAMETER_IS_READ_ONLY)


class RecorderSystemError(RecorderError):
    def __init__(self, message="RECORDER_STATUS_SYSTEM_ERROR"):
        super(RecorderSystemError, self).__init__(message, RECORDER_STATUS_SYSTEM_ERROR)


class InvalidContainerPath(RecorderError):
    def __init__(self, message="RECORDER_STATUS_INVALID_CONTAINER_PATH"):
        super(InvalidContainerPath, self).__init__(message, RECORDER_STATUS_INVALID_CONTAINER_PATH)


class IOTimeout(RecorderError):
    def __init__(self, message="RECORDER_STATUS_IO_TIMEOUT"):
        super(IOTimeout, self).__init__(message, RECORDER_STATUS_IO_TIMEOUT)


class DataFileFull(RecorderError):
    def __init__(self, message="RECORDER_STATUS_DATA_FILE_FULL"):
        super(DataFileFull, self).__init__(message, RECORDER_STATUS_DATA_FILE_FULL)


class OperationNotAllowed(RecorderError):
    def __init__(self, message="RECORDER_STATUS_OPERATION_NOT_ALLOWED"):
        super(OperationNotAllowed, self).__init__(message, RECORDER_STATUS_OPERATION_NOT_ALLOWED)


class IndexOutOfRange(RecorderError):
    def __init__(self, message="RECORDER_STATUS_INDEX_OUT_OF_RANGE"):
        super(IndexOutOfRange, self).__init__(message, RECORDER_STATUS_INDEX_OUT_OF_RANGE)


class InvalidIndexData(RecorderError):
    def __init__(self, message="RECORDER_STATUS_INVALID_INDEX_DATA"):
        super(InvalidIndexData, self).__init__(message, RECORDER_STATUS_INVALID_INDEX_DATA)


class InvalidIndexSize(RecorderError):
    def __init__(self, message="RECORDER_STATUS_INVALID_INDEX_SIZE"):
        super(InvalidIndexSize, self).__init__(message, RECORDER_STATUS_INVALID_INDEX_SIZE)


class UnsupportedDatabaseVersion(RecorderError):
    def __init__(self, message="RECORDER_STATUS_UNSUPPORTED_DATABASE_VERSION"):
        super(UnsupportedDatabaseVersion, self).__init__(message, RECORDER_STATUS_UNSUPPORTED_DATABASE_VERSION)


class InvalidIndexHeader(RecorderError):
    def __init__(self, message="RECORDER_STATUS_INVALID_INDEX_HEADER"):
        super(InvalidIndexHeader, self).__init__(message, RECORDER_STATUS_INVALID_INDEX_HEADER)


class InvalidLengthWritten(RecorderError):
    def __init__(self, message="RECORDER_STATUS_INVALID_LENGTH_WRITTEN"):
        super(InvalidLengthWritten, self).__init__(message, RECORDER_STATUS_INVALID_LENGTH_WRITTEN)


class InvalidHandle(RecorderError):
    def __init__(self, message="RECORDER_STATUS_INVALID_HANDLE"):
        super(InvalidHandle, self).__init__(message, RECORDER_STATUS_INVALID_HANDLE)


class ResourceInUse(RecorderError):
    def __init__(self, message="RECORDER_STATUS_RESOURCE_IN_USE"):
        super(ResourceInUse, self).__init__(message, RECORDER_STATUS_RESOURCE_IN_USE)


class EndOfData(RecorderError):
    def __init__(self, message="RECORDER_STATUS_END_OF_DATA"):
        super(EndOfData, self).__init__(message, RECORDER_STATUS_END_OF_DATA)


class InvalidArgument(RecorderError):
    def __init__(self, message="RECORDER_STATUS_INVALID_ARGUMENT"):
        super(InvalidArgument, self).__init__(message, RECORDER_STATUS_INVALID_ARGUMENT)


class NoContainer(RecorderError):
    def __init__(self, message="RECORDER_STATUS_NO_CONTAINER"):
        super(NoContainer, self).__init__(message, RECORDER_STATUS_NO_CONTAINER)


class LicenseManagerError(RecorderError):
    def __init__(self, message="RECORDER_STATUS_LICENSE_MANAGER_ERROR"):
        super(LicenseManagerError, self).__init__(message, RECORDER_STATUS_LICENSE_MANAGER_ERROR)


class NoLicense(RecorderError):
    def __init__(self, message="RECORDER_STATUS_NO_LICENSE"):
        super(NoLicense, self).__init__(message, RECORDER_STATUS_NO_LICENSE)


class ImageConversionError(RecorderError):
    def __init__(self, message="RECORDER_STATUS_IMAGE_CONVERSION_ERROR"):
        super(ImageConversionError, self).__init__(message, RECORDER_STATUS_IMAGE_CONVERSION_ERROR)


class UnsupportedImageFormat(RecorderError):
    def __init__(self, message="RECORDER_STATUS_UNSUPPORTED_IMAGE_FORMAT"):
        super(UnsupportedImageFormat, self).__init__(message, RECORDER_STATUS_UNSUPPORTED_IMAGE_FORMAT)


class Aborted(RecorderError):
    def __init__(self, message="RECORDER_STATUS_ABORTED"):
        super(Aborted, self).__init__(message, RECORDER_STATUS_ABORTED)


class InvalidDataSize(RecorderError):
    def __init__(self, message="RECORDER_STATUS_INVALID_DATA_SIZE"):
        super(InvalidDataSize, self).__init__(message, RECORDER_STATUS_INVALID_DATA_SIZE)


class InvalidChapterCharacter(RecorderError):
    def __init__(self, message="RECORDER_STATUS_INVALID_CHAPTER_CHARACTER"):
        super(InvalidChapterCharacter, self).__init__(message, RECORDER_STATUS_INVALID_CHAPTER_CHARACTER)


class ReservedChapterName(RecorderError):
    def __init__(self, message="RECORDER_STATUS_RESERVED_CHAPTER_NAME"):
        super(ReservedChapterName, self).__init__(message, RECORDER_STATUS_RESERVED_CHAPTER_NAME)


class ChapterNameAlreadyUsed(RecorderError):
    def __init__(self, message="RECORDER_STATUS_CHAPTER_NAME_ALREADY_USED"):
        super(ChapterNameAlreadyUsed, self).__init__(message, RECORDER_STATUS_CHAPTER_NAME_ALREADY_USED)


class ChapterNameTooLong(RecorderError):
    def __init__(self, message="RECORDER_STATUS_CHAPTER_NAME_TOO_LONG"):
        super(ChapterNameTooLong, self).__init__(message, RECORDER_STATUS_CHAPTER_NAME_TOO_LONG)


_RECORDER_ERRORS = {
    RECORDER_STATUS_NOT_INITIALIZED: NotInitialized,
    RECORDER_STATUS_UNKNOWN_ERROR: UnknownError,
    RECORDER_STATUS_UNKNOWN_PARAMETER: UnknownParameter,
    RECORDER_STATUS_INVALID_PARAMETER_TYPE: InvalidParameterType,
    RECORDER_STATUS_INVALID_PARAMETER_VALUE: InvalidParameterValue,
    RECORDER_STATUS_BUFFER_TOO_SMALL: BufferTooSmall,
    RECORDER_STATUS_PARAMETER_IS_READ_ONLY: ParameterIsReadOnly,
    RECORDER_STATUS_SYSTEM_ERROR: RecorderSystemError,
    RECORDER_STATUS_INVALID_CONTAINER_PATH: InvalidContainerPath,
    RECORDER_STATUS_IO_TIMEOUT: IOTimeout,
    RECORDER_STATUS_DATA_FILE_FULL: DataFileFull,
    RECORDER_STATUS_OPERATION_NOT_ALLOWED: OperationNotAllowed,
    RECORDER_STATUS_INDEX_OUT_OF_RANGE: IndexOutOfRange,
    RECORDER_STATUS_INVALID_INDEX_DATA: InvalidIndexData,
    RECORDER_STATUS_INVALID_INDEX_SIZE: InvalidIndexSize,
    RECORDER_STATUS_UNSUPPORTED_DATABASE_VERSION: UnsupportedDatabaseVersion,
    RECORDER_STATUS_INVALID_INDEX_HEADER: InvalidIndexHeader,
    RECORDER_STATUS_INVALID_LENGTH_WRITTEN: InvalidLengthWritten,
    RECORDER_STATUS_INVALID_HANDLE: InvalidHandle,
    RECORDER_STATUS_RESOURCE_IN_USE: ResourceInUse,
    RECORDER_STATUS_END_OF_DATA: EndOfData,
    RECORDER_STATUS_NO_CONTAINER: NoContainer,
    RECORDER_STATUS_INVALID_ARGUMENT: InvalidArgument,
    RECORDER_STATUS_LICENSE_MANAGER_ERROR: LicenseManagerError,
    RECORDER_STATUS_NO_LICENSE: NoLicense,
    RECORDER_STATUS_IMAGE_CONVERSION_ERROR: ImageConversionError,
    RECORDER_STATUS_UNSUPPORTED_IMAGE_FORMAT: UnsupportedImageFormat,
    RECORDER_STATUS_ABORTED: Aborted,
    RECORDER_STATUS_INVALID_DATA_SIZE: InvalidDataSize,
    RECORDER_STATUS_INVALID_CHAPTER_CHARACTER: InvalidChapterCharacter,
    RECORDER_STATUS_RESERVED_CHAPTER_NAME: ReservedChapterName,
    RECORDER_STATUS_CHAPTER_NAME_ALREADY_USED: ChapterNameAlreadyUsed,
    RECORDER_STATUS_CHAPTER_NAME_TOO_LONG: ChapterNameTooLong,
}
