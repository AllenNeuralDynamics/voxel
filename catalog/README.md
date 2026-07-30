# vxl-catalog

`vxl-catalog` defines the durable, storage-independent description of Voxel
acquisitions. It contains acquisition manifests, lifecycle states, logical
storage requests, and the physical locations of produced OME-Zarr datasets.

The package is intentionally independent of instrument control, storage
drivers, data serving, and visualization. Machine-local code in `vxl` resolves
a `StorageSpec`; the catalog only records the request and its resulting
locations.
