"""
Neuroglancer viewer examples using FastAPI.

This module provides convenience functions and examples for using FastAPIZarrServer
with Neuroglancer.
"""

from pathlib import Path

from fastapi import FastAPI
from rich import print

from ome_zarr_writer.ng_view import NGLUT, NGLayerConfig, ng_quick_view
from ome_zarr_writer.zarr_server.fastapi import FastAPIZarrServer


def ng_quick_view_fastapi(
    configs: list[NGLayerConfig],
    http_port: int = 9000,
    viewer_port: int = 8080,
    viewer_token: str = "ng_example",
    app: FastAPI | None = None,
):
    """
    Quick viewer for neuroglancer using FastAPI server.

    This is a convenience wrapper around the common ng_quick_view function
    that creates a FastAPIZarrServer automatically.

    Args:
        configs: List of layer configurations
        http_port: Port for HTTP file server
        viewer_port: Port for neuroglancer viewer
        viewer_token: Token for neuroglancer viewer
        app: Optional FastAPI app instance (creates new one if None)

    Returns:
        If blocking=False, returns (server, viewer) tuple for programmatic control
    """
    # Create FastAPI server
    server = FastAPIZarrServer(host="0.0.0.0", port=http_port, app=app)

    # Use common ng_quick_view
    return ng_quick_view(
        configs=configs,
        server=server,
        viewer_port=viewer_port,
        viewer_token=viewer_token,
    )


def example_local_v2():
    """Example: View local Zarr v2 dataset."""
    ng_quick_view_fastapi(
        configs=[
            NGLayerConfig(
                name="local_data_v2",
                sources=[Path("/media/localadmin/Data/samples/tile_000010_ch_561.zarr")],
                lut=NGLUT.CYAN,
                norm_min=0,
                norm_max=200,
            )
        ]
    )


def example_local_v3():
    """Example: View local Zarr v3 dataset."""
    src = Path("/media/localadmin/Data/duplicate/tile_000001_ch_488.zarr")
    ng_quick_view_fastapi(
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


def example_with_custom_app():
    """Example: Use a custom FastAPI app with additional routes."""
    app = FastAPI(title="My Custom Application")

    @app.get("/")
    def root():
        return {"message": "Hello from my custom app!"}

    @app.get("/health")
    def health():
        return {"status": "healthy"}

    src = Path("/media/localadmin/Data/duplicate/tile_000001_ch_488.zarr")
    ng_quick_view_fastapi(
        configs=[
            NGLayerConfig(
                name="local_data_v3",
                sources=[src],
                lut=NGLUT.CYAN,
                norm_min=0,
                norm_max=200,
            )
        ],
        app=app,
    )


if __name__ == "__main__":
    print("\n[yellow]Available examples:[/yellow]")
    print("1. example_local_v2() - Local Zarr v2 dataset")
    print("2. example_local_v3() - Local Zarr v3 dataset")
    print("4. example_with_custom_app() - Custom FastAPI app with additional routes")
    print("\n[dim]Uncomment one to run[/dim]\n")

    # example_local_v2()
    # example_local_v3()
    example_with_custom_app()
