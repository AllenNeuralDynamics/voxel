from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ome_zarr_writer.buffer import MultiScaleBuffer
from ome_zarr_writer.config import WriterConfig
from ome_zarr_writer.s3_utils import S3Config
from ome_zarr_writer.metadata import Zarr3GroupMeta


class Backend(ABC):
    """
    Abstract base class for OME-Zarr storage backends.

    All backends must accept WriterConfig in __init__ and store it.
    Implementations write downsampled multi-scale buffers to various storage backends.

    The storage_root can be:
    - str or Path: Local filesystem path
    - S3Config: S3 storage configuration (for S3-compatible backends)
    """

    def __init__(self, cfg: WriterConfig, storage_root: str | Path | S3Config):
        self.cfg = cfg
        self.overwrite = True

        metadata_json = Zarr3GroupMeta.from_ome(self.cfg.ome).to_json()
        if isinstance(storage_root, S3Config):
            from ome_zarr_writer.s3_utils import write_file_to_s3

            self._is_local = False
            self.storage_root = storage_root / self.ome_zarr_filename(cfg.name)
            success = write_file_to_s3(self.storage_root, metadata_json, key="zarr.json")
            if not success:
                raise ValueError(f"Could not write zarr.json metadata to S3: {self.storage_root}")
        else:
            self._is_local = True
            self.storage_root = Path(storage_root) / self.ome_zarr_filename(cfg.name)
            self.storage_root.mkdir(parents=True, exist_ok=True)
            zarr_json_path = self.storage_root / "zarr.json"
            with zarr_json_path.open("w") as f:
                f.write(metadata_json)

        self._initialize()

    @staticmethod
    def ome_zarr_filename(name: str) -> str:
        if name.endswith(".ome.zarr"):
            return name
        elif name.endswith(".zarr"):
            # Replace .zarr with .ome.zarr
            return name[:-5] + ".ome.zarr"
        else:
            # Append .ome.zarr
            return f"{name}.ome.zarr"

    # def _write_zarr_group_metadata(self) -> None:
    #     """Write zarr.json metadata file to root path."""
    #     self.root_path.mkdir(parents=True, exist_ok=True)
    #     zarr_json_path = self.root_path / "zarr.json"
    #     with zarr_json_path.open("w") as f:
    #         f.write(Zarr3GroupMeta.from_ome(self.cfg.ome).to_json())

    @abstractmethod
    def _initialize(self) -> None:
        """Open writer for writing."""
        ...

    @abstractmethod
    def write_batch(self, buffer: MultiScaleBuffer) -> bool:
        """
        Write a completed buffer batch to storage.

        Args:
            buffer: MultiScaleBuffer with all scale levels computed (stage=READY)

        Returns:
            True on success, False on failure
        """
        ...

    @abstractmethod
    def _finalize(self) -> None:
        """Clean up resources (flush, close files, etc.)."""
        ...

    def close(self):
        self._finalize()


class MultiBackend(Backend):
    def __init__(self, backends: list[Backend], parallel: bool = True, require_all: bool = True):
        if not backends:
            raise ValueError("At least one backend must be provided.")

        # Validate all backends have same config
        config = backends[0].cfg
        if not all(backend.cfg == config for backend in backends):
            raise ValueError("All backends must have the same config.")

        # Use the storage_root from the first backend
        storage_root = backends[0].storage_root
        super().__init__(config, storage_root)
        self.backends = backends
        self.parallel = parallel
        self.require_all = require_all
        self._batch_count = 0

        # For parallel writes
        if parallel:
            self._executor = ThreadPoolExecutor(max_workers=len(backends))

    def _initialize(self) -> None:
        pass

    def write_batch(self, buffer: MultiScaleBuffer) -> bool:
        """
        Write batch to all child backends.

        Args:
            buffer: MultiScaleBuffer with computed pyramid

        Returns:
            True if write succeeds according to require_all policy:
            - require_all=True: ALL backends must succeed
            - require_all=False: At least ONE backend must succeed
        """
        if self.parallel:
            # Write to all backends in parallel
            futures = [self._executor.submit(writer.write_batch, buffer) for writer in self.backends]
            results = [f.result() for f in futures]
        else:
            # Write sequentially
            results = [writer.write_batch(buffer) for writer in self.backends]

        # Log any failures for debugging
        for i, (writer, success) in enumerate(zip(self.backends, results)):
            if not success:
                writer_name = type(writer).__name__
                print(f"Warning: Writer {i} ({writer_name}) failed for batch {buffer.batch_idx}")

        # Determine success based on policy
        if self.require_all:
            success = all(results)
        else:
            success = any(results)

        if success:
            self._batch_count += 1

        return success

    def _finalize(self) -> None:
        """Close all child backends and cleanup resources."""
        # Close all backends, catching exceptions to ensure all get closed
        for i, backend in enumerate(self.backends):
            try:
                backend._finalize()
            except Exception as e:
                backend_name = type(backend).__name__
                print(f"Error closing backend {i} ({backend_name}): {e}")

        # Shutdown executor if using parallel mode
        if self.parallel:
            self._executor.shutdown(wait=True)
