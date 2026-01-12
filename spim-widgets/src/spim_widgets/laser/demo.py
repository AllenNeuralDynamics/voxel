# from voxel.devices.laser.drivers.genesis_mx import GenesisMXLaser

# from spim_widgets.laser.widget import LaserWidget

# if __name__ == "__main__":
#     import asyncio

#     from PySide6 import QtAsyncio
#     from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QVBoxLayout, QWidget
#     from voxel.devices.laser.controller import LaserAgent
#     from voxel.devices.laser.mock import SimulatedLaser
#     from voxel.utils.log import VoxelLogging

#     from spim_widgets.laser.adapter import QtLaserAdapter, run_adapters

#     class LaserDemoWindow(QMainWindow):
#         def __init__(self, agents: dict[str, LaserAgent]) -> None:
#             super().__init__()
#             self.setWindowTitle("Laser Widget Demo")
#             self.setGeometry(100, 100, 800, 600)

#             self._wgts: dict[str, LaserWidget] = {}

#             container = QWidget()
#             h_layout = QHBoxLayout(container)
#             h_layout.addStretch()

#             v_layout = QVBoxLayout()
#             for name, controller in agents.items():
#                 wgt = LaserWidget(controller=controller)
#                 self._wgts[name] = wgt
#                 v_layout.addWidget(wgt)
#             v_layout.addStretch()

#             h_layout.addLayout(v_layout)
#             h_layout.addStretch()
#             self.setCentralWidget(container)

#         @property
#         def adapters(self) -> list[QtLaserAdapter]:
#             return [wgt.adapter for wgt in self._wgts.values()]

#     app = QApplication([])

#     async def main() -> None:
#         VoxelLogging.setup(level="DEBUG")

#         lasers = {
#             "laser_1": SimulatedLaser(wavelength=488, name="simulated_laser_1"),
#             "laser_2": SimulatedLaser(wavelength=560, name="simulated_laser_2"),
#             "laser_3": SimulatedLaser(wavelength=639, name="simulated_laser_3"),
#             "genesis_1": GenesisMXLaser("genesis_1", "A679409EM263", wavelength=488, max_power_mw=100),
#         }

#         for laser in lasers.values():
#             laser.power_setpoint_mw = 50.0

#         agents = {name: LaserAgent(laser=laser) for name, laser in lasers.items()}

#         win = LaserDemoWindow(agents=agents)
#         win.show()
#         await asyncio.wait_for(run_adapters(win.adapters, app.lastWindowClosed), timeout=None)

#     QtAsyncio.run(main())
