import numpy
import time
from multiprocessing.shared_memory import SharedMemory
from voxel.utils.processing.histogram import HistogramProjection

if __name__ == "__main__":
    num_frames = 1024
    img_shape = (1024, 1024)

    histogram_projection = HistogramProjection(path=".")

    histogram_projection.row_count_px = img_shape[0]
    histogram_projection.column_count_px = img_shape[1]
    histogram_projection.frame_count_px = num_frames
    histogram_projection.z_bin_count_px = 32
    histogram_projection.y_bin_count_px = 64
    histogram_projection.x_bin_count_px = 128
    histogram_projection.z_bins = 1024
    histogram_projection.y_bins = 512
    histogram_projection.x_bins = 256
    histogram_projection.z_min_value = 0
    histogram_projection.y_min_value = 0
    histogram_projection.x_min_value = 0
    histogram_projection.z_max_value = 1024
    histogram_projection.y_max_value = 512
    histogram_projection.x_max_value = 256
    histogram_projection.data_type = "uint16"
    histogram_projection.filename = "data"
    histogram_projection.acquisition_name = "test"

    img_bytes = numpy.prod(img_shape) * numpy.dtype("uint16").itemsize

    mip_buffer = SharedMemory(create=True, size=int(img_bytes))
    mip_image = numpy.ndarray(img_shape, dtype="uint16", buffer=mip_buffer.buf)

    histogram_projection.prepare(mip_buffer.name)
    histogram_projection.start()

    # Images arrive serialized in repeating channel order.
    for stack_index in range(num_frames):
        frame = numpy.random.normal(loc=100, scale=50, size=img_shape).astype(numpy.uint16)

        stack_index += 1

        while histogram_projection.new_image.is_set():
            time.sleep(0.1)
        mip_image[:, :] = frame
        histogram_projection.new_image.set()

    histogram_projection.wait_to_finish()
    mip_buffer.close()
    mip_buffer.unlink()
    del mip_buffer
