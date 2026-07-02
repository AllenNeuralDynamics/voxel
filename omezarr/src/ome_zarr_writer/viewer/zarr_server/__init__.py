"""
Zarr server implementations for serving Zarr datasets over HTTP.

This package provides server implementations that can serve Zarr datasets
to clients like Neuroglancer or other applications.

Note: FastAPIZarrServer is only available if fastapi is installed.
Import it directly from .fastapi if needed.
"""

from .base import ZarrServer, get_host_ip, get_host_name
from .httpd import HTTPDZarrServer

__all__ = ["ZarrServer", "HTTPDZarrServer", "get_host_ip", "get_host_name"]

# from ome_zarr_writer.zarr_server.fastapi import FastAPIZarrServer
