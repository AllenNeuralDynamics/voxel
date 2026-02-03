"""
Example: Using TensorStore S3 Backend

This example demonstrates how to use the TensorStoreS3Backend to write
OME-Zarr data directly to S3-compatible storage.
"""

from vxlib.vec import UIVec3D

from ome_zarr_writer import S3AuthType, S3Config, WriterConfig
from ome_zarr_writer.backends.ts import TensorStoreBackend
from ome_zarr_writer.types import ScaleLevel


def example_aws_credentials():
    """Example: Using AWS credentials for authentication."""

    # Configure the writer
    cfg = WriterConfig(
        name="experiment_001",
        volume_shape=UIVec3D(100, 512, 512),
        shard_shape=UIVec3D(10, 128, 128),
        chunk_shape=UIVec3D(1, 64, 64),
        max_level=ScaleLevel.L3,
        batch_z_shards=1,
    )

    # Configure S3 with AWS credentials
    s3_config = S3Config(
        bucket="my-bucket",
        auth_type=S3AuthType.ACCESS_KEY,
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
    )

    # Create backend
    backend = TensorStoreBackend(cfg, s3_config / "experiments/2024")

    print(f"Backend initialized for s3://{s3_config.bucket}/experiments/2024")
    backend.close()


def example_aws_profile():
    """Example: Using AWS profile for authentication."""

    cfg = WriterConfig(
        name="experiment_002",
        volume_shape=UIVec3D(100, 512, 512),
        shard_shape=UIVec3D(10, 128, 128),
        chunk_shape=UIVec3D(1, 64, 64),
        max_level=ScaleLevel.L3,
        batch_z_shards=1,
    )

    # Configure S3 with AWS profile
    s3_config = S3Config(
        bucket="my-bucket",
        auth_type=S3AuthType.PROFILE,
        profile="my-profile",
        region="us-east-1",
    )

    backend = TensorStoreBackend(cfg, s3_config)
    print(f"Backend initialized with AWS profile: {s3_config.profile}")
    backend.close()


def example_anonymous_public_bucket():
    """Example: Anonymous access to public S3 bucket."""

    cfg = WriterConfig(
        name="public_data",
        volume_shape=UIVec3D(100, 512, 512),
        shard_shape=UIVec3D(10, 128, 128),
        chunk_shape=UIVec3D(1, 64, 64),
        max_level=ScaleLevel.L3,
        batch_z_shards=1,
    )

    # Configure S3 for anonymous access
    s3_config = S3Config(bucket="public-bucket", auth_type=S3AuthType.ANONYMOUS, path="")

    backend = TensorStoreBackend(cfg, s3_config)
    print("Backend initialized for anonymous access")
    backend.close()


def example_s3_compatible_minio():
    """Example: Using S3-compatible storage (MinIO, Wasabi, etc.)."""

    cfg = WriterConfig(
        name="minio_experiment",
        volume_shape=UIVec3D(100, 512, 512),
        shard_shape=UIVec3D(10, 128, 128),
        chunk_shape=UIVec3D(1, 64, 64),
        max_level=ScaleLevel.L3,
        batch_z_shards=1,
    )

    # Configure S3-compatible endpoint (MinIO example)
    s3_config = S3Config(
        bucket="my-bucket",
        endpoint="http://localhost:9000",  # MinIO default endpoint
        auth_type=S3AuthType.ACCESS_KEY,
        access_key_id="minioadmin",
        secret_access_key="minioadmin",
        region="us-east-1",
    )

    backend = TensorStoreBackend(cfg, s3_config)
    print(f"Backend initialized for MinIO at {s3_config.endpoint}")
    backend.close()


def example_with_performance_tuning():
    """Example: S3 backend with performance tuning."""

    cfg = WriterConfig(
        name="high_performance",
        volume_shape=UIVec3D(100, 512, 512),
        shard_shape=UIVec3D(10, 128, 128),
        chunk_shape=UIVec3D(1, 64, 64),
        max_level=ScaleLevel.L3,
        batch_z_shards=1,
    )

    # Configure S3 with performance tuning
    s3_config = S3Config(
        bucket="my-bucket",
        auth_type=S3AuthType.PROFILE,
        profile="my-profile",
        region="us-east-1",
        # Performance tuning
        request_concurrency=64,  # Increase concurrent requests
        max_retries=10,  # Reduce retry attempts
        initial_retry_delay=0.5,  # Faster retry
        max_retry_delay=10.0,
    )

    backend = TensorStoreBackend(cfg, s3_config)
    print("Backend initialized with custom performance settings")
    print(f"  Concurrency: {s3_config.request_concurrency}")
    print(f"  Max retries: {s3_config.max_retries}")
    backend.close()


def example_iam_role():
    """Example: Using IAM role (for EC2/ECS instances)."""

    cfg = WriterConfig(
        name="ec2_experiment",
        volume_shape=UIVec3D(100, 512, 512),
        shard_shape=UIVec3D(10, 128, 128),
        chunk_shape=UIVec3D(1, 64, 64),
        max_level=ScaleLevel.L3,
        batch_z_shards=1,
    )

    # Configure S3 to use IAM role
    s3_config = S3Config(
        bucket="my-bucket",
        auth_type=S3AuthType.IAM_ROLE,
        region="us-east-1",
    )

    backend = TensorStoreBackend(cfg, s3_config)
    print("Backend initialized using IAM role")
    backend.close()


if __name__ == "__main__":
    print("=" * 70)
    print("TensorStore S3 Backend Examples")
    print("=" * 70)
    print()

    print("1. AWS Credentials Authentication")
    print("-" * 70)
    try:
        example_aws_credentials()
    except Exception as e:
        print(f"  Note: {e}")
    print()

    print("2. AWS Profile Authentication")
    print("-" * 70)
    try:
        example_aws_profile()
    except Exception as e:
        print(f"  Note: {e}")
    print()

    print("3. Anonymous Access (Public Buckets)")
    print("-" * 70)
    try:
        example_anonymous_public_bucket()
    except Exception as e:
        print(f"  Note: {e}")
    print()

    print("4. S3-Compatible Storage (MinIO)")
    print("-" * 70)
    try:
        example_s3_compatible_minio()
    except Exception as e:
        print(f"  Note: {e}")
    print()

    print("5. Performance Tuning")
    print("-" * 70)
    try:
        example_with_performance_tuning()
    except Exception as e:
        print(f"  Note: {e}")
    print()

    print("6. IAM Role Authentication")
    print("-" * 70)
    try:
        example_iam_role()
    except Exception as e:
        print(f"  Note: {e}")
    print()

    print("=" * 70)
    print("All examples completed!")
    print("=" * 70)
