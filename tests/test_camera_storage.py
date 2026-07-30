from pathlib import PurePosixPath
from types import SimpleNamespace

from cloudpathlib import S3Path
from ome_zarr_writer import Local
from vxl_catalog import (
    LocalLocation,
    LocationRole,
    LocationStatus,
    ObjectLocation,
    RemoteTarget,
)
from vxl_catalog import StorageSpec as CatalogStorageSpec

from vxl.camera import StorageSpec, resolve_storage
from vxl.camera import storage as camera_storage


def test_catalog_storage_spec_remains_available_from_camera(monkeypatch, tmp_path) -> None:
    system = SimpleNamespace(store=tmp_path / "store", scratch=tmp_path / "scratch", remotes={})
    monkeypatch.setattr(camera_storage, "System", lambda: system)
    spec = StorageSpec(path=PurePosixPath("experiment/run"))

    resolved = resolve_storage(spec, PurePosixPath("tile/profile/channel"))

    assert StorageSpec is CatalogStorageSpec
    assert isinstance(resolved, Local)
    assert resolved.target == tmp_path / "store/experiment/run/tile/profile/channel"


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
