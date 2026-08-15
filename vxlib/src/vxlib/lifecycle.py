"""Shared lifecycle callback types."""

from collections.abc import Callable

type Teardown = Callable[[], None]

__all__ = ["Teardown"]
