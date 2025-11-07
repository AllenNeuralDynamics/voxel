from abc import abstractmethod

from ome_zarr_writer.types import Vec2D

from pyrig import Device, DeviceType
from spim_rig.camera.roi import ROI, ROIAlignmentPolicy, ROIConstraints, ROIPlacementError, coerce_roi


class SpimCamera(Device):
    __DEVICE_TYPE__ = DeviceType.CAMERA
    roi_alignment_policy: ROIAlignmentPolicy = ROIAlignmentPolicy.ALIGN

    # ------------------------------ ROI Configuration ------------------------------------
    @property
    @abstractmethod
    def sensor_size_px(self) -> Vec2D[int]:
        """Get the size of the camera sensor in pixels."""

    @property
    def roi(self) -> ROI:
        """Get the current ROI configuration."""
        return self._do_get_roi()

    @roi.setter
    def roi(self, roi: ROI) -> None:
        """Set the current ROI configuration.

        Raises:
            ROIPlacementError: If the ROI could not be set due to policy violations.
        """
        eff = coerce_roi(roi, caps=self.roi_constraints, policy=self.roi_alignment_policy)
        self._do_set_roi(eff)

    @abstractmethod
    def _do_get_roi(self) -> ROI: ...

    @abstractmethod
    def _do_set_roi(self, roi: ROI) -> None: ...

    @property
    @abstractmethod
    def roi_constraints(self) -> ROIConstraints:
        """Get the constraints of the ROI."""
