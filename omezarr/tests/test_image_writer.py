import pytest
from ome_zarr_writer import OMEZarrWriter
from vxlib.imaging.writer import ImageWriter


def test_the_writer_keeps_the_image_writer_contract() -> None:
    assert isinstance(OMEZarrWriter(), ImageWriter)


def test_a_writer_that_leaves_out_a_method_cannot_be_built() -> None:
    partial = type("Partial", (ImageWriter,), {})  # a writer with none of the contract's methods
    with pytest.raises(TypeError, match="abstract"):
        partial()
