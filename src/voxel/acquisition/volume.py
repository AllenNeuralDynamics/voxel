import math
from collections.abc import Callable

from voxel.utils.vec import Plane, Vec3D
from voxel.utils.log_config import get_logger


class VolumeBoundaryError(Exception):
    def __init__(self, message: str, min_value: float, max_value: float):
        super().__init__(message)
        self.min_value = min_value
        self.max_value = max_value

    def __str__(self):
        return f"{self.args[0]} (min: {self.min_value}, max: {self.max_value})"


class Volume:
    def __init__(self, min_corner: Vec3D, max_corner: Vec3D, step_size: float):
        self.log = get_logger(self.__class__.__name__)
        self._min_corner = min_corner
        self._max_corner = max_corner
        self._step_size = step_size
        self._observers: list[Callable[[], None]] = []

    def __repr__(self):
        return f"Volume(min_corner={self.min_corner}, max_corner={self.max_corner}, step_size={self.step_size})"

    def add_observer(self, callback: Callable[[], None]):
        self._observers.append(callback)

    def _notify_observers(self):
        for callback in self._observers:
            callback()

    @property
    def min_corner(self) -> Vec3D[float]:
        return self._min_corner

    @min_corner.setter
    def min_corner(self, min_corner: Vec3D):
        self._min_corner = min_corner
        self._notify_observers()

    @property
    def max_corner(self) -> Vec3D[float]:
        return self._max_corner

    @max_corner.setter
    def max_corner(self, max_corner: Vec3D):
        self._max_corner = max_corner
        self._notify_observers()

    @property
    def step_size(self) -> float:
        return self._step_size

    @step_size.setter
    def step_size(self, step_size: float) -> None:
        self._step_size = step_size
        self.size.z = math.ceil(self.size.z / step_size) * step_size
        self._notify_observers()

    @property
    def size(self) -> Vec3D[float]:
        return Vec3D(
            self.max_corner.x - self.min_corner.x,
            self.max_corner.y - self.min_corner.y,
            self.max_corner.z - self.min_corner.z,
        )

    @property
    def center(self) -> Vec3D[float]:
        return Vec3D(
            (self.min_corner.x + self.max_corner.x) / 2,
            (self.min_corner.y + self.max_corner.y) / 2,
            (self.min_corner.z + self.max_corner.z) / 2,
        )

    def contains(self, point: Vec3D) -> bool:
        return (
            self.min_corner.x <= point.x <= self.max_corner.x
            and self.min_corner.y <= point.y <= self.max_corner.y
            and self.min_corner.z <= point.z <= self.max_corner.z
        )

    def intersects(self, other: "Volume") -> bool:
        return (
            self.min_corner.x <= other.max_corner.x
            and self.max_corner.x >= other.min_corner.x
            and self.min_corner.y <= other.max_corner.y
            and self.max_corner.y >= other.min_corner.y
            and self.min_corner.z <= other.max_corner.z
            and self.max_corner.z >= other.min_corner.z
        )

    def _set_boundary(self, attribute: str, plane: Plane):
        current_min = getattr(self.min_corner, attribute)
        current_max = getattr(self.max_corner, attribute)
        new_value = getattr(plane.min_corner, attribute)

        if attribute.startswith("min"):
            if new_value > current_max:
                raise VolumeBoundaryError(
                    f"{attribute} cannot be greater than current max_{attribute}", new_value, current_max
                )
            setattr(self.min_corner, attribute, new_value)
        else:  # max
            if new_value < current_min:
                raise VolumeBoundaryError(
                    f"{attribute} cannot be less than current min_{attribute}", current_min, new_value
                )
            setattr(self.max_corner, attribute, new_value)

        self._notify_observers()

    @property
    def min_x(self):
        return self.min_corner.x

    @min_x.setter
    def min_x(self, plane: Plane):
        self._set_boundary("x", plane)

    @property
    def max_x(self):
        return self.max_corner.x

    @max_x.setter
    def max_x(self, plane: Plane):
        self._set_boundary("x", plane)

    @property
    def min_y(self):
        return self.min_corner.y

    @min_y.setter
    def min_y(self, plane: Plane):
        self._set_boundary("y", plane)

    @property
    def max_y(self):
        return self.max_corner.y

    @max_y.setter
    def max_y(self, plane: Plane):
        self._set_boundary("y", plane)

    @property
    def min_z(self):
        return self.min_corner.z

    @min_z.setter
    def min_z(self, plane: Plane):
        self._set_boundary("z", plane)
        valid_min_z = self.max_corner.z - (
            math.ceil((self.max_corner.z - self.min_corner.z) / self.step_size) * self.step_size
        )
        self.min_corner.z = valid_min_z

    @property
    def max_z(self):
        return self.max_corner.z

    @max_z.setter
    def max_z(self, plane: Plane):
        self._set_boundary("z", plane)
        valid_max_z = (
            math.ceil((self.max_corner.z - self.min_corner.z) / self.step_size) * self.step_size
        ) + self.min_corner.z
        self.max_corner.z = valid_max_z
