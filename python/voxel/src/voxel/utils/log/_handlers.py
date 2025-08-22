import logging

from ._formatter import CustomFormatter, JSONFormatter


def get_default_console_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setFormatter(CustomFormatter(detailed=True))
    return handler


def get_default_json_handler() -> logging.FileHandler:
    handler = logging.FileHandler('app.log.jsonl', mode='a')
    handler.setFormatter(JSONFormatter())
    return handler
