"""The shared inputs of the 2 records prototypes, so they run the same acquisition."""

from vxlib.vector import Transform, Vec3D

from vxl.storage import LocalLocation, LocationRole, LocationStatus

TRANSFORM = Transform(
    Vec3D(z=0.0, y=0.0, x=0.0),
    (Vec3D(z=2.0, y=0.0, x=0.0), Vec3D(z=0.0, y=0.5, x=0.0), Vec3D(z=0.0, y=0.0, x=0.5)),
    (10, 64, 64),
)
CAMERA_LOCATION = LocalLocation(
    role=LocationRole.DESTINATION, status=LocationStatus.WRITING, host="rig", path="/data/run/0/camera.ome.zarr"
)


def show(design: str, status: str, visits: list[tuple[object, ...]], extra: object) -> None:
    print(f"design {design}: acquisition {status}")
    for index, visit in enumerate(visits):
        print(f"  visit {index}: {visit}")
    print(f"  {extra}")
