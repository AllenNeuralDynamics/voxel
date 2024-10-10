# -*- coding: utf-8 -*-
"""
Formatted StreamHandler for logging to sys.stderr

Copyright @ Excelitas PCO GmbH 2005-2023

Set your logging handler to pco.stream_handler
"""

import sys
import logging
import logging.handlers


class CustomFormatterStream(logging.Formatter):

    red = "\033[31m"
    yellow = "\033[33m"
    reset = "\033[0m"

    FORMATS = {
        logging.DEBUG: "[%(asctime)s] %(message)s",
        logging.INFO: "[%(asctime)s] %(message)s",
        logging.WARNING: "[%(asctime)s] "
        + yellow
        + "%(message)s"
        + reset
        + " (%(filename)s:%(lineno)d)",
        logging.ERROR: "[%(asctime)s] "
        + red
        + "%(message)s"
        + reset
        + " (%(filename)s:%(lineno)d)",
        logging.CRITICAL: "[%(asctime)s] "
        + red
        + "%(message)s"
        + reset
        + " (%(filename)s:%(lineno)d)",
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


stream_handler = logging.StreamHandler(stream=sys.stderr)
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(CustomFormatterStream())
