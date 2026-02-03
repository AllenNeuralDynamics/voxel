"""
Utilities for S3 operations.

Provides helper functions for reading/writing files to S3 storage
using the S3Config configuration.
"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class S3AuthType(StrEnum):
    """S3 authentication method."""

    ANONYMOUS = "anonymous"
    ACCESS_KEY = "access_key"
    PROFILE = "profile"
    IAM_ROLE = "iam_role"
    DEFAULT = "default"


class S3Config(BaseModel):
    """
    S3 storage configuration for TensorStore backends.

    Supports multiple authentication methods and S3-compatible services.

    Examples:
        >>> # Anonymous access (public buckets)
        >>> config = S3Config(
        ...     bucket="public-bucket",
        ...     auth_type=S3AuthType.ANONYMOUS
        ... )

        >>> # AWS credentials
        >>> config = S3Config(
        ...     bucket="my-bucket",
        ...     auth_type=S3AuthType.ACCESS_KEY,
        ...     access_key_id="AKIAIOSFODNN7EXAMPLE",
        ...     secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        ... )

        >>> # AWS profile
        >>> config = S3Config(
        ...     bucket="my-bucket",
        ...     auth_type=S3AuthType.PROFILE,
        ...     profile="my-profile"
        ... )

        >>> # S3-compatible endpoint (MinIO, Wasabi, etc.)
        >>> config = S3Config(
        ...     bucket="my-bucket",
        ...     endpoint="https://s3.wasabisys.com",
        ...     region="us-east-1",
        ...     auth_type=S3AuthType.ACCESS_KEY,
        ...     access_key_id="...",
        ...     secret_access_key="..."
        ... )
    """

    # Required fields
    bucket: str = Field(..., description="S3 bucket name")
    path: str = Field(default="", description="Path within the bucket")

    # Authentication
    auth_type: S3AuthType = Field(default=S3AuthType.DEFAULT, description=f"{S3AuthType._member_names_}")
    access_key_id: str | None = Field(default=None, description="AWS access key ID (for access_key auth)")
    secret_access_key: str | None = Field(default=None, description="AWS secret access key (for access_key auth)")
    session_token: str | None = Field(default=None, description="AWS session token (for temporary credentials)")
    profile: str | None = Field(default=None, description="AWS profile name (for profile auth)")
    credentials_file: str | None = Field(default=None, description="Path to AWS credentials file (for profile auth)")

    # Endpoint configuration
    region: str | None = Field(default=None, description="AWS region (e.g., 'us-east-1')")
    endpoint: str | None = Field(default=None, description="Custom S3 endpoint URL (for S3-compatible services)")
    host_header: str | None = Field(default=None, description="Override HTTP host header for custom endpoints")

    # Performance tuning
    request_concurrency: int | None = Field(default=None, description="Max concurrent S3 requests (default: 32)")
    max_retries: int = Field(default=32, description="Maximum retry attempts")
    initial_retry_delay: float = Field(default=1.0, ge=0, description="Initial retry delay in seconds")
    max_retry_delay: float = Field(default=32.0, ge=0, description="Maximum retry delay in seconds")

    # Additional options
    requester_pays: bool = Field(default=False, description="Enable for requester-pays buckets")

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_auth_config(self) -> Self:
        """Validate that required auth fields are provided based on auth_type."""
        if self.auth_type == S3AuthType.ACCESS_KEY:
            if not self.access_key_id or not self.secret_access_key:
                raise ValueError("access_key_id and secret_access_key required for ACCESS_KEY auth")
        elif self.auth_type == S3AuthType.PROFILE:
            if not self.profile and not self.credentials_file:
                raise ValueError("profile or credentials_file required for PROFILE auth")
        return self

    def __truediv__(self, other: str) -> "S3Config":
        """
        Create a new S3Config with appended path (like pathlib.Path / operator).

        Args:
            other: Path component to append

        Returns:
            New S3Config with updated path

        Examples:
            >>> config = S3Config(bucket="my-bucket", auth_type=S3AuthType.ANONYMOUS)
            >>> data_config = config / "experiments" / "2024" / "data.zarr"
            >>> print(data_config.path)  # "experiments/2024/data.zarr"
        """
        new_path = f"{self.path.rstrip('/')}/{other}".lstrip("/")
        return self.model_copy(update={"path": new_path})

    def __str__(self) -> str:
        """String representation as S3 URL."""
        if self.path:
            return f"s3://{self.bucket}/{self.path}"
        return f"s3://{self.bucket}"

    @classmethod
    def from_url(cls, url: str, auth_type: S3AuthType = S3AuthType.ANONYMOUS, **kwargs) -> "S3Config":
        """
        Create S3Config from an S3 URL, defaulting to anonymous access.

        Args:
            url: S3 URL (e.g., "s3://bucket/path" or "s3://bucket")
            auth_type: Authentication type (default: ANONYMOUS)
            **kwargs: Additional S3Config parameters (access_key_id, region, etc.)

        Returns:
            S3Config instance

        Examples:
            >>> # Anonymous access (default)
            >>> config = S3Config.from_url("s3://public-bucket/data")

            >>> # With AWS credentials
            >>> config = S3Config.from_url(
            ...     "s3://my-bucket/data",
            ...     auth_type=S3AuthType.ACCESS_KEY,
            ...     access_key_id="AKIAIOSFODNN7EXAMPLE",
            ...     secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
            ... )

            >>> # With AWS profile
            >>> config = S3Config.from_url(
            ...     "s3://my-bucket",
            ...     auth_type=S3AuthType.PROFILE,
            ...     profile="my-profile"
            ... )
        """
        from urllib.parse import urlparse

        if not url.startswith("s3://"):
            raise ValueError(f"URL must start with 's3://': {url}")

        parsed = urlparse(url)
        bucket = parsed.netloc
        path = parsed.path.lstrip("/")

        if not bucket:
            raise ValueError(f"Bucket not found in URL: {url}")

        return cls(bucket=bucket, path=path, auth_type=auth_type, **kwargs)


def write_file_to_s3(s3_config: "S3Config", content: str | bytes, key: str | None = None) -> bool:
    """
    Write a file to S3 storage.

    Args:
        s3_config: S3Config with bucket, path, and authentication
        content: File content as string or bytes
        key: Optional key/filename to append to s3_config.path.
             If None, writes directly to s3_config.path

    Returns:
        True if successful, False otherwise

    Examples:
        >>> # Write to specific path
        >>> s3 = S3Config.from_url("s3://my-bucket/data")
        >>> write_file_to_s3(s3, "hello world", key="test.txt")
        >>> # Writes to: s3://my-bucket/data/test.txt

        >>> # Write to exact path in s3_config
        >>> s3 = S3Config.from_url("s3://my-bucket/data/test.txt")
        >>> write_file_to_s3(s3, "hello world")
        >>> # Writes to: s3://my-bucket/data/test.txt
    """
    try:
        from botocore.exceptions import ClientError, NoCredentialsError
    except ImportError as e:
        print(f"Warning: boto3 not available for S3 operations: {e}")
        return False

    # Build S3 key (path within bucket)
    if key:
        s3_key = f"{s3_config.path}/{key}".lstrip("/") if s3_config.path else key
    else:
        s3_key = s3_config.path

    # Convert content to bytes if needed
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    else:
        content_bytes = content

    # Create S3 client based on auth configuration
    try:
        s3_client = create_s3_client(s3_config)

        # Write to S3
        s3_client.put_object(
            Bucket=s3_config.bucket,
            Key=s3_key,
            Body=content_bytes,
        )
        return True

    except (NoCredentialsError, ClientError) as e:
        print(f"Error writing to S3: {e}")
        return False


def read_file_from_s3(s3_config: "S3Config", key: str | None = None) -> bytes | None:
    """
    Read a file from S3 storage.

    Args:
        s3_config: S3Config with bucket, path, and authentication
        key: Optional key/filename to append to s3_config.path.
             If None, reads directly from s3_config.path

    Returns:
        File content as bytes, or None if read failed

    Examples:
        >>> # Read from specific path
        >>> s3 = S3Config.from_url("s3://my-bucket/data")
        >>> content = read_file_from_s3(s3, key="test.txt")
        >>> # Reads from: s3://my-bucket/data/test.txt

        >>> # Read from exact path in s3_config
        >>> s3 = S3Config.from_url("s3://my-bucket/data/test.txt")
        >>> content = read_file_from_s3(s3)
        >>> # Reads from: s3://my-bucket/data/test.txt
    """
    try:
        from botocore.exceptions import ClientError, NoCredentialsError
    except ImportError as e:
        print(f"Warning: boto3 not available for S3 operations: {e}")
        return None

    # Build S3 key (path within bucket)
    if key:
        s3_key = f"{s3_config.path}/{key}".lstrip("/") if s3_config.path else key
    else:
        s3_key = s3_config.path

    # Create S3 client and read
    try:
        s3_client = create_s3_client(s3_config)

        response = s3_client.get_object(
            Bucket=s3_config.bucket,
            Key=s3_key,
        )
        return response["Body"].read()

    except (NoCredentialsError, ClientError) as e:
        print(f"Error reading from S3: {e}")
        return None


def create_s3_client(s3_config: "S3Config"):
    """
    Create a boto3 S3 client from S3Config.

    Args:
        s3_config: S3Config with authentication and endpoint settings

    Returns:
        Configured boto3 S3 client
    """
    import boto3

    session_kwargs = {}
    client_kwargs = {}

    # Configure authentication
    if s3_config.auth_type.value == "access_key":
        session_kwargs["aws_access_key_id"] = s3_config.access_key_id
        session_kwargs["aws_secret_access_key"] = s3_config.secret_access_key
        if s3_config.session_token:
            session_kwargs["aws_session_token"] = s3_config.session_token
    elif s3_config.auth_type.value == "profile":
        if s3_config.profile:
            session_kwargs["profile_name"] = s3_config.profile
    elif s3_config.auth_type.value == "anonymous":
        # For anonymous access, use unsigned config
        from botocore import UNSIGNED
        from botocore.config import Config

        client_kwargs["config"] = Config(signature_version=UNSIGNED)
    # For iam_role and default, boto3 handles it automatically

    # Configure region
    if s3_config.region:
        session_kwargs["region_name"] = s3_config.region

    # Configure custom endpoint
    if s3_config.endpoint:
        client_kwargs["endpoint_url"] = s3_config.endpoint

    # Create session and client
    session = boto3.Session(**session_kwargs)
    return session.client("s3", **client_kwargs)


def list_s3_objects(s3_config: "S3Config", prefix: str | None = None, max_keys: int = 1000) -> list[str]:
    """
    List objects in S3 bucket with optional prefix.

    Args:
        s3_config: S3Config with bucket and authentication
        prefix: Optional prefix to filter objects. If None, uses s3_config.path
        max_keys: Maximum number of keys to return (default: 1000)

    Returns:
        List of object keys (paths within bucket)

    Example:
        >>> s3 = S3Config.from_url("s3://my-bucket/data")
        >>> objects = list_s3_objects(s3, prefix="experiments/")
        >>> # Returns: ["experiments/2024/data.zarr", "experiments/2024/test.txt", ...]
    """
    try:
        from botocore.exceptions import ClientError, NoCredentialsError
    except ImportError as e:
        print(f"Warning: boto3 not available for S3 operations: {e}")
        return []

    # Use provided prefix, or fall back to s3_config.path
    list_prefix = prefix if prefix is not None else s3_config.path

    try:
        s3_client = create_s3_client(s3_config)

        response = s3_client.list_objects_v2(
            Bucket=s3_config.bucket,
            Prefix=list_prefix,
            MaxKeys=max_keys,
        )

        if "Contents" not in response:
            return []

        return [obj["Key"] for obj in response["Contents"]]

    except (NoCredentialsError, ClientError) as e:
        print(f"Error listing S3 objects: {e}")
        return []
