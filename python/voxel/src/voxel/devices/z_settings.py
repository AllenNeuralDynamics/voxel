import bisect
from functools import total_ordering
from typing import Self

import numpy as np
from pydantic import BaseModel, RootModel, model_validator


@total_ordering
class ZPoint(BaseModel):
    z: float
    value: float
    model_config = {"frozen": True}

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ZPoint):
            return NotImplemented
        return (self.z, self.value) == (other.z, other.value)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ZPoint):
            return NotImplemented
        if self.z == other.z:
            return False
        return self.z < other.z


class ZSetting(RootModel[list[ZPoint]]):
    @property
    def points(self) -> list[ZPoint]:
        return self.root

    @model_validator(mode="after")
    def check_and_sort_points(self) -> Self:
        if not self.root:
            raise ValueError("ZSetting points cannot be empty")
        self.root.sort()
        return self

    def __setitem__(self, z: float, value: float) -> None:
        self.add_point(ZPoint(z=z, value=value))

    def __getitem__(self, z: float) -> float:
        return self.get_value(z)

    def __delitem__(self, z: float) -> None:
        self.remove_point(z)

    @property
    def z_coords(self) -> list[float]:
        return [p.z for p in self.points]

    def add_point(self, point: ZPoint) -> None:
        for i, p in enumerate(self.points):
            if p.z == point.z:
                self.points[i] = point
                return
        bisect.insort_left(self.points, point)

    def merge(self, other: Self) -> None:
        """
        Merges another ZSetting into this one.
        Points from the other setting are added to this one.
        If a point with the same z-coordinate exists, it is replaced.
        """
        for point in other.points:
            self.add_point(point)

    def get_value(self, z: float | None = None) -> float:
        """
        Retrieves the value at a given z-coordinate.
        - If z is None, it returns the value of the point with the median z-coordinate.
          (Or, if values are non-numeric, the value of the middle point by index).
        - If only one point exists, its value is returned.
        - If an exact z-match exists, that point's value is returned.
        - For numeric values, interpolates if no exact match.
        - For non-numeric values, returns the value of the nearest point with z_point <= z.
          If no such point, returns the value of the first point (smallest z).
        """
        if not self.points:
            raise ValueError("ZSetting has no points from which to get a value.")

        # if only one point is present, return its value
        if len(self.points) == 1:
            return self.points[0].value

        # if z is not provided, set it to the middle point
        z = z if z is not None else self.points[len(self.points) // 2].z

        # if an exact match is found, return the value
        for point in self.points:
            if point.z == z:
                return point.value

        setting_vals_np = np.array([p.value for p in self.points], dtype=float)
        return float(np.interp(z, self.z_coords, setting_vals_np).item())

    def remove_point(self, z: float) -> None:
        """
        Removes a point with the specified z-coordinate unless it is the only point.
        Raises IndexError if the point is the only one in the list.
        Raises ValueError if no such point exists.
        """
        if len(self.points) == 1:
            raise IndexError("Cannot remove the only point in the ZSetting.")
        for i, p in enumerate(self.points):
            if p.z == z:
                del self.points[i]
                return
        raise ValueError(f"No point found with z-coordinate {z}.")


type ZSettingsCollection = dict[str, ZSetting]  # prop_name -> ZSetting for that property


def merge_z_settings_collections(settings1: ZSettingsCollection, settings2: ZSettingsCollection) -> ZSettingsCollection:
    merged = settings1.copy()
    for key, value in settings2.items():
        if key in merged:
            merged[key].merge(value)
        else:
            merged[key] = value
    return merged
