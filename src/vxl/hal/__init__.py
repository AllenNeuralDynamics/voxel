"""Microscope hardware topology and runtime."""

from .core import HAL, Stage
from .errors import HALError, HALStartupError, Violation, ViolationLoc, assignment_violations
from .topology import (
    DetectionAssembly,
    DiscreteAxisPositions,
    HardwareTopology,
    IlluminationAssembly,
    OpticalAssembly,
    OpticalRouteDefinition,
    OpticalRouting,
    RouteByDimension,
    StageAxes,
)

__all__ = [
    "HAL",
    "DetectionAssembly",
    "DiscreteAxisPositions",
    "HALError",
    "HALStartupError",
    "HardwareTopology",
    "IlluminationAssembly",
    "OpticalAssembly",
    "OpticalRouteDefinition",
    "OpticalRouting",
    "RouteByDimension",
    "Stage",
    "StageAxes",
    "Violation",
    "ViolationLoc",
    "assignment_violations",
]
