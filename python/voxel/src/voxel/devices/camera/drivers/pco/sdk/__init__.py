# -*- coding: utf-8 -*-
"""
This module provides a high level Software Development Kit (SDK) for working with PCO cameras.
It contains everything needed for camera setup, image acquistion, readout and color conversion.

Copyright @ Excelitas PCO GmbH 2005-2023

Submodules are:
- camera
- sdk
- recorder
- convert
- flim
- logging
"""

from .camera import Camera
from .flim import Flim

from .logging import stream_handler
