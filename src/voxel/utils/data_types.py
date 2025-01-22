from enum import IntEnum, StrEnum


class StrEnumValue(StrEnum):
    @property
    def options(self) -> list[str]:
        return [member.value for member in self.__class__]


class IntEnumValue(IntEnum):
    @property
    def options(self) -> list[int]:
        return [member.value for member in self.__class__]
