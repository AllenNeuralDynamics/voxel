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
    def setup(level: str | int = logging.DEBUG, handlers: list[logging.Handler] | None = None):
        """
        Setup the queue logging with optional handlers.
        :param handlers: List of logging handlers to use.
        """
        if handlers is None:
            handlers = [get_default_console_handler(), get_default_json_handler()]

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
        """
        Redirects the specified loggers to the given log queue.
        :param loggers: List of loggers to redirect.
        :param log_queue: The queue to which logs will be sent.
        """
        for logger in loggers:
            if isinstance(logger, logging.LoggerAdapter):
                logger = logger.logger
            logger.handlers.clear()
            logger.addHandler(QueueHandler(log_queue))
            logger.setLevel(VoxelLogging._log_level)
            logger.propagate = False

    @staticmethod
    def get_logger(name: str | None = None, *, object: object | None = None, extra: dict | None = None) -> "LoggerType":
        """
        Get a logger with the specified name.
        :param name: The name of the logger.
        :param object: An object to derive the logger name from. If provided alongside `name`, `name` will be ignored.
        :param extra: Extra attributes to include in the log records.
        :return: A logger instance.
        """
        if object is not None:
            name = f"{object.__class__.__name__}"
            uid = getattr(object, "uid", None)
            if uid is None:
                uid = getattr(object, "_uid", None)
            if uid:
                name += f"[{uid}]"
            VoxelLogging.get_logger(name, extra=extra)

        logger = logging.getLogger(name) if name else logging.getLogger()
        if extra:
            logger = logging.LoggerAdapter(logger, extra)
        return logger

    @staticmethod
    def get_queue() -> Queue:
        """
        Get the log queue.
        :return: The log queue.
        """
        return VoxelLogging._log_queue

    @staticmethod
    def log_level() -> int:
        """
        Get the current log level.
        :return: The log level.
        """
        return VoxelLogging._log_level
