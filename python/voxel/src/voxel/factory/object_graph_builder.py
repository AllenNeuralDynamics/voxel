from typing import Any

from voxel.reporting.errors import ErrorInfo

from .models import SpinnerErrorType, SpinnerResults
from .object_builder import DEFAULT_UID_PARAMS, build_object
from .specs import BuildSpec, BuildSpecs


class ObjectGraphBuilder[T: object]:
    """Builds collections of objects from a dictionary of BuildSpecs.

    This builder uses a recursive approach with explicit state management to
    resolve dependency graphs. The builder instance is reusable for multiple
    build jobs.
    """

    def __init__(self, *, base_class: type[T] = object, uid_params: set[str] | None = None):
        """Initialize the graph builder.
        :param: base_class: Base class that all built objects must inherit from
        :param uid_params: Parameter names to auto-inject with the object key.
        """
        self._base_class = base_class
        self._uid_params = (uid_params or set()) | DEFAULT_UID_PARAMS

        # Internal state is defined here but managed per-build
        self._built: dict[str, T] = {}
        self._errors: dict[str, ErrorInfo] = {}
        self._building: set[str] = set()

    def build(self, specs: BuildSpecs) -> SpinnerResults[T]:
        """Build all objects in the specification collection.

        Args:
            specs: Dictionary mapping object names to their build specifications.

        Returns:
            SpinnerResults containing built objects and errors.

        """
        # Clear state to ensure the instance is clean for each build run
        self._built.clear()
        self._errors.clear()
        self._building.clear()

        for name in specs:
            # Process each spec only if it hasn't already been handled
            if name not in self._built and name not in self._errors:
                self._build_one(name, specs)

        return SpinnerResults(items=self._built, errors=self._errors)

    def _build_one(self, name: str, specs: BuildSpecs) -> T | ErrorInfo:
        """Build a single object, detecting circular dependencies."""
        if name in self._built:
            return self._built[name]

        if name in self._building:
            error = ErrorInfo(
                name=name,
                category=SpinnerErrorType.DEPENDENCY,
                message=f"Object '{name}' is part of a circular dependency",
            )
            # Store the error and return immediately
            self._errors[name] = error
            return error

        self._building.add(name)
        try:
            # Pass the full `specs` dict down to the next level
            result = self._perform_build(name, specs[name], specs)

            if isinstance(result, ErrorInfo):
                self._errors[name] = result
            else:
                self._built[name] = result
            return result
        finally:
            self._building.discard(name)

    def _perform_build(self, name: str, spec: BuildSpec, specs: BuildSpecs) -> T | ErrorInfo:
        """Resolve dependencies and orchestrate the build of a single object."""
        dependencies_needed = self._extract_dependencies(spec, name, specs)

        resolved_dependencies = {}
        for dep_name in dependencies_needed:
            # If a dependency has already failed, this object must also fail.
            if dep_name in self._errors:
                return ErrorInfo(
                    name=name,
                    category=SpinnerErrorType.DEPENDENCY,
                    message=f"Dependency '{dep_name}' failed to build",
                    details=self._errors[dep_name].model_dump(),
                )

            # Build the dependency if it's not already built.
            dep_result = self._build_one(dep_name, specs)
            if isinstance(dep_result, ErrorInfo):
                # The error is already stored by the _build_one call
                return ErrorInfo(
                    name=name,
                    category=SpinnerErrorType.DEPENDENCY,
                    message=f"Dependency '{dep_name}' failed",
                    details=dep_result.model_dump(),
                )
            resolved_dependencies[dep_name] = dep_result

        return build_object(
            spec,
            dependencies=resolved_dependencies,
            base=self._base_class,
            uid_params=self._uid_params,
            uid=name,
        )

    def _extract_dependencies(self, spec: BuildSpec, object_uid: str, specs: BuildSpecs) -> set[str]:
        """Extract string references from args/kwargs that match other spec keys."""
        dependencies = set()

        def _scan_value(value: Any) -> None:
            # A dependency is a string that exists as a key in the main specs dict
            if isinstance(value, str) and value in specs and value != object_uid:
                dependencies.add(value)
            elif isinstance(value, list):
                for item in value:
                    _scan_value(item)
            elif isinstance(value, dict):
                for v in value.values():
                    _scan_value(v)

        for arg in spec.args:
            _scan_value(arg)

        for value in spec.kwargs.values():
            _scan_value(value)

        return dependencies


def build_object_graph[T](
    specs: BuildSpecs,
    base_class: type[T],
    id_params: set[str] | None = None,
) -> SpinnerResults[T]:
    """Build a graph of objects from the specification collection."""
    return ObjectGraphBuilder(base_class=base_class, uid_params=id_params).build(specs)
