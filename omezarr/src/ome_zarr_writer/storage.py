"""Resolved write locations for a writer run, and the S3 connection that reaches them.

A `StorageSpec` (control-side, logical) resolves on the node into one concrete `Storage` variant,
one per write pipeline:

- `Local`    — write straight to a local directory.
- `DirectS3` — write straight to S3 (the array writers hit S3 via TensorStore).
- `StagedS3` — write to a local scratch dir, then upload the shards to S3 (s5cmd).

A `Storage` is a plain *location* — a base ``target`` path plus (for S3) a connection. It carries
no dataset naming; `OMEZarrWriter` appends the ``.ome.zarr`` suffix. Every variant's fields are
mandatory and always meaningful (there is no "scratch set but target is local" state to guard).

`S3Store` carries only connection *routing* (endpoint/region/profile), never secrets: credentials
come from the standard AWS chain, which TensorStore, cloudpathlib, and s5cmd all resolve natively.
Only the endpoint (and, for a custom endpoint, the region) must be passed explicitly, because
TensorStore cannot read the endpoint from the environment.
"""

from functools import lru_cache
from pathlib import Path
from typing import Self

from cloudpathlib import S3Client, S3Path
from pydantic import BaseModel, ConfigDict, model_validator
from vxlib import AnonymousCredentials, ProfileCredentials, S3Store


@lru_cache
def _s3_client(store: S3Store) -> S3Client:
    """A cloudpathlib client for `store`'s connection (endpoint + credential strategy; region via the
    profile/env). Bind S3 paths to it so cloudpathlib operations reach the configured endpoint.

    Cached per `S3Store` (frozen/hashable): `resolve()` rebuilds a `Storage` on every call, but the
    boto session + credential-chain walk should happen once per connection, not once per resolve."""
    creds = store.credentials
    profile_name = creds.name if isinstance(creds, ProfileCredentials) else None
    return S3Client(
        endpoint_url=store.endpoint,
        profile_name=profile_name,
        no_sign_request=isinstance(creds, AnonymousCredentials),
    )


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class StagingConfig(_Frozen):
    """Tuning for staged (scratch → S3) upload."""

    max_pending: int = 4  # batches uploaded-or-queued before the flush blocks (bounds scratch growth)
    numworkers: int = 256  # s5cmd parallelism per invocation
    retry_count: int = 10  # s5cmd per-object retries


class Local(_Frozen):
    """Write directly to a local directory."""

    target: Path


class _S3(_Frozen):
    """Common S3 fields: the ``target`` (bound at construction to a cloudpathlib client for the
    connection, so cloudpathlib operations reach the endpoint) and the ``store`` connection (also
    used to configure the TensorStore and s5cmd clients, which don't take a cloudpathlib client)."""

    target: S3Path
    store: S3Store

    @model_validator(mode="after")
    def _bind_client(self) -> Self:
        # `store` is hashable at runtime (frozen model) so it's a valid lru_cache key; pydantic's stub
        # still types __hash__ as None, so pyright can't see that — hence the ignore.
        client = _s3_client(self.store)  # pyright: ignore[reportArgumentType]
        # Frozen model: assign via object.__setattr__ (plain `self.target =` raises "Instance is frozen").
        object.__setattr__(self, "target", S3Path(str(self.target), client=client))
        return self


class DirectS3(_S3):
    """Write straight to S3 — the array writers author shards at the S3 target directly."""


class StagedS3(_S3):
    """Write shards to a local scratch dir, then upload them to the S3 target."""

    scratch: Path
    tuning: StagingConfig = StagingConfig()


Storage = Local | DirectS3 | StagedS3
"""A resolved, concrete write *location*: a base path plus connection. `OMEZarrWriter` names the
dataset (appends ``.ome.zarr``). Built from a `StorageSpec` on the node."""
