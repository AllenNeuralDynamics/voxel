import atexit
import logging

# from abc import ABC, abstractmethod
from enum import Enum, StrEnum
from logging.handlers import QueueHandler, QueueListener
from multiprocessing import Queue
from pathlib import Path
from typing import ClassVar

LOGGING_SUBPROC_SUFFIX = '_sub'
LOGGING_PROJECT_NAME = 'voxel'
NAME_MIN_WIDTH = 8
MSG_MIN_WIDTH = 8
LOG_QUEUE = Queue(-1)


class LogColor(Enum):
    """ANSI color codes for logging."""

    GREEN = '\033[32;20m'
    YELLOW = '\033[33;20m'
    RED = '\033[31;20m'
    BOLD_RED = '\033[31;1m'
    PURPLE = '\033[35;20m'
    BLUE = '\033[34;20m'
    CYAN = '\033[36;20m'
    GREY = '\033[38;20m'
    RESET = '\033[0m'


class LogEmoji(StrEnum):
    """Emoji ansi codes."""

    GREEN_CIRCLE = '\U0001f7e2'
    PURPLE_CIRCLE = '\U0001f7e3'
    BLUE_CIRCLE = '\U0001f535'
    YELLOW_CIRCLE = '\U0001f7e1'
    RED_CIRCLE = '\U0001f534'
    CROSS_MARK = '❌'


class CustomFormatter(logging.Formatter):
    """Enhanced formatter with modular and extendable formatting logic."""

    LEVEL_EMOJIS: ClassVar[dict[int, str]] = {
        logging.DEBUG: LogEmoji.PURPLE_CIRCLE,
        logging.INFO: LogEmoji.BLUE_CIRCLE,
        logging.WARNING: LogEmoji.YELLOW_CIRCLE,
        logging.ERROR: LogEmoji.RED_CIRCLE,
        logging.CRITICAL: LogEmoji.CROSS_MARK,
    }

    LEVEL_COLORS: ClassVar[dict[int, LogColor]] = {
        logging.DEBUG: LogColor.PURPLE,
        logging.INFO: LogColor.BLUE,
        logging.WARNING: LogColor.YELLOW,
        logging.ERROR: LogColor.RED,
        logging.CRITICAL: LogColor.BOLD_RED,
    }

    FIELD_COLORS: ClassVar[dict[str, str]] = {
        'asctime': '%(color_code)s',
        'name': '%(color_code)s',
        'message': '%(color_code)s',
        'filename': LogColor.CYAN.value,
        'processName': LogColor.GREY.value,
    }

    def __init__(
        self,
        detailed: bool = True,
        fancy: bool = False,
        colored: bool = True,
        extra_fields: dict[str, str] | None = None,
    ) -> None:
        """:param detailed: Whether to include detailed fields like process name and file location.
        :param fancy: Whether to include emojis in log level display.
        :param colored: Whether to apply color coding to fields.
        :param extra_fields: Additional fields to include in the format, e.g., thread name.
        """
        self.detailed = detailed
        self.fancy = fancy
        self.colored = colored
        self.extra_fields = extra_fields or {}

        fmt = self._build_format()
        date_fmt = '%Y-%m-%d %H:%M:%S'
        super().__init__(fmt=fmt, datefmt=date_fmt)

    def _build_format(self) -> str:
        """Constructs the format string dynamically."""
        level_str = '%(emoji)s ' if self.fancy else '%(levelname)8s - '

        base_format = level_str

        fields = ['asctime', 'name', 'message']

        for i, field in enumerate(fields):
            separator = ' - ' if i < len(fields) - 1 else ''
            base_format += f'{self.FIELD_COLORS.get(field, "")}%({field})s{LogColor.RESET.value}{separator}'

        if self.detailed:
            base_format += f' - {LogColor.CYAN.value}%(filename)s:%(lineno)d{LogColor.RESET.value}'
            base_format += f' - {LogColor.GREY.value}%(processName)s %(threadName)s{LogColor.RESET.value}'

        return base_format

    def format(self, record: logging.LogRecord) -> str:
        """Override format to inject emojis and color codes."""
        if self.fancy:
            record.emoji = self.LEVEL_EMOJIS.get(record.levelno, '-')
        if self.colored:
            record.color_code = self.LEVEL_COLORS.get(record.levelno, LogColor.GREY).value
        return super().format(record)

    def formatException(self, ei) -> str:  # noqa: N802
        """Format exception messages with red color."""
        formatted = super().formatException(ei)
        if self.colored and formatted:
            return f'{self.LEVEL_COLORS[logging.ERROR].value}{formatted}{LogColor.RESET.value}'
        return formatted


def get_logger(name) -> logging.Logger:
    """Get a logger with the given name, ensuring it's a child of the 'voxel' logger.

    :param name: The name of the logger.
    :return: A Logger instance.
    """
    return logging.getLogger(f'{LOGGING_PROJECT_NAME}.{name}')


def get_component_logger(obj) -> logging.Logger:
    """Get a logger for a specific component.

    :param obj: The component object for which to get the logger.
    :return: A Logger instance.
    """
    if hasattr(obj, 'uid') and isinstance(obj.uid, str) and obj.uid:
        name = obj.uid
    elif hasattr(obj, 'name') and isinstance(obj.name, str) and obj.name:
        name = obj.name
    else:
        name = obj.__class__.__name__
    return get_logger(name)


def get_subprocess_component_logger(obj, queue, level) -> logging.Logger:
    logger = get_component_logger(obj)
    logger.propagate = False
    logger.handlers.clear()
    logger.addHandler(QueueHandler(queue))
    logger.setLevel(level)
    return logger


def _create_handlers(log_file: str | None, detailed: bool = True, fancy: bool = True) -> list[logging.Handler]:
    """Create and configure log handlers."""
    handlers = []

    # Create formatters
    console_formatter = CustomFormatter(detailed=detailed, fancy=fancy, colored=True)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    handlers.append(console_handler)

    # File handler if log file specified
    if log_file:
        file_formatter = CustomFormatter(detailed=detailed, fancy=False, colored=False)
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)

    return handlers


def setup_logging(
    level: str | int = logging.INFO,
    log_file: str | None = None,
    fancy: bool = True,
    detailed: bool = False,
):
    """Set up logging for the application.

    :param level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    :param log_file: Optional path to log file
    :param fancy: Whether to use emoji and color formatting
    :param detailed: Whether to include detailed information in log messages
    """
    root_logger = logging.getLogger()
    lib_logger = logging.getLogger(LOGGING_PROJECT_NAME)

    # Normalize log level
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # Clear existing handlers
    root_logger.handlers.clear()
    lib_logger.handlers.clear()

    # Create handlers
    handlers = _create_handlers(log_file, detailed=detailed, fancy=fancy)

    root_logger.setLevel(level)
    lib_logger.setLevel(level)
    root_logger.addHandler(QueueHandler(LOG_QUEUE))

    # Listener for subprocess logs
    listener = QueueListener(LOG_QUEUE, *handlers, respect_handler_level=True)
    listener.start()

    # Register listener stop on exit
    atexit.register(listener.stop)


def get_log_queue() -> Queue:
    """Get the global log queue for subprocess communication.

    :return: The log queue.
    """
    return LOG_QUEUE


def get_log_level() -> int:
    """Get the current log level of the library logger.

    :return: The log level.
    """
    return logging.getLogger(LOGGING_PROJECT_NAME).getEffectiveLevel()
