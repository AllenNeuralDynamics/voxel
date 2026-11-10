"""Serializable, secret-free S3 connection configuration."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from .schema import FrozenModel


class _S3Credentials(FrozenModel):
    """Shared validation policy for S3 credential selectors."""


class EnvCredentials(_S3Credentials):
    """Resolve credentials from the standard AWS environment variables."""

    kind: Literal["environment"] = "environment"


class ProfileCredentials(_S3Credentials):
    """Resolve credentials from a named AWS profile."""

    kind: Literal["profile"] = "profile"
    name: str = "default"
    config_file: Path | None = None
    credentials_file: Path | None = None


class ChainCredentials(_S3Credentials):
    """Resolve credentials through the default AWS provider chain."""

    kind: Literal["chain"] = "chain"


class AnonymousCredentials(_S3Credentials):
    """Use unsigned access to a public bucket."""

    kind: Literal["anonymous"] = "anonymous"


S3Credentials = Annotated[
    EnvCredentials | ProfileCredentials | ChainCredentials | AnonymousCredentials,
    Field(discriminator="kind"),
]
"""How an S3 connection resolves credentials without carrying their secret values."""


class S3Store(FrozenModel):
    """S3-compatible endpoint, region, and credential-resolution strategy."""

    endpoint: str | None = None
    region: str | None = None
    credentials: S3Credentials = EnvCredentials()


__all__ = [
    "AnonymousCredentials",
    "ChainCredentials",
    "EnvCredentials",
    "ProfileCredentials",
    "S3Credentials",
    "S3Store",
]
