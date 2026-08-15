# vxlib

Small shared building blocks used across the Voxel workspace. The current public surface includes reactive
primitives, schema and vector types, YAML/JSON helpers, logging setup, and general utilities.

Keep domain behavior in the package that owns it; `vxlib` is for dependencies that are genuinely shared. Its API is
still evolving, so use the exports from `vxlib` rather than importing private modules.
