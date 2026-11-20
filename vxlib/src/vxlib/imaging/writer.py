"""What a camera needs from the code that writes its images: the :class:`ImageWriter` contract, the progress it
reports, and the read-only frame it lends to a live view.

An image is a stack of 2D frames. Array axis 0 counts the frames; where each pixel sits in space is the image's
:class:`~vxlib.vector.Transform`. A writer holds 1 image open at a time and keeps its buffers from image to image.
"""

import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Literal, Self

import numpy as np
from pydantic import BaseModel, Field, model_validator

from vxlib.dtype import Dtype
from vxlib.schema import FrozenModel
from vxlib.vector import IVec2D, Transform

type WhenFull = Literal["wait", "drop"]
"""What a writer does with a new batch when every buffer is busy: ``wait`` for one, or ``drop`` the whole batch."""


class FrameRange(FrozenModel):
    """The frames from ``first`` to ``last`` of an image, both included."""

    first: int = Field(ge=0)
    last: int = Field(ge=0)

    @model_validator(mode="after")
    def _in_order(self) -> Self:
        if self.last < self.first:
            raise ValueError(f"last ({self.last}) must not come before first ({self.first})")
        return self

    @property
    def count(self) -> int:
        return self.last - self.first + 1


class WriterProgress(FrozenModel):
    """How far the open image is: frames ``collected`` into memory and ``flushed`` to storage, and frames
    ``dropped``, of ``total``."""

    collected: int = Field(default=0, ge=0)
    flushed: int = Field(default=0, ge=0)
    dropped: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _in_order(self) -> Self:
        if not self.flushed <= self.collected <= self.total - self.dropped:
            raise ValueError(
                f"flushed ({self.flushed}) <= collected ({self.collected}) <= total ({self.total}) - dropped "
                f"({self.dropped})"
            )
        return self


class FrameLease:
    """Read-only access to 1 written frame. While it is held, the writer does not reuse the frame's memory; ``close``
    gives it back. Safe to close from any thread, and more than once."""

    def __init__(self, array: np.ndarray, release: Callable[[], None]) -> None:
        self._array = array.view()
        self._array.flags.writeable = False
        self._release: Callable[[], None] | None = release
        self._lock = threading.Lock()

    @property
    def array(self) -> np.ndarray:
        """The frame, read-only. Raise ``RuntimeError`` once the lease is closed."""
        with self._lock:
            if self._release is None:
                raise RuntimeError("frame lease is closed")
            return self._array

    def close(self) -> None:
        """Give the frame's memory back to the writer."""
        with self._lock:
            release, self._release = self._release, None
        if release is not None:
            release()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class ImageWriter[S: BaseModel, T](ABC):
    """Writes images, 1 open at a time, into storage. ``S`` is the writer's own settings and ``T`` where it writes:
    both are the writer's types, which the camera only carries. A writer keeps its buffers from image to image, so
    the next image opens fast; :meth:`release` frees them."""

    @abstractmethod
    def open_image(
        self,
        target: T,
        size: IVec2D,
        dtype: Dtype,
        transform: Transform,
        settings: S,
        ram_bytes: int,
        when_full: WhenFull = "wait",
    ) -> T:
        """Open 1 image at ``target``, of ``transform.shape[0]`` frames of ``size`` pixels, and give back where the
        image itself is written. Use at most ``ram_bytes`` of memory for buffers. ``when_full`` says what a batch
        that finds every buffer busy does: wait, or drop all its frames. Raise ``ValueError`` when ``size`` does not
        match ``transform.shape[1:]``."""

    @property
    @abstractmethod
    def batch_frames(self) -> int:
        """How many frames fill 1 buffer: a step scan pauses after each such batch."""

    @property
    @abstractmethod
    def ready_for_batch(self) -> bool:
        """Whether a free buffer can take the next batch now, without waiting."""

    @abstractmethod
    def new_frame(self) -> AbstractContextManager[np.ndarray]:
        """The memory for the next frame: fill it inside the block, and the frame counts once the block ends. A frame
        of a dropped batch gets scratch memory, and is thrown away."""

    @abstractmethod
    def latest_frame(self) -> FrameLease | None:
        """The last frame, lent read-only; ``None`` when it was dropped or none has come yet."""

    @property
    @abstractmethod
    def dropped(self) -> list[FrameRange]:
        """The frames of the open image dropped so far, or none when no image is open."""

    @property
    @abstractmethod
    def progress(self) -> WriterProgress:
        """How far the open image is, or all zeros when none is open."""

    @abstractmethod
    def close_image(self) -> None:
        """Write what is left of the open image and close it. The buffers stay for the next image."""

    @abstractmethod
    def release(self) -> None:
        """Close any open image and free the buffers."""
