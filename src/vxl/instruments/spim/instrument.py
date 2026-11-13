from vxl.core.instrument.base import BaseInstrument

from .config import SPIMConfig, SPIMState


class Instrument(BaseInstrument[SPIMConfig, SPIMState]): ...
