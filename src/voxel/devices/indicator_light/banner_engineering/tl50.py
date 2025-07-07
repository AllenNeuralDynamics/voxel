import ctypes
import logging
import os
import platform
from ctypes import c_int, c_ubyte, c_ushort
from enum import IntEnum
from voxel.devices.indicator_light.base import BaseIndicatorLight


class Color(IntEnum):
    GREEN = 0
    RED = 1
    ORANGE = 2
    AMBER = 3
    YELLOW = 4
    LIME_GREEN = 5
    SPRING_GREEN = 6
    CYAN = 7
    SKY_BLUE = 8
    BLUE = 9
    VIOLET = 10
    MAGENTA = 11
    ROSE = 12
    WHITE = 13
    CUSTOM_COLOR_1 = 14
    CUSTOM_COLOR_2 = 15


class SegmentAnimation(IntEnum):
    SEGMENT_OFF = 0
    SEGMENT_STEADY = 1
    SEGMENT_FLASH = 2
    SEGMENT_TWO_COLOR_FLASH = 3
    SEGMENT_HALF_HALF = 4
    SEGMENT_HALF_HALF_ROTATE = 5
    SEGMENT_CHASE = 6
    SEGMENT_INTENSITY_SWEEP = 7


class Intensity(IntEnum):
    INTENSITY_HIGH = 0
    INTENSITY_LOW = 1
    INTENSITY_MEDIUM = 2
    INTENSITY_OFF = 3
    INTENSITY_CUSTOM = 4


class Speed(IntEnum):
    SPEED_STANDARD = 0
    SPEED_FAST = 1
    SPEED_SLOW = 2
    SPEED_CUSTOM = 3


class FlashPattern(IntEnum):
    FLASH_NORMAL = 0
    FLASH_STROBE = 1
    FLASH_THREE_PULSE = 2
    FLASH_SOS = 3
    FLASH_RANDOM = 4


class RotationalDirection(IntEnum):
    DIRECTION_COUNTERCLOCKWISE = 0
    DIRECTION_CLOCKWISE = 1


class Audible(IntEnum):
    AUDIBLE_OFF = 0
    AUDIBLE_STEADY = 1
    AUDIBLE_PULSED = 2
    AUDIBLE_SOS = 3


class CommReturnValue(IntEnum):
    SUCCESS = 0
    FAILED_PORT_NOT_FOUND = -1
    FAILED_PORT_OPEN = -2
    FAILED_WRITE = -3
    FAILED_READ = -4
    FAILED_CHECKSUM = -5
    FAIL_WITH_NACK = -6
    FAILED_NO_INIT = -7


COLORS = {
    "green": Color.GREEN,
    "red": Color.RED,
    "orange": Color.ORANGE,
    "amber": Color.AMBER,
    "yellow": Color.YELLOW,
    "lime green": Color.LIME_GREEN,
    "spring green": Color.SPRING_GREEN,
    "cyan": Color.CYAN,
    "sky blue": Color.SKY_BLUE,
    "blue": Color.BLUE,
    "violet": Color.VIOLET,
    "magenta": Color.MAGENTA,
    "rose": Color.ROSE,
    "white": Color.WHITE,
    "custom1": Color.CUSTOM_COLOR_1,
    "custom2": Color.CUSTOM_COLOR_2,
}

ANIMATIONS = {
    "off": SegmentAnimation.SEGMENT_OFF,
    "steady": SegmentAnimation.SEGMENT_STEADY,
    "flash": SegmentAnimation.SEGMENT_FLASH,
    "two color flash": SegmentAnimation.SEGMENT_TWO_COLOR_FLASH,
    "half half": SegmentAnimation.SEGMENT_HALF_HALF,
    "half half rotate": SegmentAnimation.SEGMENT_HALF_HALF_ROTATE,
    "chase": SegmentAnimation.SEGMENT_CHASE,
    "intensity sweep": SegmentAnimation.SEGMENT_INTENSITY_SWEEP,
}

INTENSITIES = {
    "high": Intensity.INTENSITY_HIGH,
    "low": Intensity.INTENSITY_LOW,
    "medium": Intensity.INTENSITY_MEDIUM,
    "off": Intensity.INTENSITY_OFF,
    "custom": Intensity.INTENSITY_CUSTOM,
}

FLASH_PATTERNS = {
    "normal": FlashPattern.FLASH_NORMAL,
    "strobe": FlashPattern.FLASH_STROBE,
    "three pulse": FlashPattern.FLASH_THREE_PULSE,
    "sos": FlashPattern.FLASH_SOS,
    "random": FlashPattern.FLASH_RANDOM,
}

DIRECTIONS = {
    "counter clockwise": RotationalDirection.DIRECTION_COUNTERCLOCKWISE,
    "clockwise": RotationalDirection.DIRECTION_CLOCKWISE,
}

SPEEDS = {
    "standard": Speed.SPEED_STANDARD,
    "fast": Speed.SPEED_FAST,
    "slow": Speed.SPEED_SLOW,
    "custom": Speed.SPEED_CUSTOM,
}

AUDIBLES = {
    "off": Audible.AUDIBLE_OFF,
    "steady": Audible.AUDIBLE_STEADY,
    "pulsed": Audible.AUDIBLE_PULSED,
    "sos": Audible.AUDIBLE_SOS,
}


class TL50IndicatorLight(BaseIndicatorLight):
    def __init__(self, com_port: str) -> None:
        """
        Initialize the TL50 indicator light device and set up DLL bindings.

        :param com_port: The COM port number to connect to.
        :type com_port: int
        """
        super().__init__()
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.id = str(com_port)

        # load DLL
        DIR = os.path.dirname(os.path.realpath(__file__))

        # check if windows or linux
        if platform.system() == "Linux":
            self.log.warning('not yet supported on linux')
        else:
            # Assuming Windows, load the DLL accordingly
            if platform.architecture()[0] == "32bit":
                self.log.info("loading 32-bit DLL")
                if not os.path.exists(f"{DIR}\\Tl50UsbLibraryWin32.dll"):
                    raise FileNotFoundError("Tl50UsbLibrary.dll not found in the expected directory.")
                self.tl50 = ctypes.CDLL(f"{DIR}\\win32\\Tl50UsbLibraryx64.dll")
            else:
                self.log.info("loading 64-bit DLL")
                if not os.path.exists(f"{DIR}\\win64\\Tl50UsbLibraryx64.dll"):
                    raise FileNotFoundError("Tl50UsbLibraryx64.dll not found in the expected directory.")
                self.tl50 = ctypes.CDLL(f"{DIR}\\win64\\Tl50UsbLibraryx64.dll")

        # initialize the device with the specified COM port
        self.log.info(f"initializing device on port {com_port}")
        self.tl50.InitByPort(int("".join(filter(lambda char: not char.isalpha(), com_port))))

        # initialize cached settings
        self._settings = dict()

        # set up function argument and return types
        self.tl50.InitByPort.argtypes = [c_int]
        self.tl50.InitByPort.restype = c_int
        self.tl50.Init.restype = c_int
        self.tl50.SetSegmentSolid.argtypes = [c_int, c_int]
        self.tl50.SetSegmentSolid.restype = c_int
        self.tl50.SetSegmentOff.argtypes = [c_int]
        self.tl50.SetSegmentOff.restype = c_int
        self.tl50.Deinit.restype = c_int
        self.tl50.GetDllVersion.restype = c_ushort
        self.tl50.SetSegment.argtypes = [
            c_int,  # segment
            c_int,
            c_int,
            c_int,  # animation, color1, intensity1
            c_int,
            c_int,  # speed, flashPattern
            c_int,
            c_int,  # color2, intensity2
            c_int,  # direction
        ]
        self.tl50.SetSegment.restype = c_int
        self.tl50.SetAudible.argtypes = [c_int]
        self.tl50.SetAudible.restype = c_int
        self.tl50.SetCustomColor1.argtypes = [c_ubyte, c_ubyte, c_ubyte]
        self.tl50.SetCustomColor1.restype = c_int
        self.tl50.SetCustomColor2.argtypes = [c_ubyte, c_ubyte, c_ubyte]
        self.tl50.SetCustomColor2.restype = c_int
        self.tl50.SetCustomIntensity.argtypes = [c_int]
        self.tl50.SetCustomIntensity.restype = c_int
        self.tl50.SetCustomSpeed.argtypes = [c_int]
        self.tl50.SetCustomSpeed.restype = c_int
        self.tl50.SetSegmentAdvanced.argtypes = [c_int, ctypes.POINTER(c_ubyte)]
        self.tl50.SetSegmentAdvanced.restype = c_int

    def _set_segment_solid(self, segment: int, color: Color) -> CommReturnValue:
        """
        Set a segment to a solid color.

        :param segment: The segment index to set.
        :type segment: int
        :param color: The color to set the segment to.
        :type color: Color
        :return: Communication return value indicating success or failure.
        :rtype: CommReturnValue
        """
        return CommReturnValue(self.tl50.SetSegmentSolid(segment, color))

    def _set_segment_off(self, segment: int) -> CommReturnValue:
        """
        Turn off a segment.

        :param segment: The segment index to turn off.
        :type segment: int
        :return: Communication return value indicating success or failure.
        :rtype: CommReturnValue
        """
        return CommReturnValue(self.tl50.SetSegmentOff(segment))

    def _deinit(self) -> CommReturnValue:
        """
        Deinitialize the TL50 device.

        :return: Communication return value indicating success or failure.
        :rtype: CommReturnValue
        """
        return CommReturnValue(self.tl50.Deinit())

    def _get_dll_version(self) -> tuple[int, int]:
        """
        Get the DLL version as a (major, minor) tuple.

        :return: Tuple of (major, minor) version numbers.
        :rtype: tuple[int, int]
        """
        version = self.tl50.GetDllVersion()
        major = (version >> 8) & 0xFF
        minor = version & 0xFF
        return (major, minor)

    def _set_segment(
        self,
        segment: int,
        animation: int,
        color1: int,
        intensity1: int,
        speed: int,
        flash_pattern: int,
        color2: int,
        intensity2: int,
        direction: int,
    ) -> CommReturnValue:
        """
        Set advanced segment parameters.

        :param segment: Segment index to set.
        :type segment: int
        :param animation: Animation type.
        :type animation: int
        :param color1: Primary color.
        :type color1: int
        :param intensity1: Primary intensity.
        :type intensity1: int
        :param speed: Animation speed.
        :type speed: int
        :param flash_pattern: Flash pattern type.
        :type flash_pattern: int
        :param color2: Secondary color.
        :type color2: int
        :param intensity2: Secondary intensity.
        :type intensity2: int
        :param direction: Animation direction.
        :type direction: int
        :return: Communication return value indicating success or failure.
        :rtype: CommReturnValue
        """
        return CommReturnValue(
            self.tl50.SetSegment(
                segment,
                animation,
                color1,
                intensity1,
                speed,
                flash_pattern,
                color2,
                intensity2,
                direction,
            )
        )

    def _set_audible(self, audible: Audible) -> CommReturnValue:
        """
        Set the audible mode of the device.

        :param audible: Audible mode to set.
        :type audible: Audible
        :return: Communication return value indicating success or failure.
        :rtype: CommReturnValue
        """
        return CommReturnValue(self.tl50.SetAudible(audible))

    def _set_custom_color1(self, r: int, g: int, b: int) -> CommReturnValue:
        """
        Set the first custom color.

        :param r: Red value (0-255).
        :type r: int
        :param g: Green value (0-255).
        :type g: int
        :param b: Blue value (0-255).
        :type b: int
        :return: Communication return value indicating success or failure.
        :rtype: CommReturnValue
        """
        return CommReturnValue(self.tl50.SetCustomColor1(r, g, b))

    def _set_custom_color2(self, r: int, g: int, b: int) -> CommReturnValue:
        """
        Set the second custom color.

        :param r: Red value (0-255).
        :type r: int
        :param g: Green value (0-255).
        :type g: int
        :param b: Blue value (0-255).
        :type b: int
        :return: Communication return value indicating success or failure.
        :rtype: CommReturnValue
        """
        return CommReturnValue(self.tl50.SetCustomColor2(r, g, b))

    def _set_custom_intensity(self, percent: int) -> CommReturnValue:
        """
        Set the custom intensity percentage.

        :param percent: Intensity percentage (0-100).
        :type percent: int
        :return: Communication return value indicating success or failure.
        :rtype: CommReturnValue
        """
        return CommReturnValue(self.tl50.SetCustomIntensity(percent))

    def _set_custom_speed(self, dhz: int) -> CommReturnValue:
        """
        Set the custom speed in decihertz.

        :param dhz: Speed in decihertz.
        :type dhz: int
        :return: Communication return value indicating success or failure.
        :rtype: CommReturnValue
        """
        return CommReturnValue(self.tl50.SetCustomSpeed(dhz))

    def _set_segment_advanced(self, segment: int, data: bytes) -> CommReturnValue:
        """
        Set advanced segment data using a 3-byte buffer.

        :param segment: Segment index to set.
        :type segment: int
        :param data: 3-byte data buffer.
        :type data: bytes
        :raises ValueError: If data is not 3 bytes long.
        :return: Communication return value indicating success or failure.
        :rtype: CommReturnValue
        """
        if len(data) != 3:
            raise ValueError("data must be 3 bytes long")
        buffer = (c_ubyte * 3)(*data)
        return CommReturnValue(self.tl50.SetSegmentAdvanced(segment, buffer))

    @property
    def settings(self) -> dict:
        """
        Get the current active settings for the indicator light.

        :return: Dictionary of current active settings.
        :rtype: dict
        """
        return self._settings

    @settings.setter
    def settings(self, settings: dict) -> None:
        """
        Set the settings for the indicator light.

        :param settings: Dictionary of settings to apply.
        :type settings: dict
        :raises ValueError: If any setting value is invalid.
        """
        color1 = settings["color1"]
        intensity1 = settings["intensity1"]
        animation = settings["animation"]
        speed = settings["speed"]
        flash_pattern = settings["flash_pattern"]
        color2 = settings["color2"]
        intensity2 = settings["intensity2"]
        direction = settings["direction"]

        if color1 not in COLORS:
            raise ValueError(f"Invalid color1: {color1} must be one of {list(COLORS.keys())}")
        if intensity1 not in INTENSITIES:
            raise ValueError(f"Invalid intensity1: {intensity1} must be one of {list(INTENSITIES.keys())}")
        if animation not in ANIMATIONS:
            raise ValueError(f"Invalid animation: {animation} must be one of {list(ANIMATIONS.keys())}")
        if speed not in SPEEDS:
            raise ValueError(f"Invalid speed: {speed} must be one of {list(SPEEDS.keys())}")
        if flash_pattern not in FLASH_PATTERNS:
            raise ValueError(f"Invalid flash_pattern: {flash_pattern} must be one of {list(FLASH_PATTERNS.keys())}")
        if color2 not in COLORS:
            raise ValueError(f"Invalid color2: {color2} must be one of {list(COLORS.keys())}")
        if intensity2 not in INTENSITIES:
            raise ValueError(f"Invalid intensity2: {intensity2} must be one of {list(INTENSITIES.keys())}")
        if direction not in DIRECTIONS:
            raise ValueError(f"Invalid direction: {direction} must be one of {list(DIRECTIONS.keys())}")

        self._settings["color1"] = color1
        self._settings["intensity1"] = intensity1
        self._settings["animation"] = animation
        self._settings["speed"] = speed
        self._settings["flash_pattern"] = flash_pattern
        self._settings["color2"] = color2
        self._settings["intensity2"] = intensity2
        self._settings["direction"] = direction

        self.log.info("indicator light settings stored")

    def enable(self) -> None:
        """
        Enable the TL50 device by initializing it.

        :return: None
        """
        self._set_segment(
            segment=0,  # Assuming segment 0 for simplicity, adjust as needed
            animation=ANIMATIONS[self._settings["animation"]],
            color1=COLORS[self._settings["color1"]],
            intensity1=INTENSITIES[self._settings["intensity1"]],
            speed=SPEEDS[self._settings["speed"]],
            flash_pattern=FLASH_PATTERNS[self._settings["flash_pattern"]],
            color2=COLORS[self._settings["color2"]],
            intensity2=INTENSITIES[self._settings["intensity2"]],
            direction=DIRECTIONS[self._settings["direction"]],
        )
        print("enabled")
        self.log.info("device enabled.")

    def disable(self) -> None:
        """
        Disable the TL50 device by turning off the segment.

        :return: None
        """
        self._set_segment_off(segment=0)

    def close(self) -> None:
        """
        Close the TL50 device and deinitialize resources.

        :return: None
        """
        self.disable()
        self._deinit()
        self.log.info("device closed.")
