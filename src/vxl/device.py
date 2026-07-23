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
    DAQ_ANALOG_OUTPUT = "daq_analog_output"
    DAQ_ANALOG_ON_DEMAND_OUTPUT = "daq_analog_on_demand_output"
    DAQ_DIGITAL_ON_DEMAND_OUTPUT = "daq_digital_on_demand_output"
