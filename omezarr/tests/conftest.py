"""Shared fixtures for the ome_zarr_writer test suite.

`minio` starts a throwaway MinIO container for the module and yields a `Minio` handle (endpoint,
credentials, bucket, plus boto3-client and `S3Store` helpers). It **skips** — never fails — when
Docker or the image is unavailable, so the suite runs on any laptop. Used by the `slow`
integration tests (e.g. `test_s3.py`).
"""

import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from ome_zarr_writer import S3Store

_USER = "minioadmin"
_PASSWORD = "minioadmin"
_ENDPOINT = "http://127.0.0.1:9000"
_CONTAINER = "voxel-minio-test"
_BUCKET = "voxel-test"


@dataclass(frozen=True)
class Minio:
    """Handle to the running MinIO: endpoint/credentials plus helpers tests use to reach it."""

    endpoint: str
    user: str
    password: str
    bucket: str

    def client(self) -> Any:
        """A boto3 S3 client with the root creds (for bucket setup/inspection, not the writer)."""
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.user,
            aws_secret_access_key=self.password,
            region_name="us-east-1",
            config=Config(s3={"addressing_style": "path"}),
        )

    def store(self) -> S3Store:
        """An `S3Store` pointing at this MinIO (creds resolve from the ambient env)."""
        return S3Store(endpoint=self.endpoint, region="us-east-1")


def _await_ready(server: Minio, timeout_s: float = 30.0) -> None:
    """Poll the S3 API until it serves (confirms MinIO is up and credentials work), else skip."""
    client = server.client()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            client.list_buckets()
            return
        except (BotoCoreError, ClientError):
            time.sleep(0.5)
    pytest.skip("MinIO did not become ready in time")


@pytest.fixture(scope="module")
def minio() -> Iterator[Minio]:
    if shutil.which("docker") is None:
        pytest.skip("docker not available")
    subprocess.run(["docker", "rm", "-f", _CONTAINER], capture_output=True, check=False)
    started = subprocess.run(
        ["docker", "run", "-d", "--name", _CONTAINER, "-p", "9000:9000",
         "-e", f"MINIO_ROOT_USER={_USER}", "-e", f"MINIO_ROOT_PASSWORD={_PASSWORD}",
         "quay.io/minio/minio", "server", "/data"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    if started.returncode != 0:
        pytest.skip(f"could not start MinIO: {started.stderr.strip()}")
    server = Minio(endpoint=_ENDPOINT, user=_USER, password=_PASSWORD, bucket=_BUCKET)
    try:
        _await_ready(server)
        client = server.client()
        if server.bucket not in {b["Name"] for b in client.list_buckets()["Buckets"]}:
            client.create_bucket(Bucket=server.bucket)
        yield server
    finally:
        subprocess.run(["docker", "rm", "-f", _CONTAINER], capture_output=True, check=False)
