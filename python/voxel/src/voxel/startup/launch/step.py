from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Self

from voxel.reporting.errors import ErrorInfo, ResultsReportEntry

if TYPE_CHECKING:
    from voxel.instrument import InstrumentNode
    from voxel.startup.remote.client import RemoteNodeSession


class LaunchStep(StrEnum):
    NEW = 'NEW'
    FETCH_CONFIG = 'FETCH CONFIG'
    SETUP_REMOTE_SESSIONS = 'SETUP REMOTE SESSIONS'
    INITIALIZE_INSTRUMENT_NODES = 'INITIALIZE NODES'
    BUILD_INSTRUMENT = 'BUILD INSTRUMENT'


class LaunchReportEntry(ResultsReportEntry):
    name: str
    step: LaunchStep


class LaunchStepResult[T](ABC):
    @property
    @abstractmethod
    def step(self) -> LaunchStep: ...

    @property
    @abstractmethod
    def data(self) -> T | None: ...

    @property
    @abstractmethod
    def errors(self) -> Sequence[ErrorInfo]: ...

    @abstractmethod
    def undo(self) -> None: ...

    @abstractmethod
    def ok(self) -> bool: ...

    @abstractmethod
    def report(self) -> list[LaunchReportEntry]: ...

    def __repr__(self) -> str:
        return f'{self.step.name} - {"OK" if self.ok() else "ERROR"}'


class BasicLaunchStepResult[T](LaunchStepResult[T]):
    def __init__(
        self,
        step: LaunchStep,
        data: T | None = None,
        errors: Sequence[ErrorInfo] | None = None,
        undo_fn: Callable[[Self], None] | None = None,
    ):
        self._step = step
        self._data = data
        self._errors = errors
        self._undo_fn = undo_fn or (lambda _: None)

    @property
    def step(self) -> LaunchStep:
        return self._step

    @property
    def data(self) -> T | None:
        return self._data

    @property
    def errors(self) -> Sequence[ErrorInfo]:
        return self._errors or []

    def undo(self) -> None:
        self._undo_fn(self)

    def ok(self) -> bool:
        return not self._errors

    def report(self) -> list[LaunchReportEntry]:
        results = []
        if self.data is not None:
            results.append(
                LaunchReportEntry(
                    name=self.step,
                    step=self.step,
                    status='OK',
                    category='✓',
                    message='Step completed successfully',
                ),
            )
        results.extend(
            LaunchReportEntry(
                name=error.name,
                step=self.step,
                status='ERROR',
                category=error.category,
                message=error.message,
            )
            for error in self.errors
        )
        return results


class StartRemoteSessionsResult(LaunchStepResult[dict[str, 'RemoteNodeSession']]):
    """Result class for starting remote sessions."""

    def __init__(self):
        self._sessions: dict[str, RemoteNodeSession] = {}
        self._errors: list[ErrorInfo] = []  # Errors encountered during session start

    @property
    def step(self) -> LaunchStep:
        return LaunchStep.SETUP_REMOTE_SESSIONS

    @property
    def data(self) -> dict[str, 'RemoteNodeSession']:
        return self._sessions

    @property
    def errors(self) -> Sequence[ErrorInfo]:
        return self._errors

    def ok(self) -> bool:
        return not self._errors

    def undo(self) -> None:
        """Close all remote sessions."""
        print('Shutting down remote sessions...')
        for session in self._sessions.values():
            session.shutdown()
        self._sessions.clear()
        self._errors.clear()

    def add_session(self, uid: str, session: 'RemoteNodeSession') -> None:
        if uid in self._sessions:
            msg = f'Session with UID {uid} already exists.'
            raise ValueError(msg)
        self._sessions[uid] = session

    def add_error(self, error: ErrorInfo) -> None:
        self._errors.append(error)

    def report(self) -> list[LaunchReportEntry]:
        """Generate a report of the session start results."""
        success = [
            LaunchReportEntry(
                name=uid,
                step=self.step,
                status='OK',
                category='✓',
                message=f'Session {uid} started successfully.',
            )
            for uid in self._sessions
        ]
        errors = [
            LaunchReportEntry(
                name=error.name,
                step=self.step,
                status='ERROR',
                category=error.category,
                message=error.message,
            )
            for error in self._errors
        ]
        return success + errors


class InitializeInstrumentNodesResult(LaunchStepResult[dict[str, 'InstrumentNode']]):
    def __init__(self):
        self._nodes: dict[str, InstrumentNode] = {}
        self._node_errors: list[ErrorInfo] = []  # Errors encountered during node initialization

    @property
    def step(self) -> LaunchStep:
        return LaunchStep.INITIALIZE_INSTRUMENT_NODES

    @property
    def data(self) -> dict[str, 'InstrumentNode']:
        return self._nodes

    def add_node(self, uid: str, node: 'InstrumentNode') -> None:
        if uid in self._nodes:
            msg = f'Node with UID {uid} already exists.'
            raise ValueError(msg)
        self._nodes[uid] = node

    @property
    def errors(self) -> Sequence[ErrorInfo]:
        errors = []
        for node in self._nodes.values():
            errors.extend(node.build_errors.values())
        errors.extend(self._node_errors)
        return errors

    def ok(self) -> bool:
        return not self.errors

    def undo(self) -> None:
        """Undo the initialization by clearing nodes and errors."""
        # TODO: Implement proper undo logic if needed
        # for node in self._nodes.values():
        #     node.shutdown()
        self._nodes.clear()
        self._node_errors.clear()

    def add_error(self, error: ErrorInfo) -> None:
        self._node_errors.append(error)

    def report(self) -> list[LaunchReportEntry]:
        success = []
        success.extend(
            LaunchReportEntry(
                name=device.uid,
                step=self.step,
                status='OK',
                category=node_uid,
                message=f'Device {node_uid}/{device.uid} initialized successfully.',
            )
            for node_uid, node in self._nodes.items()
            for device in node.devices.values()
        )

        errors = [
            LaunchReportEntry(
                name=error.name,
                step=self.step,
                status='ERROR',
                category=error.category,
                message=error.message,
            )
            for error in self.errors
        ]
        return success + errors
