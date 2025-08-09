from typing import TYPE_CHECKING, Any

from tabulate import tabulate
from voxel.devices import VoxelDevice

from .step import LaunchReportEntry, LaunchStep, LaunchStepResult, BasicLaunchStepResult

if TYPE_CHECKING:
    from voxel.instrument import InstrumentNode
    from voxel.instrument import Instrument
    from voxel.startup.config import SystemConfig
    from voxel.startup.remote.client import RemoteNodeSession
    from voxel.startup.discovery import InstrumentConfigLoader


class LaunchContext:
    _IDEMPOTENT: set[LaunchStep] = {LaunchStep.NEW, LaunchStep.FETCH_CONFIG}
    _ORDER: list[LaunchStep] = [
        LaunchStep.NEW,
        LaunchStep.FETCH_CONFIG,
        LaunchStep.SETUP_REMOTE_SESSIONS,
        LaunchStep.INITIALIZE_INSTRUMENT_NODES,
        LaunchStep.BUILD_INSTRUMENT,
    ]

    def __init__(self, loader: "InstrumentConfigLoader"):
        self._loader = loader
        self._results: dict[LaunchStep, LaunchStepResult[Any] | None] = {
            LaunchStep.NEW: BasicLaunchStepResult(step=LaunchStep.NEW, data=None),
            LaunchStep.FETCH_CONFIG: None,
            LaunchStep.SETUP_REMOTE_SESSIONS: None,
            LaunchStep.INITIALIZE_INSTRUMENT_NODES: None,
            LaunchStep.BUILD_INSTRUMENT: None,
        }

        self._current_step: LaunchStep = LaunchStep.NEW

    @property
    def uid(self) -> str:
        return self._loader.instrument_id

    @property
    def loader(self) -> "InstrumentConfigLoader":
        """Get the instrument config loader."""
        return self._loader

    @property
    def latest(self) -> LaunchStepResult[Any]:
        """Get the latest step result, if any."""
        current = self._results.get(self._current_step)
        # # Fallback for unexpected state TODO: handle this better
        current = current or BasicLaunchStepResult(step=LaunchStep.NEW, data=None)
        return current

    def can_advance(self, next_step: LaunchStep) -> bool:
        # find indices, treating NEW as “just before 0”
        try:
            curr_idx = self._ORDER.index(self._current_step)
        except ValueError:
            curr_idx = -1
        try:
            next_idx = self._ORDER.index(next_step)
        except ValueError:
            return False  # unknown step

        delta = next_idx - curr_idx
        # allow forward by one, or re‑run idempotent
        return (delta == 1) or (delta == 0 and next_step in self._IDEMPOTENT)

    def advance(self, result: LaunchStepResult[Any]) -> None:
        # 1) find our slot
        if result.step not in self._results:
            raise ValueError(f"No context slot for step {result.step}")
        # 2) guard ordering
        if not self.can_advance(result.step):
            raise ValueError(f"Cannot jump from {self._current_step.name} to {result.step.name}")
        # 3) rollback downstream regardless of success or failure
        for later_step in self._ORDER[self._ORDER.index(result.step) + 1 :]:
            if later_step in self._results:
                old = self._results[later_step]
                if isinstance(old, BasicLaunchStepResult):
                    old.undo()
                self._results[later_step] = None
        # 4) record this step’s result
        self._results[result.step] = result
        self._current_step = result.step

    def report(self) -> list["LaunchReportEntry"]:
        """Get a report of the current context state."""
        report = []
        for result in self._results.values():
            if result is None:
                continue
            try:
                report += result.report()
            except Exception as e:
                print(f"Error generating report for {result.step.name}: {e}")
        return report

    def table(self, tablefmt: str = "github") -> str:
        """Get a formatted table report of the current context state."""
        report = self.report()
        if not report:
            return "No steps executed yet."
        return tabulate(
            [[entry.name, entry.step, entry.status, entry.category, entry.message] for entry in report],
            headers=["Name", "Step", "Status", "Category", "Message"],
            tablefmt=tablefmt,
        )

    @property
    def system_config(self) -> "SystemConfig":
        """Get the current system configuration, if available.
        :return: SystemConfig instance
        :rtype: SystemConfig
        :raises: RuntimeError if no configuration has been set
        """
        return self._get_data(LaunchStep.FETCH_CONFIG, "System configuration has not been set yet.")

    @property
    def nodes(self) -> dict[str, "InstrumentNode"]:
        """Get the current instrument nodes, if available.
        :return: Dictionary of node names to InstrumentNode instances
        :rtype: dict[str, InstrumentNode]
        :raises: RuntimeError if nodes have not been initialized
        """
        return self._get_data(LaunchStep.INITIALIZE_INSTRUMENT_NODES, "Instrument nodes not initialized yet.")

    @property
    def devices(self) -> dict[str, VoxelDevice]:
        """Get the current devices available in the instrument.
        :return: Dictionary of device UIDs to VoxelDevice instances
        :rtype: dict[str, VoxelDevice]
        :raises: RuntimeError if devices have not been initialized
        """
        nodes = self.nodes
        if not nodes:
            raise RuntimeError("No instrument nodes available.")
        devices = {}
        for node in nodes.values():
            devices.update(node.devices)
        return devices

    @property
    def remote_sessions(self) -> dict[str, "RemoteNodeSession"]:
        """Get the current remote processes, if available.
        :return: Dictionary of worker UIDs to WorkerSession instances
        :rtype: dict[str, WorkerSession]
        :raises: RuntimeError if remote processes have not been initialized
        """
        return self._get_data(LaunchStep.SETUP_REMOTE_SESSIONS, "Remote processes not started yet.")

    @property
    def instrument(self) -> "Instrument":
        """Get the current instrument, if available.
        :return: Instrument instance
        :rtype: Instrument
        :raises: RuntimeError if instrument has not been initialized
        """
        return self._get_data(LaunchStep.BUILD_INSTRUMENT, "Instrument not built yet.")

    def _get_data(self, step: LaunchStep, err_msg: str = "Data not available") -> Any:
        """Helper to get data from a specific step, raising if not available."""
        result = self._results.get(step)
        if result is None or result.data is None:
            raise RuntimeError(err_msg)
        return result.data
