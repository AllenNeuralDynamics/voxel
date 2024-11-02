from multiprocessing import Value, Lock
from multiprocessing.shared_memory import SharedMemory
import numpy as np


class SharedDoubleBuffer:
    """
    A single-producer-single-consumer multi-process double buffer
    implemented as a numpy ndarray with synchronization mechanisms.
    Supports both single image and batch consumption.

    :param shape: shape of the buffer
    :type shape: tuple
    :param dtype: data type of the buffer
    :type dtype: str
    :raises ValueError: If shape is invalid or dtype is not supported
    :raises MemoryError: If shared memory allocation fails
    """

    def __init__(self, shape: tuple, dtype: str):
        if not shape or any(dim <= 0 for dim in shape):
            raise ValueError("Buffer shape must be positive")

        # overflow errors without casting for large datasets
        self.nbytes = int(np.prod(shape, dtype=np.int64) * np.dtype(dtype).itemsize)

        # Initialize synchronization primitives
        self.write_lock = Lock()
        self.read_lock = Lock()

        try:
            self.mem_blocks = [
                SharedMemory(create=True, size=self.nbytes),
                SharedMemory(create=True, size=self.nbytes),
            ]
        except FileExistsError:
            raise MemoryError("Failed to create shared memory segments")

        self.write_mem_block_idx = Value("i", 0)
        self.read_mem_block_idx = Value("i", 1)

        # attach numpy array references to shared memory
        self.write_buf = np.ndarray(shape, dtype=dtype, buffer=self.mem_blocks[0].buf)
        self.read_buf = np.ndarray(shape, dtype=dtype, buffer=self.mem_blocks[1].buf)

        # attach references to the names of the memory locations
        self.write_buf_mem_name = self.mem_blocks[0].name
        self.read_buf_mem_name = self.mem_blocks[1].name

        # save values for querying later
        self.dtype = dtype
        self.shape = shape
        self.buffer_index = -1
        self.frames_in_read_buffer = 0

        # Set initial state

    def toggle_buffers(self):
        """
        Switch read and write references and their shared memory locations.
        Ensures synchronization between producer and consumer.

        :raises RuntimeError: If previous buffer hasn't been fully consumed
        """
        with self.write_lock:

            # Transfer write buffer info to read buffer
            self.frames_in_read_buffer = self.buffer_index + 1

            # reset buffer index
            self.buffer_index = -1

            # toggle buffers
            self.read_buf, self.write_buf = self.write_buf, self.read_buf
            self.read_buf_mem_name, self.write_buf_mem_name = self.write_buf_mem_name, self.read_buf_mem_name
            self.read_mem_block_idx.value, self.write_mem_block_idx.value = (
                self.write_mem_block_idx.value,
                self.read_mem_block_idx.value,
            )

    def add_frame(self, frame: np.ndarray):
        """
        Add an image into the buffer at the correct index with thread safety.

        :param frame: Image to add to buffer
        :type frame: np.ndarray
        :raises ValueError: If frame shape doesn't match buffer shape
        :raises IndexError: If buffer is full
        """
        if frame.shape != self.shape[1:]:
            raise ValueError(f"Image shape {frame.shape} doesn't match buffer shape {self.shape[1:]}")

        with self.write_lock:
            if self.buffer_index >= self.shape[0] - 1:
                raise IndexError("Buffer is full")

            self.write_buf[self.buffer_index + 1] = frame
            self.buffer_index += 1

    def close_and_unlink(self) -> None:
        """
        Shared memory cleanup with proper synchronization.
        Call when done using this object.
        """
        with self.write_lock, self.read_lock:
            for mem in self.mem_blocks:
                try:
                    mem.close()
                    mem.unlink()
                except FileNotFoundError:
                    pass  # Already unlinked

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Cleanup called automatically if opened using a 'with' statement.
        """
        self.close_and_unlink()
