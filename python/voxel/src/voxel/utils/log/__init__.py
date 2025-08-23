import atexit
import logging
from logging.handlers import QueueHandler, QueueListener
from multiprocessing import Queue

from ._handlers import get_default_console_handler, get_default_json_handler

type LoggerType = logging.Logger | logging.LoggerAdapter


class VoxelLogging:
    """Voxel logging utility that uses a queue to handle log messages."""

    _log_level = logging.DEBUG
    _log_queue = Queue(-1)

    @staticmethod
    def setup(
        level: str | int = logging.DEBUG,
        handlers: list[logging.Handler] | None = None,
        *,
        default_console: bool = True,
        default_json: bool = False,
    ):
        """Setup the queue logging with optional handlers.
        :param level: The logging level to set.
        :param handlers: List of logging handlers to use.
        :param default_console: Whether to include the default console handler.
        :param default_json: Whether to include the default JSON handler.
        """
        if handlers is None:
            default_console = True
        handlers = []
        if default_console:
            handlers.append(get_default_console_handler())
        if default_json:
            handlers.append(get_default_json_handler())

        log_queue = VoxelLogging.get_queue()

        root = logging.getLogger()
        root.setLevel(level)
        root.handlers.clear()
        root.addHandler(QueueHandler(log_queue))

        listener = QueueListener(log_queue, *handlers, respect_handler_level=True)
        listener.start()
        atexit.register(listener.stop)

        VoxelLogging._log_level = logging.getLogger().getEffectiveLevel()

    @staticmethod
    def redirect(loggers: list[LoggerType], log_queue: Queue):
        """Redirects the specified loggers to the given log queue.
        :param loggers: List of loggers to redirect.
        :param log_queue: The queue to which logs will be sent.
        """
        for logger in loggers:
            actual_logger = logger.logger if isinstance(logger, logging.LoggerAdapter) else logger
            actual_logger.handlers.clear()
            actual_logger.addHandler(QueueHandler(log_queue))
            actual_logger.setLevel(VoxelLogging._log_level)
            actual_logger.propagate = False

    @staticmethod
    def get_logger(name: str | None = None, *, obj: object | None = None, extra: dict | None = None) -> 'LoggerType':
        """Get a logger with the specified name.
        :param name: The name of the logger.
        :param object: An object to derive the logger name from. If provided alongside `name`, `name` will be ignored.
        :param extra: Extra attributes to include in the log records.
        :return: A logger instance.
        """
        if obj is not None:
            name = f'{obj.__class__.__name__}'
            uid = getattr(obj, 'uid', None)
            if uid is None:
                uid = getattr(obj, '_uid', None)
            if uid:
                name += f'[{uid}]'

        logger = logging.getLogger(name) if name else logging.getLogger()
        if extra:
            logger = logging.LoggerAdapter(logger, extra)
        return logger

    @staticmethod
    def get_queue() -> Queue:
        """Get the log queue.
        :return: The log queue.
        """
        return VoxelLogging._log_queue

    @staticmethod
    def log_level() -> int:
        """Get the current log level.
        :return: The log level.
        """
        return VoxelLogging._log_level
