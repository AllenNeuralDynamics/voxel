"""Read-side utility for loading Zarr v2/v3 arrays via TensorStore.

The read-side mirror of the write-side `TSArrayWriter` (`array/ts.py`): opens an
existing array at a path -- a local `Path` (FileKvStore) or a cloudpathlib `S3Path`
(S3KvStore) -- and reads 3D slices into numpy arrays.

S3 credentials default to the environment (the AWS chain). Unlike the writer, the
reader also accepts an explicit `S3Auth` for cases the environment can't cover --
public/anonymous buckets, a MinIO endpoint, or cross-account reads.
"""

import os
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import pydantic_tensorstore as pts
import tensorstore as ts
from cloudpathlib import S3Path
from pydantic import BaseModel, ConfigDict, model_validator


class S3AuthType(StrEnum):
    """S3 authentication method."""

    ANONYMOUS = "anonymous"
    ACCESS_KEY = "access_key"
    PROFILE = "profile"
    IAM_ROLE = "iam_role"
    DEFAULT = "default"


class S3Auth(BaseModel):
    """Connection config for S3 reads: credentials, endpoint (for S3-compatible
    services like MinIO), region, and request tuning. Optional -- omit it to use
    the environment's default credential chain."""

    auth_type: S3AuthType = S3AuthType.DEFAULT
    access_key_id: str | None = None
    secret_access_key: str | None = None
    session_token: str | None = None
    profile: str | None = None
    credentials_file: str | None = None

    region: str | None = None
    endpoint: str | None = None
    host_header: str | None = None

    request_concurrency: int | None = None
    max_retries: int = 32
    initial_retry_delay: float = 1.0
    max_retry_delay: float = 32.0
    requester_pays: bool = False

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _validate_auth(self) -> "S3Auth":
        if self.auth_type is S3AuthType.ACCESS_KEY and not (self.access_key_id and self.secret_access_key):
            raise ValueError("ACCESS_KEY auth requires access_key_id and secret_access_key")
        if self.auth_type is S3AuthType.PROFILE and not (self.profile or self.credentials_file):
            raise ValueError("PROFILE auth requires profile or credentials_file")
        return self

    def aws_credentials(self) -> dict[str, Any] | None:
        """TensorStore `aws_credentials` block for this auth, or None for the
        environment's default chain."""
        match self.auth_type:
            case S3AuthType.ANONYMOUS:
                return {"type": "anonymous"}
            case S3AuthType.ACCESS_KEY:
                return {
                    "type": "access_key",
                    "access_key": self.access_key_id,
                    "secret_key": self.secret_access_key,
                    **({"session_token": self.session_token} if self.session_token else {}),
                }
            case S3AuthType.PROFILE:
                return {
                    "type": "profile",
                    **({"profile": self.profile} if self.profile else {}),
                    **({"filename": self.credentials_file} if self.credentials_file else {}),
                }
            case S3AuthType.IAM_ROLE:
                return {"type": "default"}
            case _:  # DEFAULT -> environment chain
                return None

    def retries(self) -> dict[str, Any] | None:
        """TensorStore `s3_request_retries` block, or None when all defaults."""
        if self.max_retries == 32 and self.initial_retry_delay == 1.0 and self.max_retry_delay == 32.0:
            return None
        return {
            "max_retries": self.max_retries,
            "initial_delay": f"{self.initial_retry_delay}s",
            "max_delay": f"{self.max_retry_delay}s",
        }

    def to_env(self) -> dict[str, str]:
        """The AWS environment variables this auth implies, for env-driven consumers
        (the writer's S3 access and s5cmd uploads, which read connection settings from
        the environment rather than an `S3Auth`).

        IAM_ROLE / DEFAULT rely on the ambient credential chain and add nothing;
        ANONYMOUS has no standard env form (use the explicit `S3Auth` on the reader).
        """
        env: dict[str, str] = {}
        if self.region:
            env["AWS_REGION"] = env["AWS_DEFAULT_REGION"] = self.region
        if self.endpoint:
            env["AWS_ENDPOINT_URL_S3"] = self.endpoint
        if self.auth_type is S3AuthType.ACCESS_KEY:
            env["AWS_ACCESS_KEY_ID"] = self.access_key_id or ""
            env["AWS_SECRET_ACCESS_KEY"] = self.secret_access_key or ""
            if self.session_token:
                env["AWS_SESSION_TOKEN"] = self.session_token
        elif self.auth_type is S3AuthType.PROFILE:
            if self.profile:
                env["AWS_PROFILE"] = self.profile
            if self.credentials_file:
                env["AWS_SHARED_CREDENTIALS_FILE"] = self.credentials_file
        return env

    def apply_env(self) -> None:
        """Set this auth's variables (`to_env()`) into `os.environ` for the process,
        so env-driven S3 (the writer, s5cmd) picks up these credentials/endpoint."""
        os.environ.update(self.to_env())


def _kvstore_for(target: Path | S3Path, auth: S3Auth | None) -> dict[str, Any]:
    """TensorStore kvstore spec for the array at `target`. For S3, `auth` (when given)
    supplies credentials / endpoint / tuning; otherwise S3 settings come from the
    environment. Local paths ignore `auth`."""
    if not isinstance(target, S3Path):
        return pts.FileKvStore(path=target.expanduser().resolve().as_posix()).model_dump(exclude_none=True, mode="json")
    if auth is None:
        spec = pts.S3KvStore(bucket=target.bucket, path=target.key)
    else:
        spec = pts.S3KvStore(
            bucket=target.bucket,
            path=target.key,
            aws_region=auth.region,
            endpoint=auth.endpoint,
            host_header=auth.host_header,
            requester_pays=auth.requester_pays,
            aws_credentials=auth.aws_credentials(),
            s3_request_retries=auth.retries(),
            context={"s3_request_concurrency": {"limit": auth.request_concurrency}}
            if auth.request_concurrency
            else None,
        )
    return spec.model_dump(exclude_none=True, mode="json")


class ZarrLoader:
    """Loads a single Zarr array via TensorStore. Open once, read many slices.

    `target` is the array's full path (local `Path` or `S3Path`); `auth` is optional
    S3 connection config (environment chain when omitted); `v3` selects the format.
    """

    def __init__(self, target: Path | S3Path, *, auth: S3Auth | None = None, v3: bool = True) -> None:
        driver = "zarr3" if v3 else "zarr"
        self._handle: Any = ts.open(
            {"driver": driver, "kvstore": _kvstore_for(target, auth), "open": True, "create": False}
        ).result()

    @property
    def rank(self) -> int:
        return int(self._handle.rank)

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(int(x) for x in self._handle.shape)

    def get_3d(self, z0: int = 0, n: int | None = None, z1: int | None = None) -> np.ndarray:
        """Load a 3D slice in (z, y, x). Leading axes (e.g. channel) are taken at index 0.

        `z1` (exclusive end) overrides `n` if both are given; otherwise the
        z-range is `[z0, z0 + (n or 128))`.
        """
        if z1 is None:
            z1 = z0 + (n if n is not None else 128)
        leading = (0,) * (self._handle.rank - 3)
        slices = (*leading, slice(z0, z1), slice(None), slice(None))
        return np.array(self._handle[slices])


def load_zarr(
    target: Path | S3Path,
    *,
    auth: S3Auth | None = None,
    v3: bool = True,
    z0: int = 0,
    n: int | None = None,
    z1: int | None = None,
) -> np.ndarray:
    """One-shot: open the array at `target`, read a 3D slice, return it."""
    return ZarrLoader(target, auth=auth, v3=v3).get_3d(z0, n, z1)
