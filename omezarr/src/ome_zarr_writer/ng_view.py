"""
Base classes and common functions for Neuroglancer viewers.

This module provides abstractions that work with both FastAPI and httpd-based servers.
"""

from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path

import neuroglancer as ng

from ome_zarr_writer.s3_utils import S3Config
from ome_zarr_writer.zarr_server import HTTPDZarrServer
from ome_zarr_writer.zarr_server.base import ZarrServer, get_host_ip, get_host_name


def replace_hostname_with_ip(viewer):
    return str(viewer).replace(f"http://{get_host_name()}:", f"http://{get_host_ip()}:")


class NGLUT(StrEnum):
    CYAN = "#59d5f8"
    MAGENTA = "#f059f8"
    YELLOW = "#f5f85c"
    RED = "#ff0000"
    GREEN = "#00ff00"
    BLUE = "#0000ff"
    WHITE = "#ffffff"

    def get_shader(self, min_val: float = 0.0, max_val: float = 1000.0) -> str:
        return f"""
    #uicontrol vec3 color color(default="{self.value}")
    #uicontrol invlerp normalized(range=[{min_val}, {max_val}])
    void main() {{
        emitRGB(color * normalized(getDataValue(0)));
    }}
    """


# class S3Config:
#     def __init__(self, bucket: str, key: str):
#         self.bucket = bucket
#         self.path = key.rstrip("/")

#     def __str__(self) -> str:
#         return f"s3://{self.bucket}/{self.path}"

#     def __truediv__(self, other: str) -> "S3Config":
#         return S3Config(self.bucket, f"{self.path}/{str(other)}")


NGLayerSource = S3Config | Path | str


class NGLayerConfig:
    def __init__(
        self,
        name: str,
        sources: Sequence[NGLayerSource],
        lut: NGLUT = NGLUT.CYAN,
        norm_min: float = 0.0,
        norm_max: float = 1000.0,
    ):
        self.name = name
        self.lut = lut
        self.norm_min = norm_min
        self.norm_max = norm_max
        self._local_sources: list[Path] = []
        self._s3_sources: list[S3Config] = []
        for source in sources:
            if isinstance(source, Path):
                self._local_sources.append(source.expanduser().resolve())
            elif isinstance(source, str):
                self._local_sources.append(Path(source).expanduser().resolve())
            elif isinstance(source, S3Config):
                self._s3_sources.append(source)

    @property
    def local_sources(self) -> list[Path]:
        return self._local_sources

    @property
    def s3_sources(self) -> list[S3Config]:
        return self._s3_sources


def build_viewer(
    configs: list[NGLayerConfig],
    server: ZarrServer,
    viewer_port: int = 8080,
    viewer_token: str | None = None,
) -> ng.Viewer:
    """
    Build a neuroglancer viewer with the given layer configurations.

    This function works with any server that inherits from ZarrServer
    (e.g., HTTPServerManager or FastAPI-based implementations).

    Args:
        configs: List of layer configurations
        server: Server inheriting from ZarrServer
        viewer_port: Port for neuroglancer viewer
        viewer_token: Optional token for viewer URL

    Returns:
        Configured neuroglancer viewer
    """
    ng.set_server_bind_address("0.0.0.0", viewer_port)
    viewer = ng.Viewer(token=viewer_token)

    with viewer.txn() as state:
        for config in configs:
            source_urls: list[str] = []

            # Add S3 sources
            for s3_url in config.s3_sources:
                source_urls.append(f"zarr://{s3_url}")

            # Add local sources
            for path in config.local_sources:
                url = server.get_url_for_zarr(path)
                source_urls.append(f"zarr://{url}")

            # Create layer
            layer = ng.ImageLayer(source=source_urls)
            layer.shader = config.lut.get_shader(min_val=config.norm_min, max_val=config.norm_max)
            # layer.annotationColor = ""
            state.layers[config.name] = layer

        for layer in state.layers:
            if "__bounds__" in layer.name.lower():
                layer.visible = False

        # Set coordinate space
        state.dimensions = ng.CoordinateSpace(
            names=["z", "y", "x"],
            units=["µm", "µm", "µm"],
            scales=[1.0, 1.0, 1.0],
        )

    return viewer


def ng_quick_view(
    configs: list[NGLayerConfig],
    server: ZarrServer | None = None,
    viewer_port: int = 8080,
    viewer_token: str = "ng",
):
    """
    Quick viewer for neuroglancer that works with any ZarrServer implementation.

    Args:
        configs: List of layer configurations
        server: Server instance (must inherit from ZarrServer)
        viewer_port: Port for neuroglancer viewer
        viewer_token: Token for neuroglancer viewer
    """
    from rich import print

    if server is None:
        server = HTTPDZarrServer(host="0.0.0.0", port=9000)

    # Start server if not already running
    server.start()

    # Build viewer
    viewer = build_viewer(configs, server=server, viewer_port=viewer_port, viewer_token=viewer_token)

    # Display connection info
    host_ip = get_host_ip()
    viewer_url = replace_hostname_with_ip(viewer)
    print(
        f"\nRun port forwarding command: ssh -L {server.port}:localhost:{server.port} -L {viewer_port}:localhost:{viewer_port} {host_ip}"
    )
    print(f"\n[bold green]Neuroglancer viewer: {viewer_url}[/bold green]")
    print(f"[green]HTTP server: http://{host_ip}:{server.port}/[/green]")
    print("\n[yellow]Press Ctrl+C to stop[/yellow]\n")

    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[yellow]Shutting down...[/yellow]")
        server.stop()
        print("[green]Server stopped[/green]")
