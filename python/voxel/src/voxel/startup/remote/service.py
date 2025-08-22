import copy
from typing import TYPE_CHECKING

import rpyc
from pydantic import BaseModel

from voxel.instrument import InstrumentNode, InstrumentNodeType
from voxel.runtime.io import IOManager
from voxel.runtime.preview.models import PreviewRelayOptions
from voxel.runtime.preview.publisher import PreviewFrameRelay
from voxel.utils.log import VoxelLogging

if TYPE_CHECKING:
    from voxel.factory import BuildSpecs


def remote_full_copy[T: BaseModel](model: T) -> T:
    model_data = model.model_dump()
    model_data_copy = copy.deepcopy(model_data)
    return model.__class__.model_validate(model_data_copy)


def remote_full_copy_jsonify[T: BaseModel](model: T) -> T:
    return model.__class__.model_validate_json(model.model_dump_json())


def remote_full_copy_dict[T: BaseModel](data: dict[str, T]) -> dict[str, T]:
    return {k: remote_full_copy(v) for k, v in data.items()}


class RemoteNodeService(rpyc.SlaveService):
    def __init__(self, uid: str):
        self._uid: str = uid
        self._log = VoxelLogging.get_logger(obj=self)
        self._active_connection: rpyc.Connection | None = None
        self._preview_publisher: PreviewFrameRelay | None = None
        self._io_manager = IOManager()
        self._node: InstrumentNode | None = None
        super().__init__()

    def on_connect(self, conn):
        if self._active_connection is not None:
            self._log.warning('Refusing new connection: already connected to a client.')
            conn.close()
            return
        self._active_connection = conn
        super().on_connect(conn)
        self._log.info(f'Client {id(conn)} connected.')

    def on_disconnect(self, conn):
        super().on_disconnect(conn)
        if self._active_connection == conn:
            self._log.info(f'Client {id(conn)} disconnected.')
            self._active_connection = None

    def initialize(self, options: PreviewRelayOptions):
        if self._preview_publisher:
            self._preview_publisher.close()
        self._preview_publisher = PreviewFrameRelay(
            options=options, logger=VoxelLogging.get_logger(f'PreviewRelay{self._uid}'),
        )

    def configure(self, device_specs: 'BuildSpecs'):
        if self._preview_publisher is None:
            raise RuntimeError('RemoteNodeService has not been initialized. Call initialize() first.')
        specs_copy = remote_full_copy_dict(device_specs)
        self._node = InstrumentNode(
            uid=self._uid,
            device_specs=specs_copy,
            preview=self._preview_publisher,
            io_manager=self._io_manager,
            node_type=InstrumentNodeType.REMOTE,
        )

    @property
    def node(self) -> InstrumentNode:
        if self._node is None:
            raise RuntimeError('Remote node has not been initialized.')
        return self._node

    def shutdown(self) -> None:
        """Shutdown the remote node service."""
        if self._preview_publisher:
            self._preview_publisher.close()
            self._preview_publisher = None
