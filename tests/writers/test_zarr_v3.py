import numpy
import time
import math
import threading
import os
from pathlib import Path
from ruamel.yaml import YAML
from threading import Event, Thread
from voxel.writers.data_structures.shared_double_buffer import SharedDoubleBuffer
from multiprocessing.shared_memory import SharedMemory
from voxel.writers.zarr_v3 import Writer

if __name__ == '__main__':

    this_dir = Path(__file__).parent.resolve() # directory of this test file.
    config_path = this_dir / Path("test_zarr_v3.yaml")
    config = YAML().load(Path(config_path))

    chunk_size_frames = 32
    num_frames = 256
    num_tiles = 1

    frame_index = 0
    tile_index = 0

    for tile_index in range(num_tiles):
        
        stack_writer_worker = Writer(config['writer']['path'])
        stack_writer_worker.row_count_px = 10640
        stack_writer_worker.column_count_px = 14192
        stack_writer_worker.x_voxel_size_um = 0.748
        stack_writer_worker.y_voxel_size_um = 0.748
        stack_writer_worker.z_voxel_size_um = 1
        stack_writer_worker.frame_count_px = num_frames
        stack_writer_worker.compression = config['writer']['compression']
        stack_writer_worker.compression_level = config['writer']['compression_level']
        stack_writer_worker.shuffle = config['writer']['shuffle']
        stack_writer_worker.data_type = config['writer']['data_type']
        stack_writer_worker.downsample_method = config['writer']['downsample_method']
        stack_writer_worker.channel = '488'
        stack_writer_worker.filename = 'test'

        # move tile over 1 mm
        stack_writer_worker.x_position_mm = 0 + tile_index*1.000
        stack_writer_worker.y_position_mm = 0
        stack_writer_worker.z_position_mm = 0
        stack_writer_worker.prepare()
        stack_writer_worker.start()

        chunk_count = math.ceil(num_frames / chunk_size_frames)
        remainder = num_frames % chunk_size_frames
        last_chunk_size = chunk_size_frames if not remainder else remainder
        last_frame_index = num_frames - 1

        mem_shape = (chunk_size_frames,
                     stack_writer_worker.row_count_px,
                     stack_writer_worker.column_count_px)

        img_buffer = SharedDoubleBuffer(mem_shape,
                                        dtype=config['writer']['data_type'])

        chunk_lock = threading.Lock()

        # Images arrive serialized in repeating channel order.
        for stack_index in range(num_frames):
            chunk_index = stack_index % chunk_size_frames
            # Start a batch of pulses to generate more frames and movements.
            img_buffer.get_last_image()
            if chunk_index == 0:
                chunks_filled = math.floor(stack_index / chunk_size_frames)
                remaining_chunks = chunk_count - chunks_filled
            # Grab simulated frame
            if chunks_filled % 2 == 0:
                img_buffer.add_image( \
                numpy.random.randint(
                    low=0,
                    high=256,
                    size=(stack_writer_worker.row_count_px, stack_writer_worker.column_count_px),
                    dtype = config['writer']['data_type']
                ))
            else:
                img_buffer.add_image( \
                    numpy.random.randint(
                        low=0,
                        high=32,
                        size=(stack_writer_worker.row_count_px, stack_writer_worker.column_count_px),
                        dtype = config['writer']['data_type']
                    ))

            # mimic 5 fps imaging
            time.sleep(0.05)
            frame_index += 1
            # Dispatch either a full chunk of frames or the last chunk,
            # which may not be a multiple of the chunk size.
            if chunk_index == chunk_size_frames - 1 or stack_index == last_frame_index:
                while not stack_writer_worker.done_reading.is_set():
                    time.sleep(0.001)
                # Dispatch chunk to each StackWriter compression process.
                # Toggle double buffer to continue writing images.
                # To read the new data, the StackWriter needs the name of
                # the current read memory location and a trigger to start.
                # Lock out the buffer before toggling it such that we
                # don't provide an image from a place that hasn't been
                # written yet.
                with chunk_lock:
                    img_buffer.toggle_buffers()
                    if config['writer']['path'] is not None:
                        stack_writer_worker.shm_name = \
                            img_buffer.read_buf_mem_name
                        stack_writer_worker.done_reading.clear()

        stack_writer_worker.wait_to_finish()

        img_buffer.close_and_unlink()
        del img_buffer

        stack_writer_worker.delete_files()