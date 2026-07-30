import datetime
import json
from pathlib import PurePosixPath
from uuid import UUID

import pytest
from pydantic import ValidationError
from vxl_catalog import (
    AcquisitionManifest,
    AcquisitionOrigin,
    AcquisitionStatus,
    AcquisitionVolume,
    Dataset,
    DatasetStatus,
    LocalLocation,
    LocationRole,
    LocationStatus,
    ObjectLocation,
    RemoteTarget,
    StorageSpec,
    VolumeStatus,
)

ACQUISITION_ID = UUID("12345678-1234-5678-1234-567812345678")
CREATED_AT = datetime.datetime(2026, 7, 29, 18, 30, tzinfo=datetime.UTC)


def _manifest() -> AcquisitionManifest:
    return AcquisitionManifest(
        id=ACQUISITION_ID,
        instrument="exaspim-1",
        origin=AcquisitionOrigin(host="controller-1", operator="operator"),
        status=AcquisitionStatus.RUNNING,
        created_at=CREATED_AT,
        started_at=CREATED_AT,
        storage=StorageSpec(
            path=PurePosixPath("experiment-42/run-7"),
            remote=RemoteTarget(store="vast", root="buffer/incoming", stage=True),
        ),
        bench_snapshot={"metadata": {"sample": "mouse-1"}, "batch_z": 64},
        hardware_snapshot={"cameras": {"left": {"node": "camera-1"}}},
        volumes=[
            AcquisitionVolume(
                task="tile-a",
                profile="488",
                status=VolumeStatus.RUNNING,
                datasets={
                    "green": Dataset(
                        status=DatasetStatus.WRITING,
                        locations=[
                            LocalLocation(
                                role=LocationRole.STAGING,
                                status=LocationStatus.WRITING,
                                host="camera-1",
                                path="/scratch/experiment-42/run-7/tile-a/488/green.ome.zarr",
                            ),
                            ObjectLocation(
                                role=LocationRole.DESTINATION,
                                status=LocationStatus.WRITING,
                                host="camera-1",
                                store="vast",
                                bucket="buffer",
                                key="incoming/experiment-42/run-7/tile-a/488/green.ome.zarr",
                            ),
                        ],
                    )
                },
            )
        ],
    )


def test_manifest_json_round_trip() -> None:
    manifest = _manifest()

    restored = AcquisitionManifest.model_validate_json(manifest.model_dump_json())

    assert restored == manifest
    payload = json.loads(manifest.model_dump_json())
    assert payload["id"] == str(ACQUISITION_ID)
    assert payload["storage"]["path"] == "experiment-42/run-7"
    assert payload["volumes"][0]["datasets"]["green"]["locations"][0]["kind"] == "local"
    assert payload["volumes"][0]["datasets"]["green"]["locations"][1]["kind"] == "object"


@pytest.mark.parametrize("path", ["/absolute/run", "../outside", "experiment/../../outside"])
def test_storage_path_stays_relative_to_root(path: str) -> None:
    with pytest.raises(ValidationError, match="path must be relative"):
        StorageSpec(path=PurePosixPath(path))


def test_manifest_rejects_duplicate_volume_keys() -> None:
    manifest = _manifest()

    with pytest.raises(ValidationError, match="task/profile pairs must be unique"):
        AcquisitionManifest.model_validate(
            {
                **manifest.model_dump(),
                "volumes": [
                    AcquisitionVolume(task="tile-a", profile="488"),
                    AcquisitionVolume(task="tile-a", profile="488"),
                ],
            }
        )


def test_volume_rejects_an_empty_channel_key() -> None:
    with pytest.raises(ValidationError):
        AcquisitionVolume(task="tile-a", profile="488", datasets={"": Dataset()})


def test_manifest_rejects_naive_timestamps() -> None:
    manifest = _manifest()

    with pytest.raises(ValidationError):
        AcquisitionManifest.model_validate(
            {
                **manifest.model_dump(),
                "created_at": CREATED_AT.replace(tzinfo=None),
            }
        )
