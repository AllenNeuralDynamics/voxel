"""Expected station feed failures."""


class StationFeedLaggedError(RuntimeError):
    """Raised when a Station feed connection's bounded update buffer overflows."""


__all__ = ["StationFeedLaggedError"]
