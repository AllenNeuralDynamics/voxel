from typing import Any

from vxl.core.instrument.config import InstrumentConfig

_IDENTITY: dict[str, Any] = {
    "id": "5x8k2m9q4r7t1v3w6y0z2b4c8d",
    "name": "bench",
    "target": "tests.Bench",
}


def bench(data: dict[str, Any]) -> InstrumentConfig:
    """An instrument with a bench and no more. ``data`` gives the bench keys of the file."""
    return InstrumentConfig.model_validate(_IDENTITY | data)
