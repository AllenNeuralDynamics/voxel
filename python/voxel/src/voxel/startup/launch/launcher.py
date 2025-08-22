"""Core launcher functionality for managing instrument lifecycle."""

from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING

from pydantic import ValidationError

from voxel.instrument import Instrument, InstrumentNode, InstrumentNodeType
from voxel.reporting.errors import ErrorInfo, pydantic_to_error_info
from voxel.runtime.io.manager import IOManager
from voxel.runtime.preview.publisher import PreviewManager
from voxel.startup.config import SystemConfig
from voxel.startup.remote.client import RemoteNodeSession

from .context import LaunchContext
from .step import (
    BasicLaunchStepResult,
    InitializeInstrumentNodesResult,
    LaunchStep,
    LaunchStepResult,
    StartRemoteSessionsResult,
)

if TYPE_CHECKING:
    from ..discovery import InstrumentConfigLoader

type LaunchStepFn[T] = Callable[['LaunchContext'], LaunchStepResult[T]]


def launch_step[T](step: LaunchStep):
    """Decorator for pipeline methods.
    - Expects the wrapped method to have signature
         def foo(ctx: LaunchContext) -> LaunchStepResult[...]
    - Enforces ctx.can_advance(step)
    - Calls ctx.advance(result) for you
    - Returns the ctx.
    """

    def decorator(fn: LaunchStepFn[T]) -> Callable[['LaunchContext'], 'LaunchContext']:
        @wraps(fn)
        def wrapper(ctx: LaunchContext) -> LaunchContext:
            # 1) guard ordering
            if not ctx.can_advance(step):
                err = ErrorInfo(
                    name=step,
                    category='invalid_state',
                    message=f'Cannot run step {step.value!r} in state {ctx.latest.step.value!r}',
                )
                result = BasicLaunchStepResult(step=step, errors=[err])
                ctx.advance(result)
                return ctx

            # 2) call the real method to get a LaunchStepResult
            result = fn(ctx)

            # 3) advance ctx
            ctx.advance(result)

            # 4) return ctx for chaining
            return ctx

        return wrapper

    return decorator


class Launcher:
    @staticmethod
    def get_context(loader: 'InstrumentConfigLoader') -> 'LaunchContext':
        return LaunchContext(loader)

    @staticmethod
    def fast_boot(loader: 'InstrumentConfigLoader') -> 'LaunchContext':
        """Fast boot process for launching an instrument.
        - Remote nodes using localhost are started in the background.
        """
        ctx = LaunchContext(loader=loader)
        for method in (
            Launcher.fetch_config,
            Launcher.setup_remote_sessions,
            Launcher.initialize_instrument_nodes,
            Launcher.build_instrument,
        ):
            ctx = method(ctx)
            if not ctx.latest.ok():
                break
        return ctx

    @staticmethod
    @launch_step(LaunchStep.FETCH_CONFIG)
    def fetch_config(ctx: LaunchContext) -> LaunchStepResult:
        """Fetch and validate the system configuration.
        """
        try:
            raw = ctx.loader.get_system_config()
            cfg = SystemConfig.model_validate(raw)
            return BasicLaunchStepResult(step=LaunchStep.FETCH_CONFIG, data=cfg)

        except ValidationError as e:
            errors = pydantic_to_error_info(e, LaunchStep.FETCH_CONFIG)
            return BasicLaunchStepResult(step=LaunchStep.FETCH_CONFIG, errors=list(errors.values()))

        except Exception as e:
            err = ErrorInfo(
                name=LaunchStep.FETCH_CONFIG,
                category='parse_error',
                message=f'Unexpected error parsing system config: {e}',
                details={'exception_type': type(e).__name__},
            )
            return BasicLaunchStepResult(step=LaunchStep.FETCH_CONFIG, errors=[err])

    @staticmethod
    @launch_step(LaunchStep.SETUP_REMOTE_SESSIONS)
    def setup_remote_sessions(ctx: LaunchContext) -> LaunchStepResult[dict[str, 'RemoteNodeSession']]:
        """Start remote servers based on the system configuration."""
        cfg = ctx.system_config
        result = StartRemoteSessionsResult()

        for uid, node in cfg.remote_nodes.items():
            try:
                session = RemoteNodeSession(uid=uid, config=node, preview_relay_opts=cfg.preview_relay_opts)
                result.add_session(uid, session)
            except Exception as exc:
                result.add_error(
                    ErrorInfo(
                        name=LaunchStep.SETUP_REMOTE_SESSIONS,
                        category='server_error',
                        message=f'Failed to start remote session for {uid}: {exc}',
                    ),
                )

        return result

    @staticmethod
    @launch_step(LaunchStep.INITIALIZE_INSTRUMENT_NODES)
    def initialize_instrument_nodes(ctx: LaunchContext) -> LaunchStepResult[dict[str, InstrumentNode]]:
        """Initialize nodes with their devices and runtimes."""
        result = InitializeInstrumentNodesResult()

        preview_manager = PreviewManager(options=ctx.system_config.preview)
        io_manager = IOManager()

        for node_id, node_cfg in ctx.system_config.nodes.items():
            if node_cfg.type == InstrumentNodeType.LOCAL:
                try:
                    node = InstrumentNode(
                        uid=node_id,
                        preview=preview_manager,
                        io_manager=io_manager,
                        device_specs=node_cfg.devices,
                        node_type=node_cfg.type,
                    )
                    result.add_node(node_id, node)
                except Exception as exc:
                    result.add_error(
                        ErrorInfo(
                            name=LaunchStep.INITIALIZE_INSTRUMENT_NODES,
                            category='local_error',
                            message=f'Failed to build local node {node_id}: {exc}',
                        ),
                    )
            session = next((s for s in ctx.remote_sessions.values() if s.uid == node_id), None)
            if session is None:
                result.add_error(
                    ErrorInfo(
                        name=LaunchStep.INITIALIZE_INSTRUMENT_NODES,
                        category='missing_session',
                        message=f'No remote session found for node {node_id}',
                    ),
                )
                continue
            try:
                session.service.configure(node_cfg.devices)
                result.add_node(node_id, session.service.node)
            except Exception as exc:
                result.add_error(
                    ErrorInfo(
                        name=LaunchStep.INITIALIZE_INSTRUMENT_NODES,
                        category='remote_error',
                        message=f'Failed to build remote node {node_id}: {exc}',
                    ),
                )
        return result

    @staticmethod
    @launch_step(LaunchStep.BUILD_INSTRUMENT)
    def build_instrument(ctx: LaunchContext) -> LaunchStepResult[Instrument]:
        instrument = Instrument(
            metadata=ctx.system_config.metadata,
            layout=ctx.system_config.layout,
            nodes=ctx.nodes,
            channels_repository=ctx.loader.get_channel_repository(),
            profiles_repository=ctx.loader.get_profile_repository(),
        )
        return BasicLaunchStepResult(step=LaunchStep.BUILD_INSTRUMENT, data=instrument)
