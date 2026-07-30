"""Machine-local resolution and description of portable catalog storage."""

from pathlib import Path, PurePosixPath

from cloudpathlib import S3Path
from ome_zarr_writer import DirectS3, Local, StagedS3, Storage
from vxl_catalog import (
    DatasetLocation,
    LocalLocation,
    LocationRole,
    LocationStatus,
    ObjectLocation,
    StorageSpec,
)

from vxl.system import System


def resolve_storage(spec: StorageSpec, subpath: PurePosixPath | None = None) -> Storage:
    """Resolve ``spec`` to a concrete writer storage on the machine executing this function.

    The catalog model remains portable: local roots, scratch paths, object-store connections, and
    credentials are supplied only here from this machine's :class:`~vxl.system.System`.
    """
    relpath = spec.path / (subpath or PurePosixPath())
    if spec.remote is None:
        return Local(target=System().store / relpath)

    remotes = System().remotes
    if spec.remote.store not in remotes:
        raise KeyError(f"unknown remote store '{spec.remote.store}'; configured: {sorted(remotes)}")
    store = remotes[spec.remote.store]
    target = S3Path(f"s3://{spec.remote.root}") / relpath.as_posix()
    if spec.remote.stage:
        return StagedS3(scratch=System().scratch / relpath, target=target, store=store)
    return DirectS3(target=target, store=store)


def describe_dataset_location(spec: StorageSpec, target: Path | S3Path) -> DatasetLocation:
    """Describe a writer's concrete dataset target as a catalog location."""
    host = System.hostname()
    if spec.remote is None:
        if not isinstance(target, Path):
            raise TypeError(f"local storage resolved to a non-local target: {target}")
        return LocalLocation(
            role=LocationRole.DESTINATION,
            status=LocationStatus.WRITING,
            host=host,
            path=str(target),
        )

    if not isinstance(target, S3Path):
        raise TypeError(f"object storage resolved to a non-object target: {target}")
    return ObjectLocation(
        role=LocationRole.DESTINATION,
        status=LocationStatus.WRITING,
        host=host,
        store=spec.remote.store,
        bucket=target.bucket,
        key=target.key,
    )
