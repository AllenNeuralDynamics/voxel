import json
import logging
import traceback
from typing import Any

from ._colors import Color, LevelColor, colorize, strip_colors

STANDARD_LOGRECORD_ATTRS: set[str] = {
    'args',
    'asctime',
    'created',
    'exc_info',
    'exc_text',
    'filename',
    'funcName',
    'levelname',
    'levelno',
    'lineno',
    'module',
    'msecs',
    'message',
    'msg',
    'name',
    'pathname',
    'process',
    'processName',
    'relativeCreated',
    'stack_info',
    'thread',
    'threadName',
    'taskName',
}


def get_extra_data(record: logging.LogRecord) -> dict[str, Any]:
    """Extracts extra data from a LogRecord that is not part of the standard attributes.
    :param record: The LogRecord instance.
    :return: A JSON string of extra data.
    """
    return {key: value for key, value in record.__dict__.items() if key not in STANDARD_LOGRECORD_ATTRS}


class CustomFormatter(logging.Formatter):
    """Lightweight formatter using Colorama."""

    def __init__(self, detailed: bool = False):
        # datefmt without milliseconds for speed
        super().__init__(fmt=self._build_fmt(detailed), datefmt='%Y-%m-%d %H:%M:%S')

    def _build_fmt(self, detailed: bool) -> str:
        # time | level | (name) message [filename:lineno]
        out = f'{colorize("%(asctime)s", color=Color.GREEN)} | %(levelname)-8s | '
        out += f'{colorize("%(name)s >>", color=Color.GRAY)} %(message)s'
        if detailed:
            out += f' {colorize("%(filename)s:%(lineno)d", color=Color.GRAY)}'
        return out

    def format(self, record: logging.LogRecord) -> str:
        # inject color codes
        level = record.levelno
        if level >= logging.CRITICAL:
            color = LevelColor.CRITICAL
        elif level >= logging.ERROR:
            color = LevelColor.ERROR
        elif level >= logging.WARNING:
            color = LevelColor.WARNING
        elif level >= logging.INFO:
            color = LevelColor.INFO
        else:
            color = LevelColor.DEBUG

        original_levelname = record.levelname
        original_msg = record.msg

        record.levelname = f'{color}{record.levelname: <8}{LevelColor.RESET}'

        # Append the extra data to the main message.
        extra_data = get_extra_data(record)
        if extra_data:
            extra_items_str = ', '.join(f'{k}={v}' for k, v in extra_data.items())
            record.msg = f'{record.msg} {colorize(extra_items_str, Color.DIM_CYAN)}'

        output = super().format(record)

        record.levelname = original_levelname
        record.msg = original_msg
        return output


class JSONFormatter(logging.Formatter):
    """Formats log records as a single line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        # Create a dictionary with the log data
        log_object: dict[str, Any] = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'name': record.name,
            'message': strip_colors(record.getMessage()),
            'process': record.process,
            'thread': record.threadName,
        }

        # Add exception info if it exists
        if record.exc_info:
            log_object['exception'] = ''.join(traceback.format_exception(*record.exc_info))

        # Add any extra fields passed to the logger
        extra_data = get_extra_data(record)
        if extra_data:
            log_object['extra'] = extra_data

        return json.dumps(log_object)
