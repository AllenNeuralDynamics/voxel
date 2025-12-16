"""Device widget runner - spawns DeviceService subprocess and creates widget."""

import asyncio
import logging
import socket
from dataclasses import dataclass, field
from multiprocessing import Process, Queue
from typing import Any

import qasync
import zmq
import zmq.asyncio
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow
from PySide6.QtWidgets import QWidget as QtWidget

from pyrig import Device
from pyrig.config import DeviceConfig
from pyrig.conn import DeviceAddress, DeviceAddressTCP, DeviceClient, DeviceService
from spim_widgets.base import DeviceClientWidget

logger = logging.getLogger(__name__)


def _find_free_port() -> int:
    """Find a free port by letting the OS choose one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def _run_device_service(
    device_cls: type[Device],
    device_kwargs: dict[str, Any],
    service_cls: type[DeviceService],
    rpc_port: int,
    pub_port: int,
    port_queue: Queue,
    log_level: int = logging.INFO,
) -> None:
    """Run a device service in a subprocess.

    This is the target function for multiprocessing.Process.
    Must remain a standalone function to be picklable for multiprocessing.
    """
    from pyrig.utils import configure_logging

    configure_logging(level=log_level)

    async def _run_async():
        # Create device
        device = device_cls(**device_kwargs)
        logger.info(f"Created device: {device.uid}")

        # Create ZMQ context
        zctx = zmq.asyncio.Context()

        # Create connection info
        conn = DeviceAddressTCP(host="0.0.0.0", rpc=rpc_port, pub=pub_port)

        # Create service
        service = service_cls(device, conn, zctx)
        logger.info(f"DeviceService started on rpc={rpc_port}, pub={pub_port}")

        # Notify parent process that we're ready
        port_queue.put({"rpc": rpc_port, "pub": pub_port, "status": "ready"})

        try:
            # Keep service running
            await asyncio.Event().wait()
        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.info(f"Shutting down device service for {device.uid}")
        finally:
            service.close()
            zctx.term()

    try:
        asyncio.run(_run_async())
    except Exception as e:
        logger.exception("Error in device service subprocess")
        port_queue.put({"status": "error", "error": str(e)})


@dataclass
class DeviceServiceInfo:
    """Information about a spawned device service."""

    device_id: str
    conn: DeviceAddress
    process: Process


@dataclass
class WidgetRunnerConfig:
    """Configuration for running multiple device widgets.

    Args:
        devices: Mapping of device_id to DeviceConfig
        widgets: Mapping of device_id to widget class
        services: Optional mapping of device_id to service class (defaults to DeviceService)
        window_title: Title for the application window
        window_size: (width, height) tuple for window size
    """

    devices: dict[str, DeviceConfig]
    widgets: dict[str, type[DeviceClientWidget]]
    services: dict[str, type[DeviceService]] = field(default_factory=dict)
    window_title: str = "Device Widget Runner"
    window_size: tuple[int, int] = (800, 600)


class DeviceWidgetRunner:
    """Manages the lifecycle of multiple device service subprocesses and their widgets.

    This class handles:
    - Spawning device service subprocesses for each device
    - Creating DeviceClients to communicate with services
    - Creating and managing widgets for each device
    - Cleanup of all resources on shutdown
    """

    zctx = zmq.asyncio.Context()

    def __init__(self, cfg: WidgetRunnerConfig) -> None:
        self.cfg = cfg  # Fixed typo: was WidgetRunnerConfig instead of cfg
        self.service_infos: dict[str, DeviceServiceInfo] = {}
        self.widgets: dict[str, DeviceClientWidget] = {}

        try:
            # Iterate over all devices in the configuration
            for device_id, device_config in cfg.devices.items():
                logger.info(f"Setting up device: {device_id}")

                # Get device class from device config
                device_cls = device_config.get_obj_class()

                # Get widget class from configuration
                if device_id not in cfg.widgets:
                    raise KeyError(f"No widget class configured for device_id: {device_id}")

                # Get service class (default to DeviceService if not specified)
                service_class = cfg.services.get(device_id, DeviceService)

                # Allocate ports for this device service
                rpc_port = _find_free_port()
                pub_port = _find_free_port()

                # Create queue for subprocess communication
                port_queue: Queue = Queue()

                # Create and start subprocess
                process = Process(
                    target=_run_device_service,
                    args=(
                        device_cls,
                        device_config.kwargs,
                        service_class,
                        rpc_port,
                        pub_port,
                        port_queue,
                        logging.root.level,  # Pass current logging level to subprocess
                    ),
                    daemon=True,
                )
                process.start()
                logger.info(f"Started device service process for {device_id} (PID: {process.pid})")

                # Wait for subprocess to be ready
                try:
                    result = port_queue.get(timeout=10.0)
                    if result.get("status") == "error":
                        raise RuntimeError(f"Device service failed to start: {result.get('error')}")
                    if result.get("status") != "ready":
                        raise RuntimeError(f"Unexpected status from device service: {result}")
                except Exception as e:
                    process.terminate()
                    process.join(timeout=2.0)
                    if process.is_alive():
                        process.kill()
                    raise RuntimeError(f"Failed to start device service for {device_id}: {e}") from e

                # Create connection info
                conn = DeviceAddressTCP(host="127.0.0.1", rpc=rpc_port, pub=pub_port)

                # Store service info
                service_info = DeviceServiceInfo(
                    device_id=device_id,
                    conn=conn,
                    process=process,
                )
                self.service_infos[device_id] = service_info
        except Exception:
            # Cleanup on any failure
            logger.exception("Failed to create DeviceWidgetRunner, cleaning up...")
            self._terminate_services()
            raise

    async def _init_clients(self):
        """Initialize device clients and widgets for all services."""
        for device_id, service_info in self.service_infos.items():
            widget_class = self.cfg.widgets[device_id]
            widget = await self._init_client(service_info, widget_class)
            if widget is not None:
                self.widgets[device_id] = widget
            else:
                self._terminate_service_process(service_info)

    @classmethod
    async def _init_client[W: DeviceClientWidget](cls, serv: DeviceServiceInfo, widget_class: type[W]) -> W | None:
        """Initialize a single device client and widget."""
        client: DeviceClient | None = None
        try:
            client = DeviceClient(
                uid=serv.device_id,
                zctx=cls.zctx,
                conn=serv.conn,
            )

            # Device connection is managed by rig node heartbeats
            # If we can get the interface, device is available
            try:
                await client.get_interface()
            except Exception as e:
                logger.warning(f"Failed to connect to device {serv.device_id}: {e}")
                try:
                    await client.close()
                except Exception:
                    logger.exception("Error closing client during cleanup")
                return None

            logger.info(f"Connected to device {serv.device_id}")

            # Create widget
            widget = widget_class(client)

            # Start widget if it has a start method
            if hasattr(widget, "start"):
                await widget.start()

            logger.info(f"Created widget for device {serv.device_id}")
            return widget

        except Exception:
            logger.exception(f"Failed to create widget for {serv.device_id}")

            if client:
                try:
                    await client.close()
                except Exception:
                    logger.exception("Error closing client during cleanup")

            return None

    @staticmethod
    def _terminate_service_process(service_info: DeviceServiceInfo):
        """Terminate a single service process."""
        if service_info.process.is_alive():
            service_info.process.terminate()
            service_info.process.join(timeout=2.0)
            if service_info.process.is_alive():
                service_info.process.kill()

    def _terminate_services(self):
        """Terminate all service processes."""
        for service_info in self.service_infos.values():
            try:
                self._terminate_service_process(service_info)
            except Exception:
                logger.exception("Error terminating process during cleanup")

    def run(self) -> int:
        """Run the Qt application with all device widgets.

        Returns:
            Exit code (0 for success)
        """
        app = QApplication([])
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        window: QMainWindow | None = None

        async def _setup_and_show():
            """Setup widgets and show window."""
            nonlocal window

            try:
                # Initialize clients and widgets
                logger.info(f"Creating widgets for {len(self.cfg.devices)} device(s)")
                await self._init_clients()

                # Create window
                window = QMainWindow()
                window.setWindowTitle(self.cfg.window_title)
                window.setGeometry(100, 100, self.cfg.window_size[0], self.cfg.window_size[1])

                # Create central widget with horizontal layout
                central = QtWidget()
                layout = QHBoxLayout(central)
                window.setCentralWidget(central)

                # Add all widgets to layout
                for device_id, widget in self.widgets.items():
                    layout.addWidget(widget)
                    logger.info(f"Added widget for {device_id} to layout")

                # Show and activate window
                window.show()
                window.raise_()
                window.activateWindow()
                logger.info(f"Window '{self.cfg.window_title}' initialized with {len(self.widgets)} widget(s)")

            except Exception:
                logger.exception("Failed to initialize widgets")
                raise

        # Run the application with qasync
        try:
            with loop:
                loop.run_until_complete(_setup_and_show())
                try:
                    loop.run_forever()
                except KeyboardInterrupt:
                    logger.info("Application interrupted by user")
                finally:
                    logger.info("Application closed, cleaning up...")
                    loop.run_until_complete(self.stop())
        finally:
            pass

        return 0

    async def stop(self) -> None:
        """Stop all device services and cleanup resources."""
        logger.info("Stopping DeviceWidgetRunner")

        # Stop all widgets
        for device_id, widget in self.widgets.items():
            try:
                await widget.stop()
                await widget.client.close()
                logger.info(f"Stopped widget for {device_id}")
            except Exception:
                logger.exception(f"Error stopping widget for {device_id}")

        # Terminate all subprocesses
        self._terminate_services()

        logger.info("DeviceWidgetRunner stopped")
