import threading
import time

from tigerasi.tiger_controller import TigerController as TigerBox

UPDATE_RATE_HZ = 1.0


class TigerController(TigerBox):
    """
    Controller for the ASI Tiger stage.
    """

    def __init__(self, com_port: str) -> None:
        """
        Initialize the TigerController object.

        :param com_port: COM port for the controller
        :type com_port: str
        """
        super().__init__(com_port)
        for axis in self.ordered_axes:
            self.log.info(f"resetting ring buffer for axis={axis.upper()}")
            # clear ring buffer incase there are persistent values
            self.reset_ring_buffer(axis=axis.upper())
        self._position_mm_updater = PositionUpdater(self)

    def get_position_mm(self) -> float:
        """
        Get the current position in millimeters.

        :return: Current position in millimeters
        :rtype: float
        """
        return self._position_mm_updater._position_mm

    def close(self) -> None:
        """
        Close the TigerController.
        """
        # stop the updating thread
        print("closing")
        self._position_mm_updater.close()
        self.ser.close()


class PositionUpdater:
    """
    Class for continuously updating the stage positions in millimeters.
    """

    def __init__(self, tigerbox) -> None:
        """
        Initialize the TigerController object.

        :param tigerbox: TigerController object.
        :type tigerbox: TigerContoller
        """
        self._tigerbox = tigerbox
        self._get_positions = True
        self._position_mm = 0  # internal cache of position values
        self._position_mm_updater = threading.Thread(target=self._position_mm_updater)
        self._position_mm_updater.start()

    def _position_mm_updater(self) -> None:
        """
        Thread to continuously get the position in millimeters for all axes.
        """
        # get position for all axes on some time interval
        # returns a dict of {hardware axes: positions}
        while self._get_positions:
            with threading.RLock():
                self._position_mm = self._tigerbox.get_position(*self._tigerbox.ordered_axes)
            time.sleep(1.0 / UPDATE_RATE_HZ)

    def close(self) -> None:
        """
        Close the position updater class.
        """
        self._get_positions = False
