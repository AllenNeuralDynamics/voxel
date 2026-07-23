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
    DAQ_AO = "daq_ao"
    DAQ_ON_DEMAND_AO = "daq_on_demand_ao"
    DAQ_ON_DEMAND_DO = "daq_on_demand_do"
