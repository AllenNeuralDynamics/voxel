"""
FastAPI server implementation for serving Zarr datasets to Neuroglancer.

This implementation wraps FastAPI to conform to the ZarrServer interface,
allowing it to work with the common ng_quick_view function.
"""

import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from rich import print

from .base import ZarrServer, get_host_ip


class FastAPIZarrServer(ZarrServer):
    """
    FastAPI-based implementation of ZarrServer.

    This class wraps FastAPI to provide the ZarrServer interface,
    allowing it to be used with the common ng_quick_view function.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 9000, app: FastAPI | None = None):
        self.host = host
        self._port = port
        self.app = app if app is not None else FastAPI()
        self.server_thread: threading.Thread | None = None
        self._cors_added = False
        self._mounted_paths: dict[str, Path] = {}

    @property
    def port(self) -> int:
        """Server port number."""
        return self._port

    def _ensure_cors(self):
        """Add CORS middleware if not already added."""
        if not self._cors_added:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
                expose_headers=["Content-Range", "Content-Length", "Accept-Ranges"],
            )
            self._cors_added = True

    def get_url_for_zarr(self, zarr_path: Path, use_localhost: bool = True) -> str:
        """Get HTTP URL for a Zarr directory."""
        zarr_path = zarr_path.expanduser().resolve()
        parent_dir = zarr_path.parent
        mount_name = parent_dir.name

        # Add mount if not already present
        if mount_name not in self._mounted_paths:
            self.app.mount(
                f"/{mount_name}", StaticFiles(directory=str(parent_dir), html=False), name=f"zarr_{mount_name}"
            )
            self._mounted_paths[mount_name] = parent_dir
            print(f"[green]Mounted {parent_dir} → /{mount_name}/[/green]")

        host = "localhost" if use_localhost else get_host_ip()
        url = f"http://{host}:{self._port}/{mount_name}/{zarr_path.name}/"
        print(f"[cyan]Zarr URL: {url}[/cyan]")
        return url

    def start(self) -> None:
        """Start the FastAPI server in a background thread."""
        if self.server_thread is not None:
            print("[yellow]Server already running[/yellow]")
            return

        # Ensure CORS is configured
        self._ensure_cors()

        # Run uvicorn in a separate thread
        def run_server():
            uvicorn.run(self.app, host=self.host, port=self._port, log_level="info")

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        print(f"[green]FastAPI server started on {self.host}:{self._port}[/green]")

    def stop(self) -> None:
        """Stop the FastAPI server."""
        # Note: uvicorn doesn't provide a clean shutdown mechanism when run in a thread
        # For production use, consider running uvicorn in a subprocess instead
        if self.server_thread:
            print("[yellow]Note: FastAPI server running in background thread[/yellow]")
            print("[yellow]Server will stop when main program exits[/yellow]")
            self.server_thread = None
