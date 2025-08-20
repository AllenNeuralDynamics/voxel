import numpy
import time
from multiprocessing.shared_memory import SharedMemory
from voxel.utils.processing.max_projection.gpu.pyclesperanto import GPUMaxProjection

if __name__ == "__main__":
    num_frames = 256
    img_shape = (1024, 1024)

    max_projection = GPUMaxProjection(path=".")

    max_projection.row_count_px = img_shape[0]
    max_projection.column_count_px = img_shape[1]
    max_projection.frame_count_px = num_frames
    max_projection.z_projection_count_px = 256
    max_projection.x_projection_count_px = 256
    max_projection.y_projection_count_px = 256
    max_projection.data_type = "uint16"
    max_projection.filename = "image"
    max_projection.acquisition_name = "test"

    img_bytes = numpy.prod(img_shape) * numpy.dtype("uint16").itemsize

    mip_buffer = SharedMemory(create=True, size=int(img_bytes))
    mip_image = numpy.ndarray(img_shape, dtype="uint16", buffer=mip_buffer.buf)

    max_projection.prepare(mip_buffer.name)
    max_projection.start()

    # Images arrive serialized in repeating channel order.
    for stack_index in range(num_frames):
        frame = numpy.random.randint(low=0, high=256, size=img_shape, dtype="uint16")

        stack_index += 1

        while max_projection.new_image.is_set():
            time.sleep(0.1)
        mip_image[:, :] = frame
        max_projection.new_image.set()

    max_projection.wait_to_finish()
    mip_buffer.close()
    mip_buffer.unlink()
    del mip_buffer
