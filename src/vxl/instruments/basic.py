"""An instrument with only what every instrument has: a ``rig.yaml`` can name it and run with no code of its own."""

from typing import Unpack

from rigup.interface import update

from vxl.station.instrument.base import Instrument
from vxl.station.instrument.config import InstrumentConfig
from vxl.station.instrument.state import InstrumentState, ProfileFields, ProfileId


class BasicInstrument(Instrument[InstrumentConfig, InstrumentState]):
    """An instrument with only what every instrument has. A kind that adds its own profile fields subclasses
    :class:`Instrument` instead."""

    @update("profiles", key="profile_id")
    async def update_profile(self, profile_id: ProfileId, **fields: Unpack[ProfileFields]) -> None:
        """Change the label or notes of a profile, as 1 edit."""
        await self._update_profile(profile_id, fields, ProfileFields)


__all__ = ["BasicInstrument"]
