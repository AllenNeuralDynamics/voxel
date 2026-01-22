from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)
from spim_rig.axes.discrete import DiscreteAxis

from spim_widgets.filter_wheel.graphic import WheelGraphic


class FilterWheelWidget(QWidget):
    def __init__(self, filter_wheel: DiscreteAxis, hues: dict[str, int | float] | None = None) -> None:
        super().__init__()
        self._hues: dict[str, float | int] = {
            "655LP": 0,  # red (0 degrees)
            "620/60BP": 120,  # green (120 degrees)
            "500LP": 230,  # blue (240 degrees)
        }
        if hues is not None:
            self._hues.update(hues)

        self._fw = filter_wheel

        self._graphic = WheelGraphic(
            num_slots=self._fw.slot_count,
            assignments=self._fw.labels,
            hue_mapping=self._hues,
        )
        self._graphic.selected_changed.connect(lambda: self._update_filter())
        self._status_label = QLabel("Hover over circles to see labels, click to select")

        layout = QVBoxLayout()
        layout.addWidget(self._graphic)
        layout.addLayout(self._create_controls_ui())
        self.setLayout(layout)

    def _update_filter(self) -> None:
        if (slot := self._graphic.selected_slot) is not None:
            self._fw.move(slot)

    def _create_controls_ui(self) -> QVBoxLayout:
        # Create controls
        controls_layout = QVBoxLayout()
        controls_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # - Row 1 - Step controls
        left_btn = QPushButton("◀")
        left_btn.setToolTip("Spin left")
        left_btn.clicked.connect(self._graphic.step_to_next)

        right_btn = QPushButton("▶")
        right_btn.setToolTip("Spin right")
        right_btn.clicked.connect(self._graphic.step_to_previous)

        row_1_layout = QHBoxLayout()
        row_1_layout.addWidget(left_btn)
        row_1_layout.addStretch()
        row_1_layout.addWidget(right_btn)

        # - Row 2 - Reset jand Status
        reset_btn = QPushButton("⟳")
        reset_btn.setToolTip("Reset wheel rotation")
        reset_btn.clicked.connect(self._graphic.reset_rotation)

        row_2_layout = QHBoxLayout()
        row_2_layout.addWidget(self._status_label)
        row_2_layout.addStretch()
        row_2_layout.addWidget(reset_btn)

        controls_layout.addLayout(row_1_layout)
        controls_layout.addLayout(row_2_layout)

        return controls_layout


if __name__ == "__main__":
    import logging
    import sys

    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow,
    )
    from spim_drivers.axes.simulated import SimulatedDiscreteAxis

    from pyrig.utils import configure_logging

    class FilterWheelWidgetDemo(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Filter Wheel Widget Demo")
            self.setGeometry(100, 100, 800, 600)

            # Create main widget and layout
            main_widget = QWidget()
            self.setCentralWidget(main_widget)
            layout = QVBoxLayout(main_widget)

            fw = SimulatedDiscreteAxis(
                uid="simulated-filter_wheel",
                slots={1: "655LP", 2: "620/60BP", 3: "500LP"},
                slot_count=6,
            )

            fw_wgt = FilterWheelWidget(fw)
            layout.addWidget(fw_wgt)

    configure_logging(level=logging.DEBUG)

    app = QApplication(sys.argv)
    app.setWindowIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
    demo = FilterWheelWidgetDemo()
    demo.show()
    sys.exit(app.exec())
