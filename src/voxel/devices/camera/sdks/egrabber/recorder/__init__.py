# Copyright Euresys 2021

"""Python wrapper built on top of the low-level C API that defines the Recorder library."""

import ctypes
import six
import threading
from .api import *
from .errors import *
from ..generated.cEGrabber import get_library_name
from ..utils import to_cstr

# C types
_RECORDER_STATUS         = ctypes.c_int
_RECORDER_HANDLE         = ctypes.c_void_p
_RECORDER_PARAMETER      = ctypes.c_uint32
_RECORDER_OPEN_MODE      = ctypes.c_uint32
_RECORDER_CLOSE_MODE     = ctypes.c_uint32
_RECORDER_PROGRESS_STATE = ctypes.c_uint32

_RECORDER_PARAMETER_TYPE = {
    RECORDER_PARAMETER_VERSION : six.text_type,
    RECORDER_PARAMETER_CHAPTER_NAME : six.text_type,
    RECORDER_PARAMETER_CHAPTER_USER_INFO : six.text_type,
}

def _from_cchar_array(array):
    return array.value.decode()

def to_cchar_array(ptr, size):
    """Convert a buffer pointer to a `ctypes.c_char_Array_` buffer.

    Parameters
    ----------
    ptr : int
        Pointer to buffer.
    size : int
        Buffer size.

    Returns
    -------
    buffer : ctypes.c_char_Array_
    """
    return ctypes.cast(ptr, ctypes.POINTER(ctypes.c_char * size)).contents

class Progress:
    """Progress indicator for Recorder.export function. """

    def __init__(self, index, count, working):
        self.index = index
        self.count = count
        self.working = working

class ChapterInfo:
    """Chapter information (cf. Recorder.chapters)"""

    def __init__(self, recorder):
        self.index = recorder.get(RECORDER_PARAMETER_CHAPTER_INDEX)
        self.base_record_index = recorder.get(RECORDER_PARAMETER_RECORD_INDEX) - recorder.get(RECORDER_PARAMETER_CHAPTER_RECORD_INDEX)
        self.record_count = recorder.get(RECORDER_PARAMETER_CHAPTER_RECORD_COUNT)
        self.name = recorder.get(RECORDER_PARAMETER_CHAPTER_NAME)
        self.user_info = recorder.get(RECORDER_PARAMETER_CHAPTER_USER_INFO)
        self.timestamp_ns = recorder.get(RECORDER_PARAMETER_CHAPTER_TIMESTAMP)
        self.utc_ns = recorder.get(RECORDER_PARAMETER_CHAPTER_UTC)

class Recorder:
    """A Recorder object encapsulates a recorder handle and exposes higher level
    recorder functions; the destructor takes care of closing the recorder
    when the object goes out of scope.
    """

    def __init__(self, recorder_lib, handle, open_mode, close_mode):
        """Create a Recorder object from a recorder handle (cf. RecorderLibrary.open_recorder)."""
        self.recorder_lib = recorder_lib
        self.handle = handle
        self.open_mode = open_mode
        self.close_mode = close_mode
        self.lock = threading.RLock()
        self.current_progress = Progress(0, 0, False)
        self.abort_flag = False
        self.chapters = []
        if open_mode == RECORDER_OPEN_MODE_READ:
            if self.get(RECORDER_PARAMETER_RECORD_COUNT):
                index = self.get(RECORDER_PARAMETER_RECORD_INDEX)
            else:
                index = None
            try:
                for chapter_index in range(self.get(RECORDER_PARAMETER_CHAPTER_COUNT)):
                    try:
                        self.set(RECORDER_PARAMETER_CHAPTER_INDEX, chapter_index)
                    except IndexOutOfRange:
                        # IndexOutOfRange happens when selecting a last empty chapter
                        # because the base record index of the chapter is out of range
                        self.chapters.append(None)
                    else:
                        self.chapters.append(ChapterInfo(self))
            finally:
                if index is not None:
                    self.set(RECORDER_PARAMETER_RECORD_INDEX, index)

    def __del__(self):
        """Close a recorder using the mode defined when the recorder was created."""
        try:
            self.close()
        except:
            pass

    def __enter__(self):
        """Return a Recorder within a `with` block. This Recorder will automatically
        be closed when exiting the `with` block."""
        return self

    def __exit__(self, type, value, traceback):
        """Close a recorder when exiting a `with` block (using the mode defined when
        the recorder was created)."""
        self.close()

    def __bool__(self):
        """Check if the recorder handle is valid."""
        return bool(self.handle)

    def __nonzero__(self):
        """Check if the recorder handle is valid."""
        return self.__bool__()

    def close(self, mode=None):
        """Close the recorder using the given close mode.

        Parameters
        ----------
        mode : int (RECORDER_CLOSE_MODE), optional
            If None, the mode defined when the recorder was created is used.
        """
        if self.handle:
            if mode:
                self.recorder_lib._close(self.handle, mode)
            else:
                self.recorder_lib._close(self.handle, self.close_mode)
            self.handle = None

    def set(self, parameter, value):
        """Set a recorder parameter.

        Parameters
        ----------
        parameter : int (RECORDER_PARAMETER)
        value : int or str
        """
        dtype = type(value)
        if dtype in six.integer_types:
            self.recorder_lib._set_parameter_integer(self.handle, parameter, value)
        elif dtype in (str, six.text_type):
            self.recorder_lib._set_parameter_string(self.handle, parameter, value)
        else:
            raise InvalidParameterType('value must be {} or {}'.format(six.integer_types, six.text_type))

    def get(self, parameter, dtype=None):
        """Get a recorder parameter.

        Parameters
        ----------
        parameter : int (RECORDER_PARAMETER)
        dtype : class <int> or <str>, optional
            Type of return value. Can either be `int` or `str`.
            If None, type of `value` is automatically assigned.

        Returns
        -------
        value : int or str
        """
        if dtype is None:
            dtype = _RECORDER_PARAMETER_TYPE.get(parameter, int)
        if dtype in six.integer_types:
            return self.recorder_lib._get_parameter_integer(self.handle, parameter)
        elif dtype in (str, six.text_type):
            return self.recorder_lib._get_parameter_string(self.handle, parameter)
        else:
            raise InvalidParameterType('dtype must be {} or {}'.format(six.integer_types, six.text_type))

    def start_chapter(self, name="", info=""):
        """Start a new chapter.

        Parameters
        ----------
        name : str, optional
            Name of the new chapter. Allowed character are [-A-Za-z0-9 ].
        info : str, optional
            Additional chapter information.

        Notes
        -----
        - A chapter helps grouping recordings and provides a synchronization point between
          system and UTC timestamps.
        - A chapter is automatically created if needed on the first write after opening the
          container if this function has not been called. The name of the automatically created
          chapter is "Chapter<xx>", where <xx> is the index of the new chapter.
        - It is allowed to call this method at any time to signal a time discontinuity or start
          a new group of recordings.
        - The newly created chapter becomes the current chapter and the RECORDER_CHAPTER_XXXX
          parameters are updated accordingly.
        - The chapter name length cannot exceed 255 characters.
        - When a chapter is created, a synchronized pair of system/UTC timestamps is captured
          and stored in the storage as RECORDER_PARAMETER_CHAPTER_TIMESTAMP and
          RECORDER_PARAMETER_CHAPTER_UTC; the system time timestamp is expressed in nanoseconds
          since the computer booted.
        - When reading back from a container, this pair of synchronized timestamps of the
          corresponding chapter is used internally to compute the value of the (non-zero) utc
          field of a RECORDER_BUFFER_INFO record from the value of the (system) timestamp field.
        """
        return self.recorder_lib._start_chapter(self.handle, name, info)

    def write(self, info, buffer):
        """Write to the container.

        Parameters
        ----------
        info : RECORDER_BUFFER_INFO
            Buffer metadata to write to the container.
        buffer : ctypes.c_char_Array_, bytearray or bytes
            Buffer data (pixels) to write to the container.

        Notes
        -----
        - A `ctypes.c_char_Array_` buffer can be obtained using `to_cchar_array` helper function,
          given a pointer and size of the buffer.
        - The buffer info and data are written to the container at the current index position
          (RECORDER_PARAMETER_RECORD_INDEX); the recorder index is automatically incremented
          by one after a write and the recorder count (RECORDER_PARAMETER_RECORD_COUNT) is also
          adapted accordingly.
        """
        return self.recorder_lib._write(self.handle, info, buffer)

    def read(self):
        """Read data from the container.

        Returns
        -------
        buffer : ctypes.c_char_Array_
            Buffer data (pixels) read from the container.
        info : RECORDER_BUFFER_INFO
            Buffer metadata read from the container.

        Notes
        -----
        - The function reads the buffer info and data of the record at the position defined by
          the parameter `RECORDER_PARAMETER_RECORD_INDEX`. The recorder index is automatically set
          to the next record after a successful read.
        """
        return self.recorder_lib._read(self.handle)

    def read_info(self):
        """Read metadata from the container.

        Returns
        -------
        info : RECORDER_BUFFER_INFO
            Buffer metadata read from the container.

        Notes
        -----
        - The function reads the buffer info of the record at the position defined by the parameter
          `RECORDER_PARAMETER_RECORD_INDEX`. The recorder index is not changed by this function.
        """
        return self.recorder_lib._read_info(self.handle)

    def export(self, path, count, export_pixel_format=None, on_progress=None):
        """Export images from the container.

        Parameters
        ----------
        path : str
            Path template of the exported files (see below for a description of the name decoration).
        count : int
            Number of records to export.
        export_pixel_format : int, optional
            Pixel format of the exported file. If None, original pixel format is used.
        on_progress : Callable[[Progress], None], optional
            Progress indication.

        Returns
        -------
        count : int
            Number of records exported.

        Notes
        -----
        - Export starts at the current index position (`RECORDER_PARAMETER_RECORD_INDEX`)
          in the container and goes on until `count` records have been exported or the
          end of the container is reached. The `RECORDER_PARAMETER_RECORD_INDEX` is updated
          accordingly.
        - File name decoration uses the @ character as a place holder for the following:
          - @i for the index relative to the first record in the container
               (number of digits used is defined by the number of records in the container)
          - @n for the index relative to the current record written
               (number of digits used is defined by the `count` parameter)
          - @p for the part index relative to the record
               (number of digits used is defined by the buffer part count of the record)
          - @t for the timestamp of the exported record
          - @c for the chapter index
          - @C for the chapter name
          - @@ for the literal @
          All other @ patterns are invalid and will lead to a `RECORDER_STATUS_INVALID_ARGUMENT` exception.
        - The file format is derived from the file extension:
          - .tiff or .tif for the TIFF file format
          - .mkv for the Matroska MKV file format (using the V_UNCOMPRESSED codec)
        - The allowed values for `export_pixel_format` depend on the file type:
          - TIFF files support the following: Mono8, Mono16, RGB8, RGB16
          - MKV files support the following: Mono8, RGB8
        - For TIFF files:
          - if `count` is greater than 1 and `path` does not contain any @ pattern, we add .@n before
            the file extension
          - if a record contains more than 1 part and the path does not contain the @p pattern,
            we add `.@p` before the file extension
        - For MKV files:
          - the export operation creates one MKV file per chapter; if the export operation
            spans several chapters, we add `@.n` automatically before the file extension
          - the image width, height and pixel format must be constant for the entire file;
            the first exported image is used to define these values. A subsequent image with a
            different format will be simply skipped and the returned count will not be updated.
          - timestamps increase monotonically; when a backward discontinuity is detected i.e. the
            relative time from the beginning of the file of the image to be written is less than the
            relative time of the latest image written, a new time reference is taken.
        - Most of the times, a record contains one image (one buffer part) so the number of exported
          images matches the number of exported records; but, if a record contains more than 1 part,
          each part is exported as a separate image so the number of exported images will
          be greater than the returned `count`.
        - Records containing Bayer formats are converted using the decoding method defined by the
          parameter `RECORDER_PARAMETER_BAYER_DECODING_METHOD`.
        """
        _RECORDER_PROGRESS_STATE_STARTING = 0
        _RECORDER_PROGRESS_STATE_ONGOING  = 1
        _RECORDER_PROGRESS_STATE_ENDING   = 2
        @ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, _RECORDER_PROGRESS_STATE, ctypes.c_size_t, ctypes.c_size_t)
        def progress_callback(context, state, index, count):
            pcontext = ctypes.cast(context, ctypes.py_object)
            rec = pcontext.value
            with rec.lock:
                if state == _RECORDER_PROGRESS_STATE_STARTING:
                    rec.current_progress = Progress(0, 0, True)
                    rec.abort_flag = False
                elif state == _RECORDER_PROGRESS_STATE_ONGOING:
                    rec.current_progress = Progress(index, count, True)
                elif state == _RECORDER_PROGRESS_STATE_ENDING:
                    p = rec.current_progress
                    rec.current_progress = Progress(p.index, p.count, False)
                if on_progress:
                    on_progress(rec.current_progress)
                if rec.abort_flag:
                    return -1
                else:
                    return 0
        if export_pixel_format is None:
            export_pixel_format = 0
        return self.recorder_lib._export(self.handle, path, count, export_pixel_format, progress_callback, ctypes.py_object(self))

    def get_progress(self):
        with self.lock:
            return self.current_progress

    def abort(self):
        with self.lock:
            self.abort_flag = True

    def find_chapter_by_name(self, name):
        for chapter in self.chapters:
            if chapter and chapter.name == name:
                return chapter

    def find_chapter_by_record_index(self, record_index):
        for chapter in self.chapters:
            if chapter and chapter.base_record_index <= record_index and record_index < chapter.base_record_index + chapter.record_count:
                return chapter

class RecorderLibrary:
    """A RecorderLibrary object loads/unloads the Recorder library in its constructor/destructor.
    It mainly helps to open a recorder."""

    def __init__(self, path=None):
        """Create a RecorderLibrary object and initialize the Recorder Library.

        Parameters
        ----------
        path : str, optional
            File path to the Recorder Library. If None, default path is used."""
        if path:
            self._dll = ctypes.CDLL(path)
        else:
            self._dll = ctypes.CDLL(self.get_default_library_path())
        self._init_library()

    def __del__(self):
        """Close the Recorder library."""
        self._close_library()

    @staticmethod
    def get_default_library_path():
        """Get default path to the Recorder Library.

        Returns
        -------
        path : str
        """
        return get_library_name('recorder')

    def _init_library(self):
        RecorderError.check(self._dll.RecorderInitLib())

    def _close_library(self):
        RecorderError.check(self._dll.RecorderCloseLib())

    def open_recorder(self, path, open_mode, close_mode=RECORDER_CLOSE_MODE_TRIM):
        """Open a recorder and return a Recorder object that wraps the opened recorder handle.

        Parameters
        ----------
        path : str
            Path to the recorder container.
        open_mode : int (RECORDER_OPEN_MODE)
            Operation mode of the recorder.
        close_mode : int (RECORDER_CLOSE_MODE), default=RECORDER_CLOSE_MODE_TRIM
            Specifies how the recorder container is closed.
            - If `RECORDER_CLOSE_MODE_TRIM`: the recorder container is reduced to the smallest
              size that fits the container contents.
            - If `RECORDER_CLOSE_MODE_KEEP`: the recorder container size is unchanged.

        Returns
        -------
        recorder : Recorder
        """
        (handle, _) = self._open(path, open_mode)
        return Recorder(self, handle, open_mode, close_mode)

    def _open(self, path, mode):
        c_handle = _RECORDER_HANDLE()
        c_file_version = ctypes.c_uint32()
        RecorderError.check(self._dll.RecorderOpen(to_cstr(path), _RECORDER_OPEN_MODE(mode), ctypes.byref(c_handle), ctypes.byref(c_file_version)))
        return (c_handle.value, c_file_version.value)

    def _close(self, handle, mode):
        RecorderError.check(self._dll.RecorderClose(_RECORDER_HANDLE(handle), _RECORDER_CLOSE_MODE(mode)))

    def _set_parameter_string(self, handle, parameter, value):
        RecorderError.check(self._dll.RecorderSetParameterString(_RECORDER_HANDLE(handle), _RECORDER_PARAMETER(parameter), to_cstr(value)))

    def _get_parameter_string(self, handle, parameter):
        c_size = ctypes.c_size_t()
        RecorderError.check(self._dll.RecorderGetParameterString(_RECORDER_HANDLE(handle), _RECORDER_PARAMETER(parameter), None, ctypes.byref(c_size)))
        c_value = (ctypes.c_char * c_size.value)()
        RecorderError.check(self._dll.RecorderGetParameterString(_RECORDER_HANDLE(handle), _RECORDER_PARAMETER(parameter), ctypes.byref(c_value), ctypes.byref(c_size)))
        return _from_cchar_array(c_value)

    def _set_parameter_integer(self, handle, parameter, value):
        RecorderError.check(self._dll.RecorderSetParameterInteger(_RECORDER_HANDLE(handle), _RECORDER_PARAMETER(parameter), ctypes.c_int64(value)))

    def _get_parameter_integer(self, handle, parameter):
        c_value = ctypes.c_int64()
        RecorderError.check(self._dll.RecorderGetParameterInteger(_RECORDER_HANDLE(handle), _RECORDER_PARAMETER(parameter), ctypes.byref(c_value)))
        return c_value.value

    def _write(self, handle, info, buffer):
        if info and buffer:
            buffer_ptr = None
            def check_len():
                if info.size > len(buffer):
                    raise BufferTooSmall('buffer length({}) must be greater than or equal to info.size({})'.format(len(buffer), info.size))
            if type(buffer).__name__.startswith('c_char_Array_'):
                check_len()
                c_buffer = buffer
            elif type(buffer) == bytearray:
                check_len()
                c_buffer = (ctypes.c_char * info.size).from_buffer(buffer)
            elif type(buffer) == bytes:
                check_len()
                c_buffer = (ctypes.c_char * info.size).from_buffer_copy(buffer)
            elif type(buffer) == ctypes.c_void_p:
                buffer_ptr = buffer
            else:
                raise InvalidParameterType('buffer must be ctypes.c_char_Array_, bytearray or bytes for write operation')
            RecorderError.check(self._dll.RecorderWrite(_RECORDER_HANDLE(handle), ctypes.byref(info), buffer_ptr or ctypes.byref(c_buffer), None, None, None))
            return
        else:
            raise InvalidArgument('buffer and info are both required to write a record')

    def _read(self, handle):
        c_buffer_size = ctypes.c_size_t()
        RecorderError.check(self._dll.RecorderRead(_RECORDER_HANDLE(handle), None, None, ctypes.byref(c_buffer_size), None))
        info = RECORDER_BUFFER_INFO()
        c_buffer = (ctypes.c_char * (c_buffer_size.value if c_buffer_size.value else 1))()
        RecorderError.check(self._dll.RecorderRead(_RECORDER_HANDLE(handle), ctypes.byref(info), ctypes.byref(c_buffer), ctypes.byref(c_buffer_size), None))
        if not c_buffer_size:
            c_buffer = (ctypes.c_char * 0)()
        return (c_buffer, info)

    def _read_info(self, handle):
        c_buffer_size = ctypes.c_size_t()
        info = RECORDER_BUFFER_INFO()
        RecorderError.check(self._dll.RecorderRead(_RECORDER_HANDLE(handle), ctypes.byref(info), None, ctypes.byref(c_buffer_size), None))
        return info

    def _export(self, handle, path, count, export_pixel_format, progress_callback, progress_context):
        c_count = ctypes.c_size_t(count)
        RecorderError.check(self._dll.RecorderExport(_RECORDER_HANDLE(handle), to_cstr(path), ctypes.byref(c_count), ctypes.c_uint32(export_pixel_format), \
                            ctypes.c_uint32(0), progress_callback, progress_context))
        return c_count.value

    def _start_chapter(self, handle, name, info):
        RecorderError.check(self._dll.RecorderStartChapter(_RECORDER_HANDLE(handle), to_cstr(name), to_cstr(info)))

    def _set(self, parameter, value):
        dtype = type(value)
        if dtype in six.integer_types:
            RecorderError.check(self._dll.RecorderSetParameterInteger(None, _RECORDER_PARAMETER(parameter), ctypes.c_int64(value)))
        elif dtype in (str, six.text_type):
            RecorderError.check(self._dll.RecorderSetParameterString(None, _RECORDER_PARAMETER(parameter), to_cstr(value)))
        else:
            raise InvalidParameterType('value must be {} or {}'.format(six.integer_types, six.text_type))
