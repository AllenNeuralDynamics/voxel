from pathlib import PurePosixPath
from types import SimpleNamespace

from cloudpathlib import S3Path
from ome_zarr_writer import DirectS3, Local, StagedS3
from vxl_records import (
    LocalLocation,
    LocationRole,
    LocationStatus,
    ObjectLocation,
    RemoteTarget,
)
from vxl_records import StorageSpec as RecordsStorageSpec

from vxl.camera import StorageSpec, resolve_storage
from vxl.camera import storage as camera_storage
from vxl.system import Remote
from vxlib import S3Store


def test_records_storage_spec_remains_available_from_camera(monkeypatch, tmp_path) -> None:
    system = SimpleNamespace(store=tmp_path / "store", scratch=tmp_path / "scratch", remotes={})
    monkeypatch.setattr(camera_storage, "System", lambda: system)
    spec = StorageSpec(path=PurePosixPath("experiment/run"))

    resolved = resolve_storage(spec, PurePosixPath("tile/profile/channel"))

    assert StorageSpec is RecordsStorageSpec
    assert isinstance(resolved, Local)
    assert resolved.target == tmp_path / "store/experiment/run/tile/profile/channel"


def _registry(tmp_path) -> SimpleNamespace:
    """A stand-in `System` whose registry holds one remote with a non-empty ``roots`` catalog."""
    remote = Remote(
        connection=S3Store(endpoint="http://10.128.113.13", region="aind"),
        roots={"Test Dir": "buffer/prefix"},
    )
    return SimpleNamespace(store=tmp_path / "store", scratch=tmp_path / "scratch", remotes={"vast": remote})


def test_resolve_direct_object_storage_hands_over_the_bare_connection(monkeypatch, tmp_path) -> None:
    """The writer hashes the store to cache its S3 client per connection, and a `Remote`'s ``roots``
    dict is unhashable -- so resolution must pass `Remote.connection`, never the `Remote` itself."""
    system = _registry(tmp_path)
    monkeypatch.setattr(camera_storage, "System", lambda: system)
    spec = StorageSpec(
        path=PurePosixPath("experiment/run"),
        remote=RemoteTarget(store="vast", root="buffer/prefix"),
    )

    resolved = resolve_storage(spec, PurePosixPath("tile/488"))

    assert isinstance(resolved, DirectS3)
    assert type(resolved.store) is S3Store
    assert hash(resolved.store) == hash(system.remotes["vast"].connection)
    assert str(resolved.target) == "s3://buffer/prefix/experiment/run/tile/488"


def test_resolve_staged_object_storage_hands_over_the_bare_connection(monkeypatch, tmp_path) -> None:
    system = _registry(tmp_path)
    monkeypatch.setattr(camera_storage, "System", lambda: system)
    spec = StorageSpec(
        path=PurePosixPath("experiment/run"),
        remote=RemoteTarget(store="vast", root="buffer/prefix", stage=True),
    )

    resolved = resolve_storage(spec, PurePosixPath("tile/488"))

    assert isinstance(resolved, StagedS3)
    assert type(resolved.store) is S3Store
    assert resolved.scratch == tmp_path / "scratch/experiment/run/tile/488"


def test_describe_local_dataset_location(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(camera_storage.System, "hostname", staticmethod(lambda: "camera-1"))
    spec = StorageSpec(path=PurePosixPath("experiment/run"))
    target = tmp_path / "experiment/run/tasks/0001/488/green.ome.zarr"

    location = camera_storage.describe_dataset_location(spec, target)

    assert location == LocalLocation(
        role=LocationRole.DESTINATION,
        status=LocationStatus.WRITING,
        host="camera-1",
        path=str(target),
    )


def test_describe_staged_object_dataset_location_uses_destination(monkeypatch) -> None:
    monkeypatch.setattr(camera_storage.System, "hostname", staticmethod(lambda: "camera-1"))
    spec = StorageSpec(
        path=PurePosixPath("experiment/run"),
        remote=RemoteTarget(store="vast", root="buffer/prefix", stage=True),
    )
    target = S3Path("s3://buffer/prefix/experiment/run/tasks/0001/488/green.ome.zarr")

    location = camera_storage.describe_dataset_location(spec, target)

    assert location == ObjectLocation(
        role=LocationRole.DESTINATION,
        status=LocationStatus.WRITING,
        host="camera-1",
        store="vast",
        bucket="buffer",
        key="prefix/experiment/run/tasks/0001/488/green.ome.zarr",
    )
