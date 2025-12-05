# import asyncio
# import contextlib
# from collections.abc import Iterable
# from typing import Protocol, Self

# from PySide6.QtCore import QObject, Signal, Slot
# from voxel.devices.laser.agent import LaserAgent
# from voxel.utils.descriptors.deliminated import DeliminatedFloat

# from spim_widgets.ui.input.binding import FieldBinder


# class QtLaserAdapter(QObject):
#     state_changed = Signal(object)  # LaserState
#     fault = Signal(str)

#     def __init__(self, agent: LaserAgent, parent: QObject | None = None) -> None:
#         super().__init__(parent)
#         self._agent = agent
#         self._pump_task: asyncio.Task | None = None

#         # Power setpoint: read DeliminatedFloat, write float (mW)
#         self.power = FieldBinder[DeliminatedFloat, float](
#             writer=lambda v: self.setPower(float(v)),
#             debounce_ms=150,
#             settle_ms=150,
#             parent=self,
#         )
#         self.state_changed.connect(lambda st: self.power.update(st.power_setpoint))

#         # Enable: read bool, write bool
#         self.enabled = FieldBinder[bool, bool](
#             writer=lambda v: self.setEnable(bool(v)),
#             debounce_ms=0,  # toggles can be immediate
#             settle_ms=250,
#             parent=self,
#         )
#         self.state_changed.connect(lambda st: self.enabled.update(st.enabled))

#     # ----- lifecycle -----
#     async def start(self) -> None:
#         await self._agent.start()
#         self._pump_task = asyncio.create_task(self._pump_states(), name="laser-pump")

#     async def stop(self) -> None:
#         if self._pump_task:
#             self._pump_task.cancel()
#             with contextlib.suppress(asyncio.CancelledError):
#                 await self._pump_task
#             self._pump_task = None
#         await self._agent.stop()

#     async def __aenter__(self) -> Self:
#         await self.start()
#         return self

#     async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
#         await self.stop()

#     async def _pump_states(self) -> None:
#         try:
#             async for st in self._agent.states():
#                 self.state_changed.emit(st)
#         except Exception as e:  # noqa: BLE001
#             self.fault.emit(f"{e!r}")

#     # ----- command slots (thin) -----
#     @Slot(float)
#     def setPower(self, mw: float) -> None:
#         self._agent.set_power(power_mw=mw)

#     @Slot(bool)
#     def setEnable(self, on: bool) -> None:
#         self._agent.set_enable(on=on)


# class AsyncAdapter(Protocol):
#     async def __aenter__(self) -> Self: ...
#     async def __aexit__(self, exc_type, exc_val, exc_tb) -> None: ...


# def wait_signal(signal) -> asyncio.Future:
#     fut = asyncio.Future()

#     def _handler(*args):
#         if not fut.done():
#             fut.set_result(args)

#     signal.connect(_handler)

#     def _disconnect(_):
#         with contextlib.suppress(Exception):
#             signal.disconnect(_handler)

#     fut.add_done_callback(_disconnect)
#     return fut


# async def run_adapters(adapters: Iterable[AsyncAdapter], stop_signal) -> None:
#     """Enter all async context managers, wait for signal, then cleanly exit."""
#     async with contextlib.AsyncExitStack() as stack:
#         for cm in adapters:
#             await stack.enter_async_context(cm)
#         await wait_signal(stop_signal)
