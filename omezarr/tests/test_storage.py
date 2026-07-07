"""Unit tests for storage: variant invariants, and the writer's `.ome.zarr` dataset naming.

The 'unit' tier exemplar: fast and hermetic (no I/O, no network, no Docker), so it runs on every
push. Contrast with `test_s3.py`, the 'integration' (`slow`) tier that needs a live endpoint.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from cloudpathlib import S3Path
from pydantic import ValidationError

from ome_zarr_writer.storage import DirectS3, Local, S3Store, StagedS3
from ome_zarr_writer.writer import _as_ome_zarr


@pytest.mark.parametrize(
    "factory",
    [
        # Configs arrive as data (YAML/JSON) and are validated; each illegal shape must be rejected.
        pytest.param(lambda: Local.model_validate({"target": Path("/d"), "store": S3Store()}), id="local-with-store"),
        pytest.param(
            lambda: DirectS3.model_validate({"target": S3Path("s3://b/k"), "store": S3Store(), "scratch": Path("/s")}),
            id="direct-with-scratch",
        ),
        pytest.param(
            lambda: StagedS3.model_validate({"target": S3Path("s3://b/k"), "store": S3Store()}),
            id="staged-missing-scratch",
        ),
    ],
)
def test_illegal_states_are_unrepresentable(factory: Callable[[], object]) -> None:
    """Each variant's fields are exactly what that pipeline needs — no more, no less."""
    with pytest.raises(ValidationError):
        factory()


def test_storage_target_is_a_plain_location() -> None:
    """`Storage` carries the bare base path; naming the dataset is the writer's job."""
    assert Local(target=Path("/data/exp")).target == Path("/data/exp")  # no .ome.zarr on the location


@pytest.mark.parametrize(
    ("base", "expected"),
    [
        (Path("/data/exp"), Path("/data/exp.ome.zarr")),
        (Path("/data/exp.ome.zarr"), Path("/data/exp.ome.zarr")),  # idempotent
        (S3Path("s3://bucket/exp"), S3Path("s3://bucket/exp.ome.zarr")),
    ],
)
def test_writer_names_dataset_with_ome_zarr(base: Path | S3Path, expected: Path | S3Path) -> None:
    assert _as_ome_zarr(base) == expected
