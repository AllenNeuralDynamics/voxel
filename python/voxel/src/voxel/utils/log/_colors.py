# voxel_logging/_colors.py
import re

from colorama import Back, Fore, Style, init

# Initialize Colorama (no-op on Unix, enables Win32 support on Windows)
init(autoreset=True)


class Color:
    GREEN = Fore.GREEN
    GRAY = Fore.LIGHTBLACK_EX
    DIM_CYAN = Style.DIM + Fore.CYAN


class LevelColor:
    """Color constants matching Loguru's default theme."""

    DEBUG = Fore.CYAN
    INFO = Style.BRIGHT + Fore.BLUE
    WARNING = Fore.YELLOW
    ERROR = Fore.RED
    CRITICAL = Back.RED + Fore.WHITE + Style.BRIGHT
    RESET = Style.RESET_ALL


def colorize(text: str, color: str) -> str:
    """Colorizes the given text using the specified color.
    :param text: The text to colorize.
    :param color: The color to apply.
    :return: Colorized text.
    """
    return f'{color}{text}{Style.RESET_ALL}'


def strip_colors(text: str) -> str:
    # use a simple regex to remove ANSI escape sequences
    ansi_escape_pattern = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape_pattern.sub('', text)
