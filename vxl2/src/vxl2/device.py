from enum import StrEnum


class DeviceType(StrEnum):
    DAQ = "daq"
    CAMERA = "camera"
    LASER = "laser"
    AOTF = "aotf"
    CONTINUOUS_AXIS = "continuous_axis"
    LINEAR_AXIS = "linear_axis"
    ROTATION_AXIS = "rotation_axis"
    DISCRETE_AXIS = "discrete_axis"
