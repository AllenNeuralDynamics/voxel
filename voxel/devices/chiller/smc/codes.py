from enum import Enum

class SMCCommand(Enum):
    SET_TEMPERATURE_NO_FRAM = 0x31
    READ_INTERNAL_SENSOR = 0x32
    READ_EXTERNAL_SENSOR = 0x33
    READ_ALARM_STATUS = 0x34
    SET_OFFSET_NO_FRAM = 0x36
    SET_TEMPERATURE_FRAM = 0x37
    SET_OFFSET_FRAM = 0x38

class SMCControl(Enum):
    ENQ = 0x05
    STX = 0x02
    ETX = 0x03
    ACK = 0x06
    CR = 0x0D
    SOH = 0x01