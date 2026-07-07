"""Core type definitions for the rigup ecosystem.

These types are used throughout rigup and related packages for consistent
data representation across device drivers, camera handling, and schemas.
"""

from collections.abc import Awaitable, Callable, Iterable
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, final

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

type Teardown = Callable[[], None]
type AsyncTeardown = Callable[[], Awaitable[None]]


@final
class UnsetType:
    """Singleton marker for values that have not been supplied or computed."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET = UnsetType()


class SchemaModel(BaseModel):
    """Base class for schema models.

    Provides consistent configuration:
    - extra="forbid": Strict validation, no extra fields allowed
    - populate_by_name=True: Allows field names in addition to aliases
    - frozen=True: Immutable models for data integrity
    - arbitrary_types_allowed=False: Ensures type safety
    - Serialization defaults to exclude None values
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        frozen=True,
        arbitrary_types_allowed=False,
    )

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Override to exclude None by default."""
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs: Any) -> str:
        """Override to exclude None by default."""
        kwargs.setdefault("exclude_none", True)
        return super().model_dump_json(**kwargs)


class Dtype(StrEnum):
    """Data type enumeration for image/array data."""

    UINT8 = "uint8"
    UINT16 = "uint16"

    def __str__(self) -> str:
        return self.name.lower()

    def __repr__(self) -> str:
        return self.name.lower()

    @property
    def dtype(self) -> np.dtype:
        """Get the numpy dtype object."""
        return np.dtype(self.value)

    @property
    def itemsize(self) -> int:
        """Get the size in bytes of each element."""
        return np.dtype(self.value).itemsize

    @property
    def maximum(self) -> int:
        """Get the maximum representable value for this dtype."""
        return np.iinfo(self.value).max

    def calc_nbytes(self, shape: Iterable[int]) -> int:
        """Calculate total bytes for an array of the given shape."""
        return int(self.itemsize * np.prod(tuple(shape)))


class _S3Credentials(BaseModel):
    """Base for the S3 credential-resolution strategies. Carries the strategy and its non-secret
    parameters only — the secret bytes are resolved at runtime by the selected provider, never held
    here — so a store stays serializable to shareable config with no secrets."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EnvCredentials(_S3Credentials):
    """Resolve from the standard AWS environment variables (``AWS_ACCESS_KEY_ID``,
    ``AWS_SECRET_ACCESS_KEY``, and optionally ``AWS_SESSION_TOKEN``)."""

    type: Literal["environment"] = "environment"


class ProfileCredentials(_S3Credentials):
    """Resolve from a named ``~/.aws`` profile, optionally from non-default file paths."""

    type: Literal["profile"] = "profile"
    name: str = "default"
    config_file: Path | None = None
    credentials_file: Path | None = None


class ChainCredentials(_S3Credentials):
    """Resolve via the full default AWS chain (env vars, then profile, then instance/container metadata)."""

    type: Literal["chain"] = "chain"


class AnonymousCredentials(_S3Credentials):
    """Unsigned access to a public bucket; no credentials are resolved."""

    type: Literal["anonymous"] = "anonymous"


S3Credentials = Annotated[
    EnvCredentials | ProfileCredentials | ChainCredentials | AnonymousCredentials,
    Field(discriminator="type"),
]
"""How an :class:`S3Store` resolves credentials — a strategy tag plus non-secret parameters, never
the secrets themselves."""


class S3Store(BaseModel):
    """S3-compatible connection: where to reach a store and how it resolves credentials.
    Holds no secrets — the ``credentials`` strategy names a provider that resolves the secret bytes at
    runtime (env vars, a ``~/.aws`` profile, the default chain, or anonymous). Shared by the OME-Zarr
    writer/reader and the machine's remote registry; the endpoint must be passed explicitly because
    TensorStore can't read it from the environment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    endpoint: str | None = None  # None → AWS; else an S3-compatible endpoint, e.g. "http://10.128.113.13"
    region: str | None = None
    credentials: S3Credentials = EnvCredentials()
