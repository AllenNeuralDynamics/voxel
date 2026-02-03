"""
Neuroglancer viewer examples using Python's built-in http.server.

This module provides convenience functions and examples for using HTTPDZarrServer
with Neuroglancer.
"""

from pathlib import Path

from rich import print

from ome_zarr_writer.ng_view import NGLUT, NGLayerConfig, S3Config, ng_quick_view


def create_multi_tile_s3_urls(
    tiles: list[int],
    channel: int,
    bucket: str = "aind-open-data",
    directory: str = "exaSPIM_709221_2025-05-16_12-00-49/SPIM.ome.zarr/",
):
    return [S3Config(bucket=bucket, path=f"{directory}/tile_{tile:06d}_ch_{channel}.zarr") for tile in tiles]


def create_aind_exaspim_s3_urls(
    uid: str,
    tiles: list[int],
    channel: int,
    bucket: str = "aind-open-data",
) -> list[S3Config]:
    directory = f"exaSPIM_{uid}/SPIM.ome.zarr"
    return create_multi_tile_s3_urls(tiles, channel, bucket, directory)


def example_local_v2():
    """Example: View local Zarr v2 dataset."""
    ng_quick_view(
        configs=[
            NGLayerConfig(
                name="local_data_v2",
                sources=[Path("/media/localadmin/Data/samples/tile_000010_ch_561.zarr")],
                lut=NGLUT.CYAN,
                norm_min=0,
                norm_max=200,
            )
        ],
    )


def example_local_v3():
    """Example: View local Zarr v3 dataset."""
    src = Path("/media/localadmin/Data/duplicate/tile_000001_ch_488.zarr")
    ng_quick_view(
        configs=[
            NGLayerConfig(
                name="local_data_v3",
                sources=[src],
                lut=NGLUT.CYAN,
                norm_min=0,
                norm_max=200,
            )
        ]
    )


def example_aind_exaspim_s3():
    """Example: View AIND exaSPIM S3 dataset."""
    ng_quick_view(
        viewer_token="ng_example",
        configs=[
            NGLayerConfig(
                "s3",
                create_aind_exaspim_s3_urls(
                    uid="794491_2025-10-21_12-31-25",
                    tiles=[10, 11],
                    channel=488,
                ),
                NGLUT.CYAN,
                norm_min=40,
                norm_max=100,
            ),
        ],
    )


if __name__ == "__main__":
    print("\n[yellow]Available examples:[/yellow]")
    print("1. example_local_v2() - Local Zarr v2 dataset")
    print("2. example_local_v3() - Local Zarr v3 dataset")
    print("3. example_mixed_sources() - Multiple layers with S3 + local")
    print("4. example_aind_exaspim_s3() - AIND exaSPIM S3 dataset")
    print("\n[dim]Uncomment one to run[/dim]\n")

    # example_local_v2()
    example_local_v3()
    # example_mixed_sources()
    # example_aind_exaspim_s3()
