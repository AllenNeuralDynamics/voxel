"""Expected control-station configuration and feed failures."""


class StationNotConfiguredError(FileNotFoundError):
    """Raised when a control application is started without ``station.yaml``."""


class StationFeedLaggedError(RuntimeError):
    """Raised when a Station feed connection's bounded update buffer overflows."""


__all__ = ["StationFeedLaggedError", "StationNotConfiguredError"]
