from ome_zarr_writer.types import Vec2D


def parse_vec2d[T: int | float](arg: Vec2D[T] | list[T] | str, rtype: type[T]) -> Vec2D[T]:
    if isinstance(arg, str):
        arg = [rtype(x) for x in arg.split(",")]
    if isinstance(arg, list):
        assert len(arg) == 2, f"Expected 2 values, got {len(arg)}"
        return Vec2D(y=rtype(arg[0]), x=rtype(arg[1]))
    return arg
