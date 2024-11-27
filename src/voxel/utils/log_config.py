from abc import ABC, abstractmethod
import atexit
from enum import Enum
import logging
from logging.handlers import QueueHandler, QueueListener
from multiprocessing import Process, Queue
from pathlib import Path

LOGGING_SUBPROC_SUFFIX = "_sub"
LOGGING_PROJECT_NAME = "voxel"
NAME_MIN_WIDTH = 8
MSG_MIN_WIDTH = 8
LOG_QUEUE = Queue(-1)


class LogColor(Enum):
    """ANSI color codes for logging"""

    GREY = "\033[38;20m"
    BLUE = "\033[34;20m"
    YELLOW = "\033[33;20m"
    RED = "\033[31;20m"
    BOLD_RED = "\033[31;1m"
    GREEN = "\033[32;20m"
    CYAN = "\033[36;20m"
    PURPLE = "\033[35;20m"
    RESET = "\033[0m"


class CustomFormatter(logging.Formatter):
    """Base formatter with common functionality"""

    LEVEL_EMOJIS: dict[int, str] = {
        logging.DEBUG: "\U0001f7e3",
        logging.INFO: "\U0001f535",
        logging.WARNING: "\U0001f7e1",
        logging.ERROR: "\U0001f534",
        logging.CRITICAL: "❌",
    }

    LEVEL_COLORS: dict[int, LogColor] = {
        logging.DEBUG: LogColor.PURPLE,
        logging.INFO: LogColor.BLUE,
        logging.WARNING: LogColor.YELLOW,
        logging.ERROR: LogColor.RED,
        logging.CRITICAL: LogColor.BOLD_RED,
    }

    def __init__(self, detailed: bool = True, fancy: bool = False, colored: bool = True) -> None:
        self.detailed = detailed
        self.fancy = fancy
        self.colored = colored

        date_fmt = "%Y-%m-%d %H:%M:%S"
        level_str = "%(emoji)s " if self.fancy else "%(levelname)8s - "

        time_fmt = "%(asctime)s"
        time_fmt = f"%(color_code)s{time_fmt}{LogColor.RESET.value}" if self.colored else time_fmt

        name_fmt = f"%(name)-{NAME_MIN_WIDTH}s"
        name_fmt = f"%(color_code)s{name_fmt}{LogColor.RESET.value}" if self.colored else name_fmt

        msg_fmt = f"%(message)-{MSG_MIN_WIDTH}s"
        msg_fmt = f"%(color_code)s{msg_fmt}{LogColor.RESET.value}" if self.colored else msg_fmt

        default_fmt = f"{level_str}{time_fmt} - {name_fmt} - {msg_fmt}"

        # default_fmt = f"%(asctime)s - {level_str} - %(name)-{NAME_MIN_WIDTH}s - %(message)-{MSG_MIN_WIDTH}s"
        # default_fmt = f"%(color_code)s{default_fmt}{LogColor.RESET.value}" if self.colored else default_fmt

        file_name = "%(filename)s:%(lineno)d"
        file_name = f"{LogColor.GREY.value}{file_name}{LogColor.RESET.value}" if self.colored else file_name

        process_name = "%(processName)s"
        process_name = f"{LogColor.GREY.value}{process_name}{LogColor.RESET.value}" if self.colored else process_name

        detailed_fmt = default_fmt + f" - {process_name} - {file_name}"
        super().__init__(fmt=detailed_fmt if detailed else default_fmt, datefmt=date_fmt)

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with emojis"""
        if self.fancy:
            record.emoji = self.LEVEL_EMOJIS.get(record.levelno, "-")
        if self.colored:
            record.color_code = self.LEVEL_COLORS.get(record.levelno, LogColor.GREY).value
        return super().format(record)

    def formatException(self, ei) -> str:
        """Format exception with red color"""
        if ei:
            formatted = super().formatException(ei)
            if self.fancy:
                return f"{self.LEVEL_COLORS[logging.ERROR].value}{formatted}{LogColor.RESET.value}"
            return formatted
        return ""


# class FileFormatter():
#     """Formatter for file logs"""

#     def __init__(self, detailed: bool = True, jsonify: bool = True) -> None:


def get_logger(name) -> logging.Logger:
    """
    Get a logger with the given name, ensuring it's a child of the 'voxel' logger.

    :param name: The name of the logger.
    :return: A Logger instance.
    """
    return logging.getLogger(f"{LOGGING_PROJECT_NAME}.{name}")


def get_component_logger(obj) -> logging.Logger:
    """
    Get a logger for a specific component.

    :param obj: The component object for which to get the logger.
    :return: A Logger instance.
    """
    if hasattr(obj, "name") and isinstance(obj.name, str) and obj.name != "":
        return get_logger(f"{obj.__class__.__name__}[{obj.name}]")
    return get_logger(obj.__class__.__name__)


def _create_handlers(log_file: str | None, detailed: bool = True, fancy: bool = True) -> list[logging.Handler]:
    """Create and configure log handlers"""
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
    level: str | int = "INFO",
    log_file: str | None = None,
    fancy: bool = True,
    detailed: bool = False,
):
    """
    Set up logging for the application.

    :param level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    :param log_file: Optional path to log file
    :param fancy: Whether to use emoji and color formatting
    :param detailed: Whether to include detailed information in log messages
    """
    root_logger = logging.getLogger()
    lib_logger = logging.getLogger(LOGGING_PROJECT_NAME)
    LOG_LEVEL_MAP = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    level = LOG_LEVEL_MAP.get(str(level).upper(), logging.INFO)
    lib_logger.setLevel(level)
    root_logger.setLevel(level)

    lib_logger.handlers.clear()
    root_logger.handlers.clear()

    handlers = _create_handlers(log_file, detailed=detailed, fancy=fancy)
    queue_handler = QueueHandler(LOG_QUEUE)
    root_logger.addHandler(queue_handler)

    listener = QueueListener(LOG_QUEUE, *handlers, respect_handler_level=True)
    listener.start()

    atexit.register(listener.stop)


class LoggingSubprocess(Process, ABC):
    """
    Abstract base process class that handles logging setup for child processes.
    """

    def __init__(self, name: str, queue: Queue = LOG_QUEUE) -> None:
        super().__init__()
        self.name = name
        self._log_queue = queue
        self.log = get_component_logger(self)
        self._log_level = self.log.getEffectiveLevel()
        self._initialized = False

    def _setup_logging(self):
        """Set up logging for the subprocess"""
        if not self._initialized:
            for logger in [
                logging.getLogger(),
                logging.getLogger(LOGGING_PROJECT_NAME),
            ]:
                logger.handlers.clear()
                logger.setLevel(self._log_level)

            self.log = get_component_logger(self)

            queue_handler = QueueHandler(self._log_queue)
            self.log.addHandler(queue_handler)
            self.log.setLevel(self._log_level)

            self.name += LOGGING_SUBPROC_SUFFIX

            self._initialized = True

    def run(self) -> None:
        """
        Main process execution method. Sets up logging and calls _run().
        Child classes should override _run() instead of run().
        """
        try:
            self._setup_logging()
            self._run()
        except Exception as e:
            self.log.error(f"Process error: {str(e)}")
            raise e

    @abstractmethod
    def _run(self) -> None:
        """
        Main process execution logic. Must be implemented by child classes.
        """
        pass


# Example usage
class Counter(LoggingSubprocess):
    def __init__(self, name: str, count: int):
        super().__init__(name)
        self.count = count

    def _run(self):
        import time

        self.log.info(f"Counter process started with count={self.count}")  # Added startup message
        for i in range(self.count):
            self.log.info(f"Count: {i}")
            self.log.debug(f"Debug message: {i}")
            self.log.warning(f"Warning message: {i}")
            self.log.error(f"Error message: {i}")
            time.sleep(0.5)  # Reduced sleep time for faster testing
        self.log.info("Counter process completed")  # Added completion message


# @with_logging(level="ERROR")
def main() -> None:
    proc = Counter("counter", 5)
    proc.log.critical("Main process started ....................................")
    proc.log.info("Starting counter process")
    proc.start()
    proc.join()
    proc.log.warning("Counter process joined")
    proc.log.error("Counter process exited")


if __name__ == "__main__":
    setup_logging(level="DEBUG")
    main()
