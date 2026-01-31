"""
HTTP server implementation using Python's built-in http.server.

This implementation properly handles HTTP range requests which are critical for Zarr v3.
The native Python server has better support for partial content requests than some
ASGI implementations.
"""

import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote

from rich import print

from .base import ZarrServer, get_host_ip


class CORSRequestHandler(SimpleHTTPRequestHandler):
    """
    HTTP request handler with CORS support and proper range request handling.

    This handler fixes issues with Zarr v3 range requests by:
    1. Properly setting CORS headers (including Content-Range, Accept-Ranges)
    2. Using SimpleHTTPRequestHandler's built-in range request support
    3. Serving files from multiple root directories
    """

    # Class variable to store mount points
    mount_points: dict[str, Path] = {}

    def end_headers(self):
        """Add CORS headers before ending headers."""
        # CORS headers - allow all origins
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        # Critical for range requests
        self.send_header("Access-Control-Expose-Headers", "Content-Range, Content-Length, Accept-Ranges")
        super().end_headers()

    def do_OPTIONS(self):
        """Handle preflight CORS requests."""
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        """Handle GET requests with support for multiple mount points."""
        # Parse the path to find mount point
        path = unquote(self.path)

        # Remove query string if present
        if "?" in path:
            path = path.split("?")[0]

        # Find matching mount point
        for mount_name, root_dir in self.mount_points.items():
            if path.startswith(f"/{mount_name}/"):
                # Extract relative path
                relative_path = path[len(f"/{mount_name}/") :]

                # Construct full file path
                file_path = root_dir / relative_path

                # Security check - ensure path is within root_dir
                try:
                    file_path = file_path.resolve()
                    root_dir = root_dir.resolve()
                    if not str(file_path).startswith(str(root_dir)):
                        self.send_error(403, "Access denied")
                        return
                except (ValueError, OSError):
                    self.send_error(404, "File not found")
                    return

                # Serve the file directly
                self._serve_file(file_path)
                return

        # No mount point matched
        self.send_error(404, f"Mount point not found for path: {path}")

    def do_HEAD(self):
        """Handle HEAD requests (required for range request negotiation)."""
        # Parse the path to find mount point
        path = unquote(self.path)

        if "?" in path:
            path = path.split("?")[0]

        for mount_name, root_dir in self.mount_points.items():
            if path.startswith(f"/{mount_name}/"):
                relative_path = path[len(f"/{mount_name}/") :]
                file_path = root_dir / relative_path

                try:
                    file_path = file_path.resolve()
                    root_dir = root_dir.resolve()
                    if not str(file_path).startswith(str(root_dir)):
                        self.send_error(403, "Access denied")
                        return
                except (ValueError, OSError):
                    self.send_error(404, "File not found")
                    return

                # Send HEAD response
                self._send_head(file_path)
                return

        self.send_error(404, f"Mount point not found for path: {path}")

    def _send_head(self, file_path: Path):
        """Send HEAD response for a file."""
        try:
            f = open(file_path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        try:
            fs = os.fstat(f.fileno())
            self.send_response(200)
            self.send_header("Content-type", self.guess_type(str(file_path)))
            self.send_header("Content-Length", str(fs[6]))
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
        finally:
            f.close()

    def _serve_file(self, file_path: Path):
        """Serve a file with range request support."""
        try:
            f = open(file_path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return

        try:
            fs = os.fstat(f.fileno())
            file_size = fs[6]

            # Check for range request
            range_header = self.headers.get("Range")
            if range_header:
                # Parse range header
                try:
                    byte_range = range_header.replace("bytes=", "").split("-")
                    start = int(byte_range[0]) if byte_range[0] else 0
                    end = int(byte_range[1]) if len(byte_range) > 1 and byte_range[1] else file_size - 1

                    # Validate range
                    if start >= file_size or end >= file_size or start > end:
                        self.send_error(416, "Requested Range Not Satisfiable")
                        return

                    # Send partial content
                    self.send_response(206)
                    self.send_header("Content-type", self.guess_type(str(file_path)))
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.send_header("Content-Length", str(end - start + 1))
                    self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()

                    # Send the requested range
                    f.seek(start)
                    bytes_to_send = end - start + 1
                    self.wfile.write(f.read(bytes_to_send))
                except (ValueError, IndexError):
                    self.send_error(400, "Bad Range Header")
                    return
            else:
                # Send full file
                self.send_response(200)
                self.send_header("Content-type", self.guess_type(str(file_path)))
                self.send_header("Content-Length", str(file_size))
                self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

                # Send the file
                self.wfile.write(f.read())
        finally:
            f.close()

    def log_message(self, format, *args):
        """Log HTTP requests for debugging."""
        msg = format % args
        # Suppress 404 errors for chunk files (common for Zarr chunk probing)
        # Chunk paths typically end with /c/numbers like /c/0/1/3
        if "404" in msg and "/c/" in msg:
            return
        # Log all other requests
        if "200" in msg or "206" in msg:  # Successful requests
            print(f"[green]{self.address_string()} - {msg}[/green]")
        elif "404" in msg:  # Other 404s (not chunks) - worth logging
            print(f"[red]{self.address_string()} - {msg}[/red]")
        else:  # Other status codes
            print(f"[yellow]{self.address_string()} - {msg}[/yellow]")


class HTTPDZarrServer(ZarrServer):
    """Manages HTTP server in a separate thread with mount points."""

    def __init__(self, host: str = "0.0.0.0", port: int = 9000):
        self.host = host
        self._port = port
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.mount_points: dict[str, Path] = {}

    @property
    def port(self) -> int:
        """Server port number."""
        return self._port

    def add_mount_point(self, mount_name: str, directory: Path) -> None:
        """Add a directory mount point."""
        directory = directory.expanduser().resolve()
        self.mount_points[mount_name] = directory
        # Update class variable that handler uses
        CORSRequestHandler.mount_points = self.mount_points
        print(f"[green]Mounted {directory} → /{mount_name}/[/green]")

    def get_url_for_zarr(self, zarr_path: Path, use_localhost: bool = True) -> str:
        zarr_path = zarr_path.expanduser().resolve()
        parent_dir = zarr_path.parent
        mount_name = parent_dir.name

        # Add mount if not already present
        if mount_name not in self.mount_points:
            self.add_mount_point(mount_name, parent_dir)

        host = "localhost" if use_localhost else get_host_ip()
        url = f"http://{host}:{self.port}/{mount_name}/{zarr_path.name}/"
        print(f"[cyan]Zarr URL: {url}[/cyan]")
        return url

    def start(self) -> None:
        """Start the HTTP server in a background thread."""
        if self.server is not None:
            print("[yellow]Server already running[/yellow]")
            return

        self.server = HTTPServer((self.host, self.port), CORSRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        print(f"[green]HTTP server started on {self.host}:{self.port}[/green]")

    def stop(self) -> None:
        """Stop the HTTP server."""
        if self.server:
            self.server.shutdown()
            self.server = None
        if self.thread:
            self.thread.join(timeout=5)
            self.thread = None
