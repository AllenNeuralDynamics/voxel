from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from vidgets.devices.laser.adapter import QtLaserAdapter
from vidgets.devices.laser.power import PowerSetpointInput
from voxel.devices.laser.agent import LaserAgent


class LaserWidget(QWidget):
    def __init__(self, agent: LaserAgent) -> None:
        super().__init__()
        self.agent = agent
        self.adapter = QtLaserAdapter(agent)
        self._input = PowerSetpointInput(binding=self.adapter.power, wavelength=agent.laser.wavelength)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f'Laser - Wavelength: {self.agent.laser.wavelength} nm'))
        layout.addWidget(self._input)
        self.setLayout(layout)


if __name__ == '__main__':
    import asyncio

    from PySide6 import QtAsyncio
    from PySide6.QtWidgets import QApplication, QMainWindow
    from vidgets.devices.laser.adapter import run_adapters
    from voxel.devices.laser.mock import SimulatedLaser
    from voxel.utils.log import VoxelLogging

    class LaserDemoWindow(QMainWindow):
        def __init__(self, agent: LaserAgent) -> None:
            super().__init__()
            self.setWindowTitle('Laser Widget Demo')
            self.setGeometry(100, 100, 500, 200)
            self._wgt = LaserWidget(agent=agent)
            self.setCentralWidget(self._wgt)

        @property
        def adapters(self) -> list[QtLaserAdapter]:
            return [self._wgt.adapter]

    app = QApplication([])

    async def main() -> None:
        VoxelLogging.setup(level='DEBUG')

        # Create driver & agent
        laser = SimulatedLaser(wavelength=560)
        laser.power_setpoint_mw = 50.0
        agent = LaserAgent(laser=laser)

        win = LaserDemoWindow(agent=agent)
        win.show()
        await asyncio.wait_for(run_adapters(win.adapters, app.lastWindowClosed), timeout=None)

    QtAsyncio.run(main())
