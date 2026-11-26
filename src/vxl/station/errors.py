"""The failures that a person can act on. A built-in error, such as a ``TypeError``, means a bug in the code that
called."""

from collections.abc import Iterable
from typing import ClassVar

from vxlib.issues import Problem, Problems


class VoxelError(Exception):
    """A failure that a person can act on: the request or the setup is wrong, not the program."""


class StartupError(VoxelError):
    """An instrument did not start. ``problems`` lists every problem, each at its place."""

    def __init__(self, problems: Iterable[Problem]) -> None:
        self.problems = Problems(problems)
        super().__init__(str(self.problems))


class RejectedError(VoxelError):
    """The request is not valid, and nothing changed. ``problems`` lists why, when there are places to show."""

    def __init__(self, message: str, problems: Iterable[Problem] = ()) -> None:
        self.problems = Problems(problems)
        super().__init__(message)


class NotFoundError(RejectedError):
    """The request names something that does not exist, such as a task or a profile, and nothing changed."""


class StaleError(RejectedError):
    """The request was made against a version that has changed since, and nothing changed. ``problem_type`` tells it
    apart from other refusals in an HTTP answer."""

    problem_type: ClassVar[str] = "tag:voxel,2026:stale"


class BusyError(VoxelError):
    """The request is valid, but it cannot run now: an activity holds what it needs, or the station is in another
    phase."""


class StationNotConfiguredError(VoxelError):
    """There is no ``station.yaml``."""


__all__ = [
    "BusyError",
    "NotFoundError",
    "RejectedError",
    "StaleError",
    "StartupError",
    "StationNotConfiguredError",
    "VoxelError",
]
