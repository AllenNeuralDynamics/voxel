"""
Test MultiBackend functionality.

Demonstrates writing to multiple backends simultaneously (LogBackend + LogBackend).
"""

import numpy as np
from rich import print
from rich.table import Table

from ome_zarr_writer import Dtype, OMEZarrWriter, ScaleLevel, UIVec3D, WriterConfig
from ome_zarr_writer.backends.base import MultiBackend
from ome_zarr_writer.backends.log import LogBackend


def test_multiwriter():
    """Test MultiBackend with two LogBackends (simulating dual storage)."""

    # Configuration
    v_shape = UIVec3D(z=50, y=512, x=512)
    max_level = ScaleLevel.L2

    c_shape = max_level.chunk_shape
    s_shape = WriterConfig.compute_shard_shape_from_target(
        v_shape=v_shape,
        c_shape=c_shape,
        dtype=Dtype.UINT16,
        target_shard_gb=0.01,
    )

    cfg = WriterConfig(
        name="test_multiwriter",
        volume_shape=v_shape,
        shard_shape=s_shape,
        chunk_shape=c_shape,
        dtype=Dtype.UINT16,
        max_level=max_level,
        batch_z_shards=1,
    )

    print("\n[bold cyan]MultiBackend Test[/bold cyan]")
    print(f"Volume: {v_shape}")
    print(f"Batch size: {cfg.batch_z} frames")
    print(f"Total batches: {cfg.num_batches}")

    # Create two separate log backends (simulating dual storage)
    storage_root = "./tmp"
    backend1 = LogBackend(cfg, storage_root)
    backend2 = LogBackend(cfg, storage_root)

    log_path_1 = backend1.log_path
    log_path_2 = backend2.log_path

    # Create MultiBackend with both backends
    multi_backend = MultiBackend(
        backends=[backend1, backend2],
        parallel=True,  # Write to both in parallel
        require_all=True,  # Both must succeed
    )

    print(f"\n[yellow]Writing to {len(multi_backend.backends)} backends in parallel[/yellow]")
    print(f"  Primary: {log_path_1}")
    print(f"  Backup:  {log_path_2}")

    # Run acquisition
    with OMEZarrWriter(multi_backend, slots=3) as writer:
        print(f"\n[yellow]Acquiring {v_shape.z} frames...[/yellow]")

        for z in range(v_shape.z):
            frame = np.random.randint(0, 1000, (v_shape.y, v_shape.x), dtype=np.uint16)
            writer.add_frame(frame)

        print(f"\n[green]Completed {v_shape.z} frames![/green]")

    # Verify both backends got all batches
    print("\n[bold yellow]Verification:[/bold yellow]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Backend", width=15)
    table.add_column("Batches Written", width=15)
    table.add_column("Log Path", width=40)

    table.add_row("Primary", str(backend1._batch_count), str(log_path_1))
    table.add_row("Backup", str(backend2._batch_count), str(log_path_2))
    table.add_row("MultiBackend", str(multi_backend._batch_count), "N/A")

    print(table)

    # Check if both match
    if backend1._batch_count == backend2._batch_count == multi_backend._batch_count:
        print("\n[green]✓ SUCCESS: All backends wrote the same number of batches![/green]")
    else:
        print("\n[red]✗ FAILURE: Batch counts don't match![/red]")

    # Show sample from logs
    print("\n[cyan]Sample from primary log:[/cyan]")
    with open(log_path_1, "r") as f:
        lines = f.readlines()
        for line in lines[-10:]:  # Last 10 lines
            print(f"  {line.rstrip()}")


def test_multiwriter_sequential():
    """Test MultiBackend with sequential writes (parallel=False)."""

    v_shape = UIVec3D(z=30, y=256, x=256)
    max_level = ScaleLevel.L1

    c_shape = max_level.chunk_shape
    s_shape = WriterConfig.compute_shard_shape_from_target(
        v_shape=v_shape,
        c_shape=c_shape,
        dtype=Dtype.UINT16,
        target_shard_gb=0.01,
    )

    cfg = WriterConfig(
        name="test_multiwriter_seq",
        volume_shape=v_shape,
        shard_shape=s_shape,
        chunk_shape=c_shape,
        dtype=Dtype.UINT16,
        max_level=max_level,
        batch_z_shards=1,
    )

    print("\n\n[bold cyan]MultiBackend Test (Sequential Mode)[/bold cyan]")

    backend1 = LogBackend(cfg, storage_root="./tmp")
    backend2 = LogBackend(cfg, storage_root="./tmp")

    multi_backend = MultiBackend(
        backends=[backend1, backend2],
        parallel=False,  # Sequential writes
        require_all=True,
    )

    print(f"[yellow]Writing sequentially to {len(multi_backend.backends)} backends[/yellow]")

    with OMEZarrWriter(multi_backend, slots=3) as writer:
        for z in range(v_shape.z):
            frame = np.full((v_shape.y, v_shape.x), z, dtype=np.uint16)
            writer.add_frame(frame)

    print(f"\n[green]Batches written: {multi_backend._batch_count}[/green]")
    print(f"  Backend 1: {backend1._batch_count}")
    print(f"  Backend 2: {backend2._batch_count}")


if __name__ == "__main__":
    # Test 1: Parallel writes
    test_multiwriter()

    # Test 2: Sequential writes
    test_multiwriter_sequential()

    print("\n[bold green]All MultiBackend tests complete![/bold green]")
