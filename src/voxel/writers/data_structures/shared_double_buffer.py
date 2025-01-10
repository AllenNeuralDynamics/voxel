from multiprocessing import Event
from multiprocessing.shared_memory import SharedMemory

import numpy as np


class SharedDoubleBuffer:
    """
    A single-producer-single-consumer multi-process double buffer\n
    implemented as a numpy ndarray.

    :param shape: shape of the buffer
    :type shape: tuple
    :param dtype: data type of the buffer
    :type dtype: str

    .. code-block: python

        dbl_buf = SharedDoubleBuffer((8, 320, 240), 'uint16')

        dbl_buf.write_mem[0][:,:] = np.zeros((320, 240), dtype='uint16')
        dbl_buf.write_mem[1][:,:] = np.zeros((320, 240), dtype='uint16')
        dbl_buf.write_mem[2][:,:] = np.zeros((320, 240), dtype='uint16')

        # When finished, switch buffers.
        # Note, user must apply flow control scheme to ensure another
        # process is done using the read_buf before we switch it.
        dbl_buf.toggle_buffers() # read_buf and write_buf have switched places.
    """

    def __init__(self, shape: tuple, dtype: str):
        # overflow errors without casting for large datasets
        nbytes = int(np.prod(shape, dtype=np.int64) * np.dtype(dtype).itemsize)
        self.mem_blocks = [
            SharedMemory(create=True, size=nbytes),
            SharedMemory(create=True, size=nbytes),
        ]
        # attach numpy array references to shared memory.
        self.read_buf = np.ndarray(shape, dtype=dtype, buffer=self.mem_blocks[0].buf)
        self.write_buf = np.ndarray(shape, dtype=dtype, buffer=self.mem_blocks[1].buf)
        # attach references to the names of the memory locations.
        self.read_buf_mem_name = self.mem_blocks[0].name
        self.write_buf_mem_name = self.mem_blocks[1].name
        # save values for querying later.
        self.dtype = dtype
        self.shape = shape
        self.nbytes = nbytes
        # create flag to indicate if data has been read out from the read buf.
        self.is_read = Event()
        self.is_read.clear()
        # initialize buffer index
        self.buffer_index = -1

    def toggle_buffers(self):
        """
        Switch read and write references and the locations of their shared\n
        memory.
        """
        # reset buffer index
        self.buffer_index = -1
        # toggle who acts as read buf and write buf.
        tmp = self.read_buf
        self.read_buf = self.write_buf
        self.write_buf = tmp
        # do the same thing with the shared memory location names
        tmp = self.read_buf_mem_name
        self.read_buf_mem_name = self.write_buf_mem_name
        self.write_buf_mem_name = tmp

    def add_image(self, image: np.array):
        """
        Add an image into the buffer at the correct index.
        """

        self.write_buf[self.buffer_index + 1] = image
        self.buffer_index += 1

    def get_last_image(self):
        """
        Get the last image from the buffer.

        :return: Last image from the buffer
        :rtype: numpy.array
        """

        if self.buffer_index == -1:
            # buffer just switched, grab last image from read buffer
            return self.read_buf[-1]
        else:
            # return the image from the write buffer
            return self.write_buf[self.buffer_index]

    def close_and_unlink(self):
        """
        Shared memory cleanup; call when done using this object.
        """

        for mem in self.mem_blocks:
            mem.close()
            mem.unlink()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Cleanup called automatically if opened using a `with` statement.
        """

        self.close_and_unlink()
