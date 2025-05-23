from voxel.microscope import BuildSpec, IOSpecs, build_object
from voxel.pipeline.io.transfers.base import VoxelFileTransfer
from voxel.pipeline.io.writers.base import VoxelWriter
from voxel.utils.log_config import get_component_logger


class IOManager:
    """Manager for IO handlers."""

    def __init__(self, specs: IOSpecs) -> None:
        self.log = get_component_logger(self)
        self._specs, warnings = self._validate_specs(specs)
        if warnings:
            for warning in warnings:
                self.log.warning(warning)

    @property
    def available_writers(self) -> list[str]:
        """Get the available writers."""
        return list(self._specs.writers.keys())

    @property
    def available_transfers(self) -> list[str]:
        """Get the available transfers."""
        return list(self._specs.transfers.keys())

    def get_writer_instance(self, writer_name: str) -> VoxelWriter:
        """Get a writer by name."""
        if writer_name not in self._specs.writers:
            raise ValueError(f"Writer {writer_name} not found.")
        return build_object(self._specs.writers[writer_name])

    def get_transfer_instance(self, transfer_name: str) -> VoxelFileTransfer:
        """Get a transfer by name."""
        if transfer_name not in self._specs.transfers:
            raise ValueError(f"Transfer {transfer_name} not found.")
        return build_object(self._specs.transfers[transfer_name])

    @staticmethod
    def _validate_specs(specs: IOSpecs) -> tuple[IOSpecs, list[str]]:
        """Validate the IO specifications.
        - Make sure at least one valid writer is provided.
        - Provide warnings for any invalid writers/transfers.
        """
        valid_writers: dict[str, BuildSpec] = {}
        valid_transfers: dict[str, BuildSpec] = {}
        warnings = []
        for name, spec in specs.writers.items():
            try:
                writer = build_object(spec)
                if isinstance(writer, VoxelWriter):
                    valid_writers[name] = spec
                else:
                    warnings.append(f"Writer {name} is not a valid VoxelWriter.")
            except Exception as e:
                warnings.append(f"Error building writer {name}: {e}")
        for name, spec in specs.transfers.items():
            try:
                transfer = build_object(spec)
                if isinstance(transfer, VoxelFileTransfer):
                    valid_transfers[name] = spec
                else:
                    warnings.append(f"Transfer {name} is not a valid VoxelFileTransfer.")
            except Exception as e:
                warnings.append(f"Error building transfer {name}: {e}")
        if not valid_writers:
            warnings.append("No valid writers provided.")
        if not valid_transfers:
            warnings.append("No valid transfers provided.")
        validated_specs = IOSpecs(
            writers=valid_writers,
            transfers=valid_transfers,
        )
        return validated_specs, warnings
