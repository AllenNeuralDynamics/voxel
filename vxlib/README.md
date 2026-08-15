# vxlib

`vxlib` provides the domain-neutral foundations shared by packages in the Voxel workspace. Its scope includes reactive
state, lifecycle callbacks, immutable schema models, numeric and quantity types, vector utilities, S3 connection
models, polling, and update coalescing.

The package is intentionally small and carries no microscopy or application-level behavior. Public concepts are
defined by focused modules such as `vxlib.reactivity`, `vxlib.schema`, and `vxlib.quantity`; the package root does not
serve as a flat re-exported API.
