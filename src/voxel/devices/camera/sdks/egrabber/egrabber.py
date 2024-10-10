# Copyright Euresys 2020

"""EGrabber module."""

from .generated import *
from .generated import cEGrabber as cE
from . import utils, query, egentl, discovery
import weakref
import six
import ctypes as ct
import sys
import threading


class _Module():
    """GenApi Port Module used by an EGrabber object."""

    def __init__(self, grabber, port_handle=None):
        self.grabber = weakref.ref(grabber)
        self.port_handle = port_handle

    def get_info(self, cmd, info_datatype=None):
        """Get GenApi Port Module information.

        Parameters
        ----------
        cmd : int (BUFFER_INFO_CMD)
            The info command to get, available values depend on module.
            - If module is SystemModule: cmd values belong to GenTL::TL_INFO_CMD_LIST.
            - If module is InterfaceModule: cmd values belong to GenTL::INTERFACE_INFO_CMD_LIST.
            - If module is DeviceModule: cmd values belong to GenTL::DEVICE_INFO_CMD_LIST.
            - If module is StreamModule: cmd values belong to GenTL::STREAM_INFO_CMD_LIST.
        info_datatype : int (INFO_DATATYPE), optional
            Type of data to get (cf. GenTL::INFO_DATATYPE_LIST).

        Returns
        -------
        info : int, bool, float or str
        """
        return self.grabber()._get_info(self.port_handle, self.__class__, cmd, info_datatype)

    def gc_read_port(self, address, size):
        """Read size bytes from specified port at given address.

        Parameters
        ----------
        address : int
            Byte address to read from.
        size : int
            Number of bytes to read.

        Returns
        -------
        data : ctypes.c_char_Array_
        """
        return self.grabber()._gc_read_port(self.port_handle, self.__class__, address, size)

    def gc_write_port(self, address, data):
        """Write len(data) bytes to specified port at given address.

        Parameters
        ----------
        address : int
            Byte address to write to.
        data : ctypes.c_char_Array_, bytearray or bytes
            Input buffer containing the data to write.
        """
        self.grabber()._gc_write_port(self.port_handle, self.__class__, address, data)

    def gc_read_port_value(self, address, ctype):
        """Read a single value from specified port at given address.

        Parameters
        ----------
        address : int
            Byte address to read from.
        ctype : class
            - ctypes.c_size_t
            - ctypes.c_int8
            - ctypes.c_int16
            - ctypes.c_int32
            - ctypes.c_int64
            - ctypes.c_uint8
            - ctypes.c_uint16
            - ctypes.c_uint32
            - ctypes.c_uint64
            - ctypes.c_float
            - ctypes.c_double
            - ctypes.POINTER(ctypes.c_char)
            The C type corresponding to the value to read.

        Returns
        -------
        value : int or float
        """
        return self.grabber()._gc_read_port_value(self.port_handle, self.__class__, address, ctype)

    def gc_write_port_value(self, address, ctype, value):
        """Write a single value to specified port at given address.

        Parameters
        ----------
        address : int
            Byte address to write to.
        ctype : class
            - ctypes.c_size_t
            - ctypes.c_int8
            - ctypes.c_int16
            - ctypes.c_int32
            - ctypes.c_int64
            - ctypes.c_uint8
            - ctypes.c_uint16
            - ctypes.c_uint32
            - ctypes.c_uint64
            - ctypes.c_float
            - ctypes.c_double
            The C type corresponding to the value to write.
        value : int or float
            Value to write as a sequence of bytes.
        """
        self.grabber()._gc_write_port_value(self.port_handle, self.__class__, address, ctype, value)

    def gc_read_port_string(self, address, size):
        """Read size bytes as null-terminated string from specified port at given address.

        Parameters
        ----------
        address : int
            Byte address to read from.
        size : int
            Number of bytes to read.

        Returns
        -------
        value : str
        """
        return self.grabber()._gc_read_port_string(self.port_handle, self.__class__, address, size)

    def get(self, feature, dtype=None):
        """Get value of GenApi Port Module feature.

        Parameters
        ----------
        feature : str
            Name of feature to read.
        dtype : class, optional
            Type of return value. Can either be int, float, bool, str, list or (ctypes.c_char * N).
            If None, type of value is automatically assigned.
            If (ctypes.c_char * N), N is the number of bytes to get from a Register feature.

        Returns
        -------
        value : int, float, bool, str, list or ctypes.c_char_Array
        """
        return self.grabber()._get(self.port_handle, self.__class__, feature, dtype)

    def set(self, feature, value):
        """Set value of GenApi Port Module feature.

        Parameters
        ----------
        feature : str
            Name of feature to modify.
        value : int, float, str, bool or ctypes.c_char_Array
            Value to write.
            If type(value) is ctypes.c_char_Array, the feature is expected to expose a Register interface.
        """
        self.grabber()._set(self.port_handle, self.__class__, feature, value)

    def execute(self, command):
        """Execute GenApi Port Module command feature.

        Parameters
        ----------
        command : str
            Name of feature to execute.
        """
        self.grabber()._execute(self.port_handle, self.__class__, command)

    def attach_event(self, event_id, event_data=None):
        """Attach GenApi event to specified GenApi Port Module.

        Parameters
        ----------
        event_id : int
            GenApi event identifier.
        event_data : ctypes.c_ubyte_Array, optional
            Data associated to the event.
        """
        self.grabber()._attach_event(self.port_handle, self.__class__, event_id, event_data)

    def invalidate(self, feature):
        """Invalidate cache of GenApi Port Module feature (and its dependencies).

        Parameters
        ----------
        feature : str
            Name of feature to invalidate.

        Notes
        -----
        - This only invalidates the cache (the feature itself will not be changed).
        """
        self.grabber()._invalidate(self.port_handle, self.__class__, feature)

    def attributes(self):
        """Get the list of attributes exposed by a GenApi Module.

        Returns
        -------
        str
        """
        return self.get(query.attributes(), str)

    def features(self, available_only=True):
        """Get the list of features exposed by a GenApi Module.

        Parameters
        ----------
        available_only : bool
            If true: the query will be configured to only include features available at "query" time; 
            if false: the query will be configured to include all the exposed features.

        Returns
        -------
        list
        """
        return self.get(query.features(available_only), list)

    def features_of(self, category, available_only=True):
        """Get the list of features of a category exposed by a GenApi Module.

        Parameters
        ----------
        category : str
            Name of the category.
        available_only : bool
            If true: the query will be configured to only include features of the category available at "query" time;
            if false: the query will be configured to include all the exposed features of the category.

        Returns
        -------
        list
        """
        return self.get(query.features_of(category, available_only), list)

    def categories(self, available_only=True):
        """Get the list of categories exposed by a GenApi Module.

        Parameters
        ----------
        available_only : bool
            If true: the query will be configured to only include categories available at "query" time;
            if false: the query will be configured to include all the exposed categories.

        Returns
        -------
        list
        """
        return self.get(query.categories(available_only), list)

    def categories_of(self, category, available_only=True):
        """Get the list of categories of a category exposed by a GenApi Module.

        Parameters
        ----------
        category : str
            Name of the category.
        available_only : bool
            If true: the query will be configured to only include categories of the category available at "query" time;
            if false: the query will be configured to include all the exposed categories of the category.

        Returns
        -------
        list
        """
        return self.get(query.categories_of(category, available_only), list)

    def enum_entries(self, feature, available_only=True):
        """Get the list of entries of a GenApi enumeration.

        Parameters
        ----------
        feature : str
            Name of enumeration feature to query.
        available_only : bool
            If true: the query will be configured to only include enumeration entries available at "query" time;
            if false: the query will be configured to include all enumeration entries of the given feature.

        Returns
        -------
        list
        """
        return self.get(query.enum_entries(feature, available_only=True), list)

    def available(self, feature):
        """Check if a feature is available.

        Parameters
        ----------
        feature : str
            Name of the feature to query.

        Returns
        -------
        bool
        """
        return self.get(query.available(feature), bool)

    def readable(self, feature):
        """Check if a feature is readable.

        Parameters
        ----------
        feature : str
            Name of the feature to query.

        Returns
        -------
        bool
        """
        return self.get(query.readable(feature), bool)

    def writeable(self, feature):
        """Check if a feature is writeable.

        Parameters
        ----------
        feature : str
            Name of the feature to query.

        Returns
        -------
        bool
        """
        return self.get(query.writeable(feature), bool)

    def implemented(self, feature):
        """Check if a feature is implemented.

        Parameters
        ----------
        feature : str
            Name of the feature to query.

        Returns
        -------
        bool
        """
        return self.get(query.implemented(feature), bool)

    def command(self, feature):
        """Check if a feature is a command.

        Parameters
        ----------
        feature : str
            Name of the feature to query.

        Returns
        -------
        bool
        """
        return self.get(query.command(feature), bool)

    def done(self, feature):
        """Check if execution of a command is done.

        Parameters
        ----------
        feature : str
            Name of the command to query.

        Returns
        -------
        bool
        """
        return self.get(query.done(feature), bool)

    def interfaces(self, feature):
        """Get the list of interfaces of a feature.

        Parameters
        ----------
        feature : str
            Name of the feature to query.

        Returns
        -------
        list
        """
        return self.get(query.interfaces(feature), list)

    def source(self, feature):
        """Get the XML source of a feature.

        Parameters
        ----------
        feature : str
            Name of the feature to query.

        Returns
        -------
        str
        """
        return self.get(query.source(feature), str)

    def xml(self):
        """Get the register description document of a GenApi Module.

        Returns
        -------
        str
        """
        return self.get(query.xml(), str)

    def info(self, feature, what):
        """Get XML information of a feature node.

        Parameters
        ----------
        feature : str
            Name of the feature to query.
        what : str
            Name of the XML child to query.

        Returns
        -------
        str
        """
        return self.get(query.info(feature, what), str)

    def declared(self):
        """Get the list of declared virtual user features.

        Returns
        -------
        list
        """
        return self.get(query.declared(), list)

class SystemModule(_Module):
    pass
class InterfaceModule(_Module):
    pass
class DeviceModule(_Module):
    pass
class StreamModule(_Module):
    pass
class RemoteModule(_Module):
    pass


@six.add_metaclass(utils.FinalClass)
class EGrabberGenICam(object):
    """An object that encapsulates a set of related GenTL modules
    (an interface, a device, a data stream, a remote device).

    -   An InterfaceModule: the module that represents global (shared) frame
        grabber settings and features. This includes digital I/O control, PCIe
        and firmware status...
    -   A DeviceModule (or local device, as opposed to remote device): the
        module that contains the frame grabber settings and features relating
        to the camera. This consists mainly of camera and illumination control
        features: strobes, triggers...
    -   A StreamModule: the module that handles image buffers.
    -   A RemoteModule: the CoaXPress camera.

    Attributes
    ----------
    system : SystemModule
    interface: InterfaceModule
    device : DeviceModule
    remote : StreamModule
    stream : RemoteModule
    """

    def __init__(self, grabber, ix):
        c_ix = ct.c_int(ix)
        self.grabber = grabber
        self.c_system_port = ct.c_void_p()
        self.c_interface_port = ct.c_void_p()
        self.c_device_port = ct.c_void_p()
        self.c_remote_port = ct.c_void_p()
        self.c_stream_port = ct.c_void_p()
        cE.Eur_EGrabber_CallbackOnDemand_getSystemPort__from__int(grabber._box, c_ix, ct.byref(self.c_system_port))
        cE.Eur_EGrabber_CallbackOnDemand_getInterfacePort__from__int(grabber._box, c_ix, ct.byref(self.c_interface_port))
        cE.Eur_EGrabber_CallbackOnDemand_getDevicePort__from__int(grabber._box, c_ix, ct.byref(self.c_device_port))
        cE.Eur_EGrabber_CallbackOnDemand_getRemotePort__from__int(grabber._box, c_ix, ct.byref(self.c_remote_port))
        cE.Eur_EGrabber_CallbackOnDemand_getStreamPort__from__int(grabber._box, c_ix, ct.byref(self.c_stream_port))
        self.system = SystemModule(grabber, self.c_system_port) if self.c_system_port else None
        self.interface = InterfaceModule(grabber, self.c_interface_port) if self.c_interface_port else None
        self.device = DeviceModule(grabber, self.c_device_port) if self.c_device_port else None
        self.remote = RemoteModule(grabber, self.c_remote_port) if self.c_remote_port else None
        self.stream = StreamModule(grabber, self.c_stream_port) if self.c_stream_port else None

    def __repr__(self):
        gid = []
        if self.system:
            gid.append(self.system.get('TLID', str))
            if self.interface:
                gid.append(self.interface.get('InterfaceID', str))
                if self.device:
                    gid.append(self.device.get('DeviceID', str))
                    if self.stream:
                        gid.append(self.stream.get('StreamID', str))
        return '/'.join(gid)

    def run_script(self, script):
        """Run a Euresys GenApi script.

        Parameters
        ----------
        script : str
            Euresys GenApi script to run.
            This can be either a location (path) or some actual script statements
            (cf. EGenTL::genapiRunScript).
        """

        if self.c_stream_port:
            port_handle = self.c_stream_port
        elif self.c_device_port:
            port_handle = self.c_device_port
        elif self.c_interface_port:
            port_handle = self.c_interface_port
        else:
            port_handle = self.c_system_port
        cE.Eur_EGenTL_genapiRunScript__from__PORT_HANDLE__const_char_p(self.grabber.gentl._box, port_handle, utils.to_cstr(script))


@six.add_metaclass(utils.FinalClass)
class EGrabber(object):
    """An EGrabber object encapsulates a set of related GenTL modules
    (an interface, a device, a data stream, a remote device, and a number of buffers).

    -   An InterfaceModule: the module that represents global (shared) frame
        grabber settings and features. This includes digital I/O control, PCIe
        and firmware status...
    -   A DeviceModule (or local device, as opposed to remote device): the
        module that contains the frame grabber settings and features relating
        to the camera. This consists mainly of camera and illumination control
        features: strobes, triggers...
    -   A StreamModule: the module that handles image buffers.
    -   A RemoteModule: the CoaXPress camera.
    -   A number of buffers.

    Attributes
    ----------
    gentl : EGenTL
    system : SystemModule
    interface: InterfaceModule
    device : DeviceModule
    remote : StreamModule
    stream : RemoteModule

    Notes
    -----
    - EGrabber is only available as CallbackOnDemand model.
    """

    def __init__(self, data, interface=0, device=0, data_stream=0,
            device_open_flags=DEVICE_ACCESS_CONTROL,
            remote_required=True):
        """Create an EGrabber object with CallbackOnDemand model.

        Parameters
        ----------
        data : EGenTL, EGrabberInfo, EGrabberCameraInfo
            - When data is an instance of EGenTL
                create a grabber from GenTL module indexes.
            - When data is an instance of EGrabberInfo
                create a grabber from a discovered grabber
            - When data is an instance of EGrabberCameraInfo
                create a grabber from a discovered camera
        interface : int, default=0
            Index of the InterfaceModule to use. If None, module is not used.
            Only used when data is an instance of EGenTL.
        device : int, default=0
            Index of the DeviceModule to use. If None, module is not used.
            Only used when data is an instance of EGenTL.
        data_stream : int, default=0
            Index of of the StreamModule to use. If None, module is not used.
            Only used when data is an instance of EGenTL.
        device_open_flags : int (DEVICE_ACCESS_FLAGS), default=DEVICE_ACCESS_CONTROL
            How the device is to be opened.
        remote_required : bool, default=True
            Whether the remote device is required to create the grabber.
            Only used when data is an instance of EGenTL or EGrabberInfo.
        """
        is_gentl = isinstance(data, egentl.EGenTL)
        is_grabber_info = isinstance(data, discovery.EGrabberInfo)
        is_camera_info = isinstance(data, discovery.EGrabberCameraInfo)
        if not any([is_gentl, is_grabber_info, is_camera_info]):
            raise TypeError('Invalid data type %s' % type(data))
        self._box = cE.Eur_EGrabber_CallbackOnDemand()
        try:
            if is_gentl:
                if interface is None:
                    interface = -1
                if device is None:
                    device = -1
                if data_stream is None:
                    data_stream = -1
                gentl = data
                cE.Eur_EGrabber_CallbackOnDemand_create__from__Eur_EGenTL__int__int__int__DEVICE_ACCESS_FLAGS__bool8_t(
                    gentl._box, ct.c_int32(interface), ct.c_int32(device), ct.c_int32(data_stream), ct.c_int32(device_open_flags),
                    ct.c_ubyte(remote_required), ct.byref(self._box))
                self._len_grabbers = 1
            elif is_grabber_info:
                gentl = data.gentl
                cE.Eur_EGrabber_CallbackOnDemand_create__from__Eur_EGrabberInfo__DEVICE_ACCESS_FLAGS__bool8_t(
                    data._box, ct.c_int32(device_open_flags), ct.c_ubyte(remote_required), ct.byref(self._box))
                self._len_grabbers = 1
            else: # is_camera_info:
                gentl = data.gentl
                cE.Eur_EGrabber_CallbackOnDemand_create__from__Eur_EGrabberCameraInfo__DEVICE_ACCESS_FLAGS(
                    data._box, ct.c_int32(device_open_flags), ct.byref(self._box))
                self._len_grabbers = len(data.grabbers)
        except:
            self._box = None
            raise
        self.gentl = gentl
        self.system = SystemModule(self) if self._has_system() else None
        self.interface = InterfaceModule(self) if self._has_interface() else None
        self.device = DeviceModule(self) if self._has_device() else None
        self.remote = RemoteModule(self) if self._has_remote() else None
        self.stream = StreamModule(self) if self._has_stream() else None
        self._wr = utils.WeakRefBox(self, '_box', '_shutdown')
        self._callback_failures = {}
        self._contexts = {}

    def __del__(self):
        if self._box is not None:
            cE.Eur_EGrabber_CallbackOnDemand_destroy(self._box)

    def __repr__(self):
        gid = []
        if self.system:
            gid.append(self.system.get('TLID', str))
            if self.interface:
                gid.append(self.interface.get('InterfaceID', str))
                if self.device:
                    gid.append(self.device.get('DeviceID', str))
                    if self.stream:
                        gid.append(self.stream.get('StreamID', str))
        return '/'.join(gid)

    def realloc_buffers(self, buffer_count, buffer_size=None):
        """Reallocates the buffers.

        realloc_buffers performs the following operations:
            - revoke current buffers (if any);
            - allocate bufferCount buffers (if bufferSize is zero, the size is;
              determined automatically);
            - announce the new buffers to the data stream;
            - queue the new buffers to the data stream input fifo.

        Parameters
        ----------
        buffer_count : int
        buffer_size : int, optional
            If buffer_size is zero, the size is determined automatically.

        Returns
        -------
        bir : BufferIndexRange
            Range of allocated buffer indexes.

        Notes
        -----
        - realloc_buffers invalidates all buffer indexes.
        """
        if buffer_size is None:
            buffer_size = 0
        bir = BufferIndexRange()
        cE.Eur_EGrabber_CallbackOnDemand_reallocBuffers__from__size_t__size_t(
            self._box, ct.c_size_t(buffer_count), ct.c_size_t(buffer_size),
            ct.byref(bir._box))
        return bir

    def announce_and_queue(self, memory, **kwargs):
        """Announce and queue a memory buffer from a GenTLMemory, UserMemory, BusMemory,
        NvidiaRdmaMemory or UserMemoryArray object.

        Parameters
        ----------
        memory : GenTLMemory, UserMemory, BusMemory, NvidiaRdmaMemory or UserMemoryArray
            Objet containing the memory buffer information.
        **kwargs : dict, optional
            buffer_count : int, default=1
                Only valid when memory is an instance of GenTLMemory.
                Number of GenTLMemory buffers to allocate, announce and queue.
            reverse : bool, default=False
                Only valid when memory is an instance of UserMemoryArray.
                Announce and queue the buffers of a UserMemoryArray object in reverse order.

        Returns
        -------
        bir : BufferIndexRange
            Range of announced buffer indexes.

        Notes
        -----
        - If memory is a GenTLMemory, the memory buffer is also allocated.
        """
        return memory._announce_and_queue(self, **kwargs)

    def flush_buffers(self, operation=ACQ_QUEUE_ALL_TO_INPUT):
        """Move buffers from/to specific data stream buffer queues (cf. ACQ_QUEUE_TYPE_LIST).

        Parameters
        ----------
        operation : int (ACQ_QUEUE_TYPE_LIST), default=ACQ_QUEUE_ALL_TO_INPUT
        """
        cE.Eur_EGrabber_CallbackOnDemand_flushBuffers__from__ACQ_QUEUE_TYPE(self._box, ct.c_int32(operation))

    def reset_buffer_queue(self, buffer_range=None):
        """Reset and queue a range of announced buffers.

        reset_buffer_queue performs the following operations:
            - discard pending buffers (if any);
            - queue the buffers of the given range to the data stream input fifo.
              If buffer_range is None, queue all buffers to the data stream input fifo,
              in the initial order (i.e., the order in which they were announced with
              realloc_buffers or announce_and_queue).

        Parameters
        ----------
        buffer_range : BufferIndexRange, optional

        Notes
        -----
        - The data stream must be idle when calling this function.
        """
        if buffer_range is None:
            cE.Eur_EGrabber_CallbackOnDemand_resetBufferQueue(self._box)
        else:
            cE.Eur_EGrabber_CallbackOnDemand_resetBufferQueue__from__Eur_BufferIndexRange(self._box, buffer_range._box)

    def queue(self, buffer_range):
        """Queue a range of announced buffers.

        Parameters
        ----------
        buffer_range : BufferIndexRange
        """
        cE.Eur_EGrabber_CallbackOnDemand_queue__from__Eur_BufferIndexRange(self._box, buffer_range._box)

    def revoke(self, buffer_range):
        """Revoke a range of announced buffers.

        Parameters
        ----------
        buffer_range : BufferIndexRange

        Notes
        -----
        - Revoke does not invalidate other buffer indexes.
        """
        cE.Eur_EGrabber_CallbackOnDemand_revoke__from__Eur_BufferIndexRange(self._box, buffer_range._box)

    def start(self, frame_count=GENTL_INFINITE, control_remote_device=True):
        """Start acquisitions.

        start performs the following operations:
            - if controlRemoteDevice is true, start the remote device by
              executing AcquisitionStart;
            - start the data stream for frameCount buffers.

        Parameters
        ----------
        frame_count : long, default=GENTL_INFINITE
            The number of buffers to fill.
        control_remote_device : bool, default=True
            Defines whether or not to start and stop the remote device by
            automatically executing AcquisitionStart and AcquisitionStop
            commands.

        Notes
        -----
        - The data stream must be idle when calling this function.
        - When frameCount buffers have been filled, the data stream
        automatically goes idle, but the remote device is not stopped.
        - If controlRemoteDevice is true, AcquisitionStop will be
        exectuted in a subsequent call to @ref stop (or in the EGrabber
        destructor).
        """
        cE.Eur_EGrabber_CallbackOnDemand_start__from__uint64_t__bool8_t(
            self._box, ct.c_uint64(frame_count), ct.c_ubyte(control_remote_device))

    def stop(self):
        """Stop acquisitions.

        stop performs the following operations:
        - stop the data stream;
        - stop the remote device.

        Notes
        -----
        - This function will block until the data stream is idle.
        """
        cE.Eur_EGrabber_CallbackOnDemand_stop(self._box)

    def _shutdown(self):
        cE.Eur_EGrabber_CallbackOnDemand_shutdown(self._box)

    def get_width(self):
        """Get the width (in pixels) of images produced by the grabber.

        Returns
        -------
        width : int
        """
        c_width = ct.c_size_t()
        cE.Eur_EGrabber_CallbackOnDemand_getWidth(self._box, ct.byref(c_width))
        return c_width.value

    def get_height(self):
        """Get the height (in lines) of images produced by the grabber.

        Returns
        -------
        height : int

        Notes
        -----
        - For line-scan cameras, the height is determined by the data stream
        feature "BufferHeight".
        """
        c_height = ct.c_size_t()
        cE.Eur_EGrabber_CallbackOnDemand_getHeight(self._box, ct.byref(c_height))
        return c_height.value

    def get_payload_size(self):
        """Get the payload size of images produced by the grabber.

        Returns
        -------
        payload_size : int
        """
        c_payload = ct.c_size_t()
        cE.Eur_EGrabber_CallbackOnDemand_getPayloadSize(self._box, ct.byref(c_payload))
        return c_payload.value

    def get_pixel_format(self):
        """Get the pixel format of images produced by the grabber.

        Returns
        -------
        pixel_format : str

        Notes
        -----
        - Both the camera and the data stream influence this.
        """
        with utils.Ctype.std_string() as pf:
            cE.Eur_EGrabber_CallbackOnDemand_getPixelFormat(self._box, ct.byref(pf.box))
            return pf.box_value

    _module_to_fn_prefix = {
        SystemModule.__name__:    'tl',
        InterfaceModule.__name__: 'if',
        DeviceModule.__name__:    'dev',
        StreamModule.__name__:    'ds'
    }

    _module_to_handle_name = {
        SystemModule.__name__:    'TL_HANDLE',
        InterfaceModule.__name__: 'IF_HANDLE',
        DeviceModule.__name__:    'DEV_HANDLE',
        StreamModule.__name__:    'DS_HANDLE'
    }

    _module_to_cmd_prefix = {
        SystemModule.__name__:    'TL_INFO_CMD',
        InterfaceModule.__name__: 'INTERFACE_INFO_CMD',
        DeviceModule.__name__:    'DEVICE_INFO_CMD',
        StreamModule.__name__:    'STREAM_INFO_CMD'
    }

    def _get_info(self, port_handle, module, cmd, info_datatype):
        if info_datatype is None:
            box = cE.Eur_InfoCommandInfo()
            if port_handle:
                funcname = 'Eur_EGenTL_{}GetInfo__as__InfoCommandInfo__from__{}__{}'.format(
                                EGrabber._module_to_fn_prefix[module.__name__],
                                EGrabber._module_to_handle_name[module.__name__],
                                EGrabber._module_to_cmd_prefix[module.__name__])
                getattr(cE, funcname)(self.gentl._box, port_handle, ct.c_int32(cmd), ct.byref(box))
            else:
                funcname = 'Eur_EGrabber_CallbackOnDemand_getInfo__as__InfoCommandInfo__on__{}__from__int32_t'.format(module.__name__)
                getattr(cE, funcname)(self._box, ct.c_int32(cmd), ct.byref(box))
            dt = ct.c_int()
            cE.Eur_InfoCommandInfo_get_dataType(box, ct.byref(dt))
            info_datatype = dt.value
        with utils.Ctype.from_info_datatype(info_datatype) as info:
            if port_handle:
                funcname = 'Eur_EGenTL_{}GetInfo__as__{}__from__{}__{}'.format(
                                EGrabber._module_to_fn_prefix[module.__name__],
                                info.ctypename,
                                EGrabber._module_to_handle_name[module.__name__],
                                EGrabber._module_to_cmd_prefix[module.__name__])
                getattr(cE, funcname)(self.gentl._box, port_handle, ct.c_int32(cmd), ct.byref(info.box))
            else:
                funcname = 'Eur_EGrabber_CallbackOnDemand_getInfo__as__{}__on__{}__from__int32_t'.format(info.ctypename, module.__name__)
                getattr(cE, funcname)(self._box, ct.c_int32(cmd), ct.byref(info.box))
            return info.box_value

    def get_buffer_info(self, buffer_index, cmd, info_datatype=None):
        """Get information of buffer at index bufferIndex.

        Parameters
        ----------
        buffer_index : int
            The index of the buffer to query (cf. BufferIndexRange).
        cmd : int (BUFFER_INFO_CMD)
            Command value (cf. GenTL::BUFFER_INFO_CMD_LIST).
        info_datatype : int (INFO_DATATYPE), optional
            Type of data to get (cf. GenTL::INFO_DATATYPE_LIST).

        Returns
        -------
        buffer_info : int, bool, float or str
        """
        if info_datatype is None:
            box = cE.Eur_InfoCommandInfo()
            cE.Eur_EGrabber_CallbackOnDemand_getBufferInfo__as__InfoCommandInfo__from__size_t__BUFFER_INFO_CMD(
                self._box, ct.c_size_t(buffer_index), ct.c_int32(cmd), ct.byref(box))
            dt = ct.c_int()
            cE.Eur_InfoCommandInfo_get_dataType(box, ct.byref(dt))
            info_datatype = dt.value
        with utils.Ctype.from_info_datatype(info_datatype) as info:
            funcname = 'Eur_EGrabber_CallbackOnDemand_getBufferInfo__as__{}__from__size_t__BUFFER_INFO_CMD'.format(info.ctypename)
            getattr(cE, funcname)(self._box, ct.c_size_t(buffer_index), ct.c_int32(cmd), ct.byref(info.box))
            return info.box_value

    def get_buffer_data(self, buffer_index):
        """Get handle details of buffer at index buffer_index.

        Parameters
        ----------
        buffer_index : int
            The index of the buffer to query (cf. BufferIndexRange).

        Returns
        -------
        buffer_data : NewBufferData
        """
        c_nbd = cE.Eur_NewBufferData()
        cE.Eur_EGrabber_CallbackOnDemand_getBufferData__from__size_t(self._box, ct.c_size_t(buffer_index), ct.byref(c_nbd))
        return NewBufferData._from_Eur_EventData(c_nbd)

    def _gc_read_port(self, port_handle, module, address, size):
        data = (ct.c_char * size)()
        if port_handle:
            funcname = 'Eur_EGenTL_gcReadPortData__from__PORT_HANDLE__uint64_t__void_p__size_t'
            getattr(cE, funcname)(self.gentl._box, port_handle, ct.c_uint64(address), ct.byref(data), ct.c_size_t(size))
        else:
            funcname = 'Eur_EGrabber_CallbackOnDemand_gcReadPortData__on__{}__from__uint64_t__void_p__size_t'.format(module.__name__)
            getattr(cE, funcname)(self._box, ct.c_uint64(address), ct.byref(data), ct.c_size_t(size))
        return data

    def _gc_write_port(self, port_handle, module, address, data):
        size = len(data)
        if type(data).__name__.startswith('c_char_Array_'):
            c_data = data
        if isinstance(data, bytearray):
            c_data = (ct.c_char * size).from_buffer(data)
        elif isinstance(data, bytes):
            c_data = (ct.c_char * size).from_buffer_copy(data)
        else:
            raise TypeError('data must be ctypes.c_char_Array_, bytearray or bytes for write operation')
        if port_handle:
            funcname = 'Eur_EGenTL_gcWritePortData__from__PORT_HANDLE__uint64_t__void_p__size_t'
            getattr(cE, funcname)(self.gentl._box, port_handle, ct.c_uint64(address), c_data, ct.c_size_t(size))
        else:
            funcname = 'Eur_EGrabber_CallbackOnDemand_gcWritePortData__on__{}__from__uint64_t__void_p__size_t'.format(module.__name__)
            getattr(cE, funcname)(self._box, ct.c_uint64(address), c_data, ct.c_size_t(size))

    def _gc_read_port_value(self, port_handle, module, address, ctype):
        with utils.Ctype(ctype) as value:
            if port_handle:
                funcname = 'Eur_EGenTL_gcReadPortData__from__PORT_HANDLE__uint64_t__void_p__size_t'
                getattr(cE, funcname)(self.gentl._box, port_handle, ct.c_uint64(address), ct.byref(value.box), ct.c_size_t(ct.sizeof(ctype)))
            else:
                funcname = 'Eur_EGrabber_CallbackOnDemand_gcReadPortValue__as__{}__on__{}__from__uint64_t'.format(value.ctypename, module.__name__)
                getattr(cE, funcname)(self._box, ct.c_uint64(address), ct.byref(value.box))
            return value.box_value

    def _gc_write_port_value(self, port_handle, module, address, ctype, value):
        if port_handle:
            funcname = 'Eur_EGenTL_gcWritePortData__from__PORT_HANDLE__uint64_t__void_p__size_t'
            getattr(cE, funcname)(self.gentl._box, port_handle, ct.c_uint64(address), ct.byref(ctype(value)), ct.c_size_t(ct.sizeof(ctype)))
        else:
            funcname = 'Eur_EGrabber_CallbackOnDemand_gcWritePortValue__with__{0}__on__{1}__from__uint64_t__{0}'.format(utils.Ctype.to_attr[ctype][0], module.__name__)
            getattr(cE, funcname)(self._box, ct.c_uint64(address), ctype(value))

    def _gc_read_port_string(self, port_handle, module, address, size):
        with utils.Ctype.std_string() as s:
            if port_handle:
                funcname = 'Eur_EGenTL_gcReadPortString__from__PORT_HANDLE__uint64_t__size_t'
                getattr(cE, funcname)(self.gentl._box, port_handle, ct.c_uint64(address), ct.c_size_t(size), ct.byref(s.box))
            else:
                funcname = 'Eur_EGrabber_CallbackOnDemand_gcReadPortString__on__{}__from__uint64_t__size_t'.format(module.__name__)
                getattr(cE, funcname)(self._box, ct.c_uint64(address), ct.c_size_t(size), ct.byref(s.box))
            return s.box_value

    def run_script(self, script):
        """Run a Euresys GenApi script.

        Parameters
        ----------
        script : str
            Euresys GenApi script to run.
            This can be either a location (path) or some actual script statements
            (cf. EGenTL::genapiRunScript).
        """
        cE.Eur_EGrabber_CallbackOnDemand_runScript__from__const_char_p(
            self._box, utils.to_cstr(script))

    def interrupt_script(self, script_id):
        """Interrupt the execution of a running Euresys GenApi script.

        Parameters
        ----------
        script_id : str
            Identifier of the script to interrupt. It is returned by the user
            interface callback with operation "scriptid" and parameter name "id"
            (cf. EGenTL::genapiInterruptScript).

        Pre
        ---
        interrupt_script cannot be called from the user interface callback
        """
        cE.Eur_EGrabber_CallbackOnDemand_interruptScript__from__const_char_p(
            self._box, utils.to_cstr(script_id))

    def memento(self, text, verbosity=MEMENTO_VERBOSITY_INFO, kind=0):
        """Output text to Memento with specified verbosity and user kind.

        Parameters
        ----------
        text : str
            String to output.
        verbosity : int, default=MEMENTO_VERBOSITY_INFO
            - MEMENTO_VERBOSITY_CRITICAL
            - MEMENTO_VERBOSITY_ERROR
            - MEMENTO_VERBOSITY_WARNING
            - MEMENTO_VERBOSITY_NOTICE
            - MEMENTO_VERBOSITY_INFO
            - MEMENTO_VERBOSITY_DEBUG
            - MEMENTO_VERBOSITY_VERBOSE
        kind : int, default=0
            User kind identifier, from 0 to 15.
            - 0 to output trace under the Kind "User0"
            - 1 to output trace under the Kind "User1"
            - ...
            - 10 (0xA) to output trace under the Kind "UserA"
            - 11 (0xB) to output trace under the Kind "UserB"
            - 12 (0xC) to output trace under the Kind "UserC"
            - 13 (0xD) to output trace under the Kind "UserD"
            - 14 (0xE) to output trace under the Kind "UserE"
            - 15 (0xF) to output trace under the Kind "UserF"
        """
        cE.Eur_EGrabber_CallbackOnDemand_memento__from__unsigned_char__unsigned_char__const_char_p(
            self._box, ct.c_ubyte(verbosity), ct.c_ubyte(kind), utils.to_cstr(text))

    def memento_wave_up(self, id, kind=0):
        """Inject a user analyzer event UP into the memento logging system.

        UP has a "+1" semantic on the user wave form of the analyzer event specified by id.
        The id values from 0 to 15 are mapped onto "UserWave0" to "UserWaveF"
        The display name of these 15 user analyzer events can be changed in the Analyzer Configurator
        panel of the Memento application using the Alias property found in the Advanced tab of
        the Analyzer Configurator panel.

        Parameters
        ----------
        id : int
            User analyzer event identifier, from 0 to 15, mapped onto "UserWave0" to "UserWaveF"
        kind : int
            User kind identifier, from 0 to 15, mapped onto "User0" to "UserF"
        """
        cE.Eur_EGrabber_CallbackOnDemand_mementoWaveUp__from__unsigned_char__unsigned_char(
            self._box, ct.c_ubyte(kind), ct.c_ubyte(id))

    def memento_wave_down(self, id, kind=0):
        """Inject a user analyzer event DOWN into the memento logging system.

        DOWN has a "-1" semantic on the user wave form of the analyzer event specified by id.
        The id values from 0 to 15 are mapped onto "UserWave0" to "UserWaveF"
        The display name of these 15 user analyzer events can be changed in the Analyzer Configurator
        panel of the Memento application using the Alias property found in the Advanced tab of
        the Analyzer Configurator panel.

        Parameters
        ----------
        id : int
            User analyzer event identifier, from 0 to 15, mapped onto "UserWave0" to "UserWaveF"
        kind : int
            User kind identifier, from 0 to 15, mapped onto "User0" to "UserF"
        """
        cE.Eur_EGrabber_CallbackOnDemand_mementoWaveDown__from__unsigned_char__unsigned_char(
            self._box, ct.c_ubyte(kind), ct.c_ubyte(id))

    def memento_wave_reset(self, id, kind=0):
        """Inject a user analyzer event RESET into the memento logging system.

        RESET has a "reset to 0" semantic on the user wave form of the analyzer event specified by id.
        The id values from 0 to 15 are mapped onto "UserWave0" to "UserWaveF"
        The display name of these 15 user analyzer events can be changed in the Analyzer Configurator
        panel of the Memento application using the Alias property found in the Advanced tab of
        the Analyzer Configurator panel.

        Parameters
        ----------
        id : int
            User analyzer event identifier, from 0 to 15, mapped onto "UserWave0" to "UserWaveF"
        kind : int
            User kind identifier, from 0 to 15, mapped onto "User0" to "UserF"
        """
        cE.Eur_EGrabber_CallbackOnDemand_mementoWaveReset__from__unsigned_char__unsigned_char(
            self._box, ct.c_ubyte(kind), ct.c_ubyte(id))

    def memento_wave_value(self, id, value, kind=0):
        """Inject a user analyzer event VALUE into the memento logging system.

        VALUE has a "set to value" semantic on the user wave form of the analyzer event specified by id.
        The id values from 0 to 15 are mapped onto "UserWaveValue0" to "UserWaveValueF"
        The display name of these 15 user analyzer events can be changed in the Analyzer Configurator
        panel of the Memento application using the Alias property found in the Advanced tab of
        the Analyzer Configurator panel.

        Parameters
        ----------
        id : int
            User analyzer event identifier, from 0 to 15, mapped onto "UserWaveValue0" to "UserWaveValueF"
        value : int
            Value of the analyzer event
        kind : int
            User kind identifier, from 0 to 15, mapped onto "User0" to "UserF"
        """
        cE.Eur_EGrabber_CallbackOnDemand_mementoWaveValue__from__unsigned_char__unsigned_char__uint64_t(
            self._box, ct.c_ubyte(kind), ct.c_ubyte(id), ct.c_uint64(value))

    def memento_wave_no_value(self, id, kind=0):
        """Inject a user analyzer event NOVALUE into the memento logging system.

        NOVALUE has a "disable value" semantic on the user wave form of the analyzer event specified by id.
        The id values from 0 to 15 are mapped onto "UserWaveValue0" to "UserWaveValueF"
        The display name of these 15 user analyzer events can be changed in the Analyzer Configurator
        panel of the Memento application using the Alias property found in the Advanced tab of
        the Analyzer Configurator panel.

        Parameters
        ----------
        id : int
            User analyzer event identifier, from 0 to 15, mapped onto "UserWaveValue0" to "UserWaveValueF"
        kind : int
            User kind identifier, from 0 to 15, mapped onto "User0" to "UserF"
        """
        cE.Eur_EGrabber_CallbackOnDemand_mementoWaveNoValue__from__unsigned_char__unsigned_char(
            self._box, ct.c_ubyte(kind), ct.c_ubyte(id))

    def pop(self, timeout=GENTL_INFINITE):
        """Return a NewBufferData object (to be given to ScopedBuffer or Buffer).

        Parameters
        ----------
        timeout : int, default=GENTL_INFINITE
            Timeout in milliseconds.

        Returns
        -------
        buffer_data : NewBufferData

        Pre
        ---
        - NewBufferData event is enabled (this is the default);
        """
        c_nbd = cE.Eur_NewBufferData()
        cE.Eur_EGrabber_CallbackOnDemand_pop__from__uint64_t(
            self._box, ct.c_uint64(timeout), ct.byref(c_nbd))
        return NewBufferData._from_Eur_EventData(c_nbd)

    def pop_one_of(self, events='Any', timeout=GENTL_INFINITE):
        """Return a tuple with the oldest event from a series of requested
        events and the number of pending events.

        Parameters
        ----------
        events : list[class], default='Any'
            - NewBufferData
            - IoToolboxData
            - CicData
            - DataStreamData
            - CxpInterfaceData
            - DeviceErrorData
            - CxpDeviceData
            - RemoteDeviceData
        timeout : int
            Timeout in milliseconds.

        Returns
        -------
        (data, pending) : (class, int)
            event data and the number of pending events of the requested type

        Pre
        ---
        - Requested events are enabled.
        """
        allEvents = [globals()[e] for e in cE.Euresys_AllEventNames]
        if type(events) is not list:
            events = [events]
        if 'Any' in events:
            events = allEvents
        filter = EGrabber._events_to_value(events)
        c_oneof = cE.Eur_OneOfAll()
        cE.Eur_OneOfAll_create(ct.byref(c_oneof))
        try:
            c_position = ct.c_int()
            c_num_in_queue = ct.c_size_t()
            cE.Eur_EGrabber_CallbackOnDemand_popEventFilter__from__size_t__uint64_t__Eur_OneOfAll__int_p(
                self._box, ct.c_size_t(filter), ct.c_uint64(timeout), c_oneof, ct.byref(c_position), ct.byref(c_num_in_queue))
            position = c_position.value
            eventcls = allEvents[position - 1]
            c_data = getattr(cE, 'Eur_{}'.format(eventcls.__name__))()
            getattr(cE, 'Eur_OneOfAll_at_position_{}'.format(position))(c_oneof, ct.byref(c_data))
            return (eventcls._from_Eur_EventData(c_data), c_num_in_queue.value)
        finally:
            cE.Eur_OneOfAll_destroy(c_oneof)

    def _get(self, port_handle, module, feature, dtype=None):
        # Auto assignment of dtype
        if dtype is None:
            feature_type = feature.split()[0] # check type of feature to determine dtype
            interfaces = self._get(port_handle, module, query.interfaces(feature_type), list)
            if not interfaces:
                raise TypeError("No interface found for feature '{}' in {} module."\
                                .format(feature_type, module))
            elif 'IInteger' in interfaces:
                dtype = int
            elif 'IFloat' in interfaces:
                dtype = float
            # return bool when these queries are used
            elif 'IBoolean' in interfaces \
            or feature_type in ('@available', '@readable', '@writeable',
                                '@implemented', '@command', '@done'):
                dtype = bool
            # return list when these queries are used
            elif feature_type in ('@features', '@!features', '@categories', '@!categories',
                                  '@ee', '@!ee', '@interfaces', '@selectors', '@declared'):
                dtype = list
            elif 'IString' in interfaces:
                dtype = str
            elif 'IRegister' in interfaces:
                size = self._get(port_handle, module, feature + ".Length", int)
                dtype = c_char * size;
            else: # fallback to str
                dtype = str

        if port_handle:
            funcname = 'Eur_EGenTL_genapiGet{}__from__PORT_HANDLE__const_char_p'
        else:
            funcname = 'Eur_EGrabber_CallbackOnDemand_get{}__on__{}__from__const_char_p'
        if dtype in (int, bool):
            c_value = ct.c_int64()
            if port_handle:
                funcname = funcname.format('Integer')
                getattr(cE, funcname)(self.gentl._box, port_handle, utils.to_cstr(feature), ct.byref(c_value))
            else:
                funcname = funcname.format('Integer', module.__name__)
                getattr(cE, funcname)(self._box, utils.to_cstr(feature), ct.byref(c_value))
            if dtype == bool:
                return bool(c_value.value)
            val = c_value.value
        elif dtype == float:
            c_value = ct.c_double()
            if port_handle:
                funcname = funcname.format('Float')
                getattr(cE, funcname)(self.gentl._box, port_handle, utils.to_cstr(feature), ct.byref(c_value))
            else:
                funcname = funcname.format('Float', module.__name__)
                getattr(cE, funcname)(self._box, utils.to_cstr(feature), ct.byref(c_value))
            val = c_value.value
        elif dtype in (str, list):
            tmp_str = cE.std_string()
            if port_handle:
                funcname = funcname.format('String')
                getattr(cE, funcname)(self.gentl._box, port_handle, utils.to_cstr(feature), ct.byref(tmp_str))
            else:
                funcname = funcname.format('String', module.__name__)
                getattr(cE, funcname)(self._box, utils.to_cstr(feature), ct.byref(tmp_str))
            val = utils.from_std_string(tmp_str)
            if dtype == list:
                val = val.split('\n') if val else []
            cE.std_string_destroy(tmp_str)
        elif dtype.__name__.startswith('c_char_Array_'):
            c_buffer = dtype()
            funcname += '__void_p__size_t'
            if port_handle:
                funcname = funcname.format('Register')
                getattr(cE, funcname)(self.gentl._box, port_handle, utils.to_cstr(feature), ct.byref(c_buffer), ct.c_size_t(ct.sizeof(c_buffer)))
            else:
                funcname = funcname.format('Register', module.__name__)
                getattr(cE, funcname)(self._box, utils.to_cstr(feature), ct.byref(c_buffer), ct.c_size_t(ct.sizeof(c_buffer)))
            val = c_buffer
        else:
            raise TypeError('dtype must be int, float, str, list, (c_char * N) or None.')

        return val

    def _set(self, port_handle, module, feature, value):
        if port_handle:
            funcname = 'Eur_EGenTL_genapiSet{}__from__PORT_HANDLE__const_char_p__{}'
        else:
            funcname = 'Eur_EGrabber_CallbackOnDemand_set{}__on__{}__from__const_char_p__{}'
        dtype = type(value)
        if dtype in six.integer_types + (bool,):
            if port_handle:
                funcname = funcname.format('Integer', 'int64_t')
                getattr(cE, funcname)(self.gentl._box, port_handle, utils.to_cstr(feature), ct.c_int64(value))
            else:
                funcname = funcname.format('Integer', module.__name__, 'int64_t')
                getattr(cE, funcname)(self._box, utils.to_cstr(feature), ct.c_int64(value))
        elif dtype == float:
            if port_handle:
                funcname = funcname.format('Float', 'double')
                getattr(cE, funcname)(self.gentl._box, port_handle, utils.to_cstr(feature), ct.c_double(value))
            else:
                funcname = funcname.format('Float', module.__name__, 'double')
                getattr(cE, funcname)(self._box, utils.to_cstr(feature), ct.c_double(value))
        elif dtype in (str, six.text_type):
            if port_handle:
                funcname = funcname.format('String', 'const_char_p')
                getattr(cE, funcname)(self.gentl._box, port_handle, utils.to_cstr(feature), utils.to_cstr(value))
            else:
                funcname = funcname.format('String', module.__name__, 'const_char_p')
                getattr(cE, funcname)(self._box, utils.to_cstr(feature), utils.to_cstr(value))
        elif dtype.__name__.startswith('c_char_Array_'):
            if port_handle:
                funcname = funcname.format('Register', 'void_p__size_t')
                getattr(cE, funcname)(self.gentl._box, port_handle, utils.to_cstr(feature), ct.byref(value), ct.c_size_t(ct.sizeof(value)))
            else:
                funcname = funcname.format('Register', module.__name__, 'void_p__size_t')
                getattr(cE, funcname)(self._box, utils.to_cstr(feature), ct.byref(value), ct.c_size_t(ct.sizeof(value)))
        else:
            raise TypeError('value must be int, float, str, bool or (c_char * N).')

    def _execute(self, port_handle, module, command):
        if port_handle:
            funcname = 'Eur_EGenTL_genapiExecuteCommand__from__PORT_HANDLE__const_char_p'
            getattr(cE, funcname)(self.gentl._box, port_handle, utils.to_cstr(command))
        else:
            funcname = 'Eur_EGrabber_CallbackOnDemand_execute__on__{}__from__const_char_p'.format(module.__name__)
            getattr(cE, funcname)(self._box, utils.to_cstr(command))

    def _attach_event(self, port_handle, module, event_id, event_data=None):
        size = len(event_data) if event_data is not None else 0
        if port_handle:
            funcname = 'Eur_EGenTL_genapiAttachEvent__from__PORT_HANDLE__uint64_t__void_p__size_t'
            getattr(cE, funcname)(self.gentl._box, port_handle, ct.c_uint64(event_id), event_data, ct.c_size_t(size))
        else:
            funcname = 'Eur_EGrabber_CallbackOnDemand_attachEvent__on__{}__from__uint64_t__void_p__size_t'.format(module.__name__)
            getattr(cE, funcname)(self._box, ct.c_uint64(event_id), event_data, ct.c_size_t(size))

    def _invalidate(self, port_handle, module, feature):
        if port_handle:
            funcname = 'Eur_EGenTL_genapiInvalidate__from__PORT_HANDLE__const_char_p'
            getattr(cE, funcname)(self.gentl._box, port_handle, utils.to_cstr(feature))
        else:
            funcname = 'Eur_EGrabber_CallbackOnDemand_invalidate__on__{}__from__const_char_p'.format(module.__name__)
            getattr(cE, funcname)(self._box, utils.to_cstr(feature))

    @staticmethod
    def _GenericEventCallback(box, ctx, event):
        pcontext = ct.cast(ctx, ct.py_object)
        egrabber = pcontext.value
        (callback, context) = egrabber._contexts[event]
        event_data = event._from_Eur_EventData(box)
        try:
            egrabber._callback_failures[threading.current_thread()] = None
            callback(egrabber, event_data, context)
        except:
            egrabber._callback_failures[threading.current_thread()] = sys.exc_info()

    @cE.Euresys_NewBufferEventCallback
    def _NewBufferEventCallback(_, box, ctx):
        EGrabber._GenericEventCallback(box, ctx, NewBufferData)

    @cE.Euresys_IoToolboxEventCallback
    def _IoToolboxEventCallback(_, box, ctx):
        EGrabber._GenericEventCallback(box, ctx, IoToolboxData)

    @cE.Euresys_CicEventCallback
    def _CicEventCallback(_, box, ctx):
        EGrabber._GenericEventCallback(box, ctx, CicData)

    @cE.Euresys_DataStreamEventCallback
    def _DataStreamEventCallback(_, box, ctx):
        EGrabber._GenericEventCallback(box, ctx, DataStreamData)

    @cE.Euresys_CxpInterfaceEventCallback
    def _CxpInterfaceEventCallback(_, box, ctx):
        EGrabber._GenericEventCallback(box, ctx, CxpInterfaceData)

    @cE.Euresys_DeviceErrorEventCallback
    def _DeviceErrorEventCallback(_, box, ctx):
        EGrabber._GenericEventCallback(box, ctx, DeviceErrorData)

    @cE.Euresys_CxpDeviceEventCallback
    def _CxpDeviceEventCallback(_, box, ctx):
        EGrabber._GenericEventCallback(box, ctx, CxpDeviceData)

    @cE.Euresys_RemoteDeviceEventCallback
    def _RemoteDeviceEventCallback(_, box, ctx):
        EGrabber._GenericEventCallback(box, ctx, RemoteDeviceData)

    def enable_event(self, event='All'):
        """Enable event handling for the specified events.

        Parameters
        ----------
        event : class, default='All'
            - NewBufferData
            - IoToolboxData
            - CicData
            - DataStreamData
            - CxpInterfaceData
            - DeviceErrorData
            - CxpDeviceData
            - RemoteDeviceData
        """
        self._do_event('enable', event)

    def disable_event(self, event='All'):
        """Disable event handling for the specified events.

        Parameters
        ----------
        event : class, default='All'
            - NewBufferData
            - IoToolboxData
            - CicData
            - DataStreamData
            - CxpInterfaceData
            - DeviceErrorData
            - CxpDeviceData
            - RemoteDeviceData
        """
        self._do_event('disable', event)

    def flush_event(self, event='All'):
        """Flush the event queue for the specified events.

        Parameters
        ----------
        event : class, default='All'
            - NewBufferData
            - IoToolboxData
            - CicData
            - DataStreamData
            - CxpInterfaceData
            - DeviceErrorData
            - CxpDeviceData
            - RemoteDeviceData
        """
        self._do_event('flush', event)

    _event_values = {}

    @staticmethod
    def _get_event_value(event):
        try:
            return EGrabber._event_values[event]
        except KeyError:
            eventName = EGrabber._get_event_data_name(event)
            funcname = 'Eur_getEventFilter__on__{}'.format(eventName)
            cevent = ct.c_size_t()
            getattr(cE, funcname)(ct.byref(cevent))
            EGrabber._event_values[event] = cevent.value
            return cevent.value

    @staticmethod
    def _events_to_value(events):
        eventValue = 0
        for event in events:
            if event in ['All', 'Any']:
                raise Exception('Invalid event type {}'.format(event))
            eventValue |= EGrabber._get_event_value(event)
        return eventValue

    def process_event(self, events='Any', timeout=GENTL_INFINITE):
        """Invoke the corresponding event callback.

        Parameters
        ----------
        events : list[class], default='Any'
            - NewBufferData
            - IoToolboxData
            - CicData
            - DataStreamData
            - CxpInterfaceData
            - DeviceErrorData
            - CxpDeviceData
            - RemoteDeviceData
        timeout : int, default=GENTL_INFINITE
            Timeout in milliseconds.

        Returns
        -------
        event_pending : int
            Number of pending events.
        """
        if type(events) is not list:
            events = [events]
        eventPending = ct.c_size_t()
        if 'Any' in events:
            cE.Eur_EGrabber_CallbackOnDemand_processEvent__with__Any__from__uint64_t(self._box, ct.c_uint64(timeout), ct.byref(eventPending))
        else:
            event = ct.c_size_t(EGrabber._events_to_value(events))
            cE.Eur_EGrabber_CallbackOnDemand_processEventFilter__from__size_t__uint64_t(self._box, event, ct.c_uint64(timeout), ct.byref(eventPending))
        tlsKey = threading.current_thread()
        if tlsKey in self._callback_failures and self._callback_failures[tlsKey] is not None:
            six.reraise(*self._callback_failures[threading.current_thread()])
        return eventPending.value

    def cancel_event(self, events='Any', timeout=GENTL_INFINITE):
        """Cancel a waiting process_event on corresponding events.

        Parameters
        ----------
        events : list[class], default='Any'
            - NewBufferData
            - IoToolboxData
            - CicData
            - DataStreamData
            - CxpInterfaceData
            - DeviceErrorData
            - CxpDeviceData
            - RemoteDeviceData
        timeout : int, default=GENTL_INFINITE
            Timeout in milliseconds.
        """
        if type(events) is not list:
            events = [events]
        if 'Any' in events:
            cE.Eur_EGrabber_CallbackOnDemand_cancelEvent__with__Any(self._box)
        else:
            event = ct.c_size_t(EGrabber._events_to_value(events))
            cE.Eur_EGrabber_CallbackOnDemand_cancelEventFilter__from__size_t(self._box, event)

    def get_pending_event_count(self, events='Any'):
        """Get the number of pending events in the different queues.

        Parameters
        ----------
        events : list[class], default='Any'
            - NewBufferData
            - IoToolboxData
            - CicData
            - DataStreamData
            - CxpInterfaceData
            - DeviceErrorData
            - CxpDeviceData
            - RemoteDeviceData
        """
        if type(events) is not list:
            events = [events]
        count = ct.c_size_t()
        if 'Any' in events:
            cE.Eur_EGrabber_CallbackOnDemand_getPendingEventCount__with__Any(self._box, ct.byref(count))
        else:
            event = ct.c_size_t(EGrabber._events_to_value(events))
            cE.Eur_EGrabber_CallbackOnDemand_getPendingEventCountFilter__from__size_t(self._box, event, ct.byref(count))
        return count.value

    def __setattr__(self, name, value):
        if name.startswith('on_') and name.endswith('_event'):
            words = name[3:-6].split('_')
            event = ''.join([word.capitalize() for word in words]) + 'Data'
            eventType = globals().get(event, None)
            if eventType is None:
                raise Exception('registering callback {} expects event type {} which does not exist'.format(name, event))
            eventType = globals()[event]
            self.register_callback(eventType, value)
        else:
            super(EGrabber, self).__setattr__(name, value)

    def register_callback(self, event, callback=None, context=None):
        """Register a callback for the specified events.

        Parameters
        ----------
        event : class
            - NewBufferData
            - IoToolboxData
            - CicData
            - DataStreamData
            - CxpInterfaceData
            - DeviceErrorData
            - CxpDeviceData
            - RemoteDeviceData
        callback : Callable[[EGrabber, EventData, Context], None], default=None
            None is used to unregister the callback.
            For NewBufferData, EventData contains:
                - dsh
                - bh
                - userPointer
                - timestamp
            A newBufferData can be used to instantiate Buffer.
            For RemoteDeviceData, EventData contains:
                - timestamp
                - eventId
                - data
            For the other events, EventData contains:
                - timestamp
                - numid
                - context1
                - context2
                - context3
        context : object, default=None
            Optional user-provided context.
        """
        eventName = EGrabber._get_event_data_name(event)
        callbackEvent = eventName[:-4] + 'Event'
        funcname = 'Eur_EGrabber_CallbackOnDemand_set{}Callback__from__Euresys_{}Callback__void_p'.format(callbackEvent, callbackEvent)
        callbackname = '_{}Callback'.format(callbackEvent)
        if callback is None:
            try:
                del self._contexts[event]
            except:
                pass
            getattr(cE, funcname)(self._box, 0, 0)
        else:
            cb = getattr(self, callbackname)
            self._contexts[event] = (callback, context)
            getattr(cE, funcname)(self._box, cb, ct.py_object(self))

    def _do_event(self, what, event):
        eventName = EGrabber._get_event_data_name(event)
        if event == 'Any':
            raise Exception('Invalid event type {}'.format(event))
        funcname = 'Eur_EGrabber_CallbackOnDemand_{}Event__with__{}'.format(what, eventName)
        getattr(cE, funcname)(self._box)

    @staticmethod
    def _get_event_data_name(event):
        if event in ['Any', 'All']:
            return event
        return event.__name__

    def _has_system(self):
        c_opened = ct.c_ubyte(0)
        cE.Eur_EGrabber_CallbackOnDemand_isOpen__on__SystemModule(self._box, ct.byref(c_opened))
        return bool(c_opened.value)

    def _has_interface(self):
        c_opened = ct.c_ubyte(0)
        cE.Eur_EGrabber_CallbackOnDemand_isOpen__on__InterfaceModule(self._box, ct.byref(c_opened))
        return bool(c_opened.value)

    def _has_device(self):
        c_opened = ct.c_ubyte(0)
        cE.Eur_EGrabber_CallbackOnDemand_isOpen__on__DeviceModule(self._box, ct.byref(c_opened))
        return bool(c_opened.value)

    def _has_stream(self):
        c_opened = ct.c_ubyte(0)
        cE.Eur_EGrabber_CallbackOnDemand_isOpen__on__StreamModule(self._box, ct.byref(c_opened))
        return bool(c_opened.value)

    def _has_remote(self):
        c_opened = ct.c_ubyte(0)
        cE.Eur_EGrabber_CallbackOnDemand_isOpen__on__RemoteModule(self._box, ct.byref(c_opened))
        return bool(c_opened.value)

    @property
    def last_event_grabber_index(self):
        """Grabber index of the last event received on the current thread."""
        c_index = ct.c_int()
        cE.Eur_EGrabber_CallbackOnDemand_getLastEventGrabberIndex(self._box, ct.byref(c_index))
        return c_index.value

    class _GetEGrabberGenICam(utils._EGrabberIterable):
        def __init__(self, grabber):
            self.grabber = grabber
        def __getitem__(self, ix):
            return EGrabberGenICam(self.grabber, ix)
        def __len__(self):
            return self.grabber._len_grabbers

    @property
    def grabbers(self):
        """Access the GenICam interface of a specific underlying grabber.

        Notes
        -----
            The property returns an object that needs to be indexed (by the
            index of an underlying grabber) to get access to an EGrabberGenICam
            instance wrapping the requested grabber.

            This is useful when the EGrabber instance is managing a camera
            composed by several remote devices and a remote device needs
            to be queried or configured independently.
        """
        return EGrabber._GetEGrabberGenICam(self)

    def should_reannounce_buffers(self):
        """Get an indication about the need to reconfigure internal resources like
        the DMA.

        In this case the already announced buffers need to be revoked and
        announced again otherwise some changes in the stream configuration
        like `StripeArrangement` would not be taken into account.
        """
        c_reannounce_buffers = ct.c_ubyte(0)
        cE.Eur_EGrabber_CallbackOnDemand_shouldReannounceBuffers(self._box, ct.byref(c_reannounce_buffers))
        return bool(c_reannounce_buffers.value)

    def should_realloc_buffers(self):
        """Get an indication about the need to reallocate buffers because the payload
        size or the alignment changed.

        In this case the already announced buffers need to be revoked and reallocated.
        """
        c_realloc_buffers = ct.c_ubyte(0)
        cE.Eur_EGrabber_CallbackOnDemand_shouldReallocBuffers(self._box, ct.byref(c_realloc_buffers))
        return bool(c_realloc_buffers.value)


class GenTLMemory:
    """Memory allocated by the GenTL producer.

    Attributes
    ----------
    buffer_size : int
    user_pointer : int
    """
    def __init__(self, buffer_size=0, user_pointer=None):
        """Create a GenTLMemory Object.

        Parameters
        ----------
        buffer_size : int, default=0
            When buffer_size = 0, a suitable buffer_size is evaluated.
        user_pointer : int, optional
            Optional pointer to private data (available in NewBufferData).
        """
        self.buffer_size = buffer_size
        self.user_pointer = user_pointer
        self._box = cE.Eur_GenTLMemory()
        cE.Eur_GenTLMemory_create__from__size_t__void_p(ct.c_size_t(buffer_size), ct.c_void_p(user_pointer), ct.byref(self._box))
    def __del__(self):
        cE.Eur_GenTLMemory_destroy(self._box)
    def _announce_and_queue(self, grabber, buffer_count=1):
        bir = BufferIndexRange()
        cE.Eur_EGrabber_CallbackOnDemand_announceAndQueue__from__Eur_GenTLMemory__size_t(grabber._box, self._box, ct.c_size_t(buffer_count), ct.byref(bir._box))
        return bir

class UserMemory:
    """Memory allocated by the user.

    Attributes
    ----------
    base : ctypes.c_char_Array_
        ctypes converted buffer that shares the same memory location as the user-provided buffer.
    size : int
        Size of the buffer.
    user_pointer : int
    """
    def __init__(self, buffer, user_pointer=None):
        """Create a UserMemory Object.

        Parameters
        ----------
        buffer : bytearray
            User-provided mutable buffer of bytes.
        user_pointer : int, optional
            Optional pointer to private data (available in NewBufferData).
        """
        self.size = len(buffer)
        self.base = (ct.c_char * self.size).from_buffer(buffer)
        self.user_pointer = user_pointer
        self._box = cE.Eur_UserMemory()
        cE.Eur_UserMemory_create__from__void_p__size_t__void_p(self.base, ct.c_size_t(self.size), ct.c_void_p(user_pointer), ct.byref(self._box))
    def __del__(self):
        cE.Eur_UserMemory_destroy(self._box)
    def _announce_and_queue(self, grabber):
        bir = BufferIndexRange()
        cE.Eur_EGrabber_CallbackOnDemand_announceAndQueue__from__Eur_UserMemory(grabber._box, self._box, ct.byref(bir._box))
        return bir

class BusMemory:
    """Bus addressable memory.

    Attributes
    ----------
    bus_address : int
    size : int
    user_pointer : int
    """
    def __init__(self, bus_address, size, user_pointer=None):
        """Create a BusMemory Object.

        Parameters
        ----------
        bus_address : int
            Bus buffer address on the PCIe bus.
        size : int
            Size of the buffer allocated by the user.
        user_pointer : int, optional
            Optional pointer to private data (available in NewBufferData).
        """
        self.bus_address = bus_address
        self.size = size
        self.user_pointer = user_pointer
        self._box = cE.Eur_BusMemory()
        cE.Eur_BusMemory_create__from__uint64_t__size_t__void_p(ct.c_uint64(bus_address), ct.c_size_t(size), ct.c_void_p(user_pointer), ct.byref(self._box))
    def __del__(self):
        cE.Eur_BusMemory_destroy(self._box)
    def _announce_and_queue(self, grabber):
        bir = BufferIndexRange()
        cE.Eur_EGrabber_CallbackOnDemand_announceAndQueue__from__Eur_BusMemory(grabber._box, self._box, ct.byref(bir._box))
        return bir

class NvidiaRdmaMemory:
    """NVIDIA Device memory to be translated to bus addressable memory

    Attributes
    ----------
    device_address : int
    size : int
    user_pointer : int
    """
    def __init__(self, device_address, size, user_pointer=None):
        """Create a NvidiaRdmaMemory Object.

        Parameters
        ----------
        device_address : int
            NVIDIA Device memory buffer address.
        size : int
            Size of the buffer allocated by the user.
        user_pointer : int, optional
            Optional pointer to private data (available in NewBufferData).
        """
        self.device_address = device_address
        self.size = size
        self.user_pointer = user_pointer
        self._box = cE.Eur_NvidiaRdmaMemory()
        cE.Eur_NvidiaRdmaMemory_create__from__void_p__size_t__void_p(ct.c_void_p(device_address), ct.c_size_t(size), ct.c_void_p(user_pointer), ct.byref(self._box))
    def __del__(self):
        cE.Eur_NvidiaRdmaMemory_destroy(self._box)
    def _announce_and_queue(self, grabber):
        bir = BufferIndexRange()
        cE.Eur_EGrabber_CallbackOnDemand_announceAndQueue__from__Eur_NvidiaRdmaMemory(grabber._box, self._box, ct.byref(bir._box))
        return bir

class UserMemoryArray:
    """UserMemory split into an array of contiguous buffers.

    Attributes
    ----------
    memory : UserMemory
    buffer_size : int
    """
    def __init__(self, memory, buffer_size):
        """Create an UserMemoryArray Object.

        Parameters
        ----------
        memory : UserMemory
            Memory allocated by the user to split into an array of contiguous buffers.
        buffer_size : int
            Size of buffers.

        Notes
        -----
        - Depending on the size of the user memory and the requested buffer size,
          the size of the last buffer of the array can be smaller than buffer_size,
          therefore we recommend to make sure that memory.size is a multiple of buffer_size.
        """
        self.memory = memory
        self.buffer_size = buffer_size
        self._box = cE.Eur_UserMemoryArray()
        cE.Eur_UserMemoryArray_create__from__Eur_UserMemory__size_t(memory._box, ct.c_size_t(buffer_size), ct.byref(self._box))
    def __del__(self):
        cE.Eur_UserMemoryArray_destroy(self._box)
    def _announce_and_queue(self, grabber, reverse=False):
        bir = BufferIndexRange()
        cE.Eur_EGrabber_CallbackOnDemand_announceAndQueue__from__Eur_UserMemoryArray__bool8_t(grabber._box, self._box, ct.c_ubyte(reverse), ct.byref(bir._box))
        return bir

class BufferIndexRange:
    """Range of buffer indexes returned by the EGrabber methods announcing buffers.

    Attributes
    ----------
    begin
    end
    reverse
    """

    def __init__(self):
        self._box = cE.Eur_BufferIndexRange()

    def __del__(self):
        cE.Eur_BufferIndexRange_destroy(self._box)

    def index_at(self, offset):
        """Convert a 0-based index in the range to an absolute buffer index.

        Parameters
        ----------
        offset : int
            0-based index of a buffer in the range.

        Returns
        -------
        index : int
        """
        value = ct.c_size_t()
        cE.Eur_BufferIndexRange_indexAt__from__size_t(self._box, ct.c_size_t(offset), ct.byref(value))
        return value.value

    def size(self):
        """Return the size of the range.

        Returns
        -------
        size : int
        """
        value = ct.c_size_t()
        cE.Eur_BufferIndexRange_size(self._box, ct.byref(value))
        return value.value

    def _get_data(self):
        c_begin = ct.c_size_t()
        c_end = ct.c_size_t()
        c_reverse = ct.c_ubyte()
        cE.from_box_Eur_BufferIndexRange__from__size_t_p__size_t_p__bool8_t_p(self._box, ct.byref(c_begin), ct.byref(c_end), ct.byref(c_reverse))
        return (c_begin.value, c_end.value, bool(c_reverse.value))

    @property
    def begin(self):
        """Index of the first buffer of the range."""
        b,_,_ = self._get_data()
        return b

    @property
    def end(self):
        """Index of the end of the range; the end is *not* included in the range."""
        _,e,_ = self._get_data()
        return e

    @property
    def reverse(self):
        """If the buffers have been queued in the reverse order."""
        _,_,r = self._get_data()
        return r


class _RawData(object):
    """Event data available in a callback event function.

    Attributes
    ----------
    timestamp : int
        Event timestamp.
    numid : int
        Custom event data identifier.
    context1 :
        Value of EventNotificationContext1 for this event (latched at the time the event occurred).
    context2 :
        Value of EventNotificationContext2 for this event (latched at the time the event occurred).
    context3 :
        Value of EventNotificationContext3 for this event (latched at the time the event occurred).
    """

    def __init__(self, data, box):
        for (name, _) in data._fields_:
            setattr(self, name, getattr(data, name))
        self._box = box

    def __del__(self):
        funcname = 'Eur_{}_destroy'.format(self.__class__.__name__)
        getattr(cE, funcname)(self._box)

    @classmethod
    def _from_Eur_EventData(cls, box):
        classname = 'Euresys_{}'.format(cls.__name__)
        pdata = ct.POINTER(getattr(cE, classname))()
        convname = 'Eur_{}__as__{}'.format(cls.__name__, classname)
        getattr(cE, convname)(box, ct.byref(pdata))
        return cls(pdata[0], box)

class NewBufferData(_RawData):
    """Event data available in a callback event function.

    Attributes
    ----------
    dsh : int
        Data stream handle associated to buffer.
    bh : int
        Buffer handle.
    userPointer : int
        Optional user pointer (if provided when announced).
    timestamp : int
        Timestamp associated to new buffer event.
    """
    pass
class IoToolboxData(_RawData):
    pass
class CicData(_RawData):
    pass
class DataStreamData(_RawData):
    pass
class CxpInterfaceData(_RawData):
    pass
class DeviceErrorData(_RawData):
    pass
class CxpDeviceData(_RawData):
    pass
class RemoteDeviceData(_RawData):
    """Event data available in a callback event function.

    Attributes
    ----------
    timestamp : int
        Event timestamp.
    eventNs : int
        Event namespace (cf. GenTL::EuresysCustomGenTL::EVENT_CUSTOM_REMOTE_DEVICE_NAMESPACE_LIST).
    eventId : int
        EventID of GenApi event.
    data : ctypes.c_ubyte_Array_1012
        Addressable data through the GenApi event port.
    """
    def __init__(self, data, box):
        super(RemoteDeviceData, self).__init__(data, box)
        self.data = ct.cast(self.data, ct.POINTER(ct.c_ubyte * self.size))[0]
        del self.size

class Buffer:
    """Buffer object encapsulating a GenTL buffer.

    Attributes
    ----------
    gentl : EGenTL
    grabber : EGrabber
    new_buffer_data : NewBufferData
    pixels
    """

    def __init__(self, grabber, new_buffer_data=None, timeout=GENTL_INFINITE):
        """Create a Buffer object.

        Parameters
        ----------
        grabber : EGrabber
            The grabber managing the underlying GenTL buffer.
        new_buffer_data : NewBufferData, optional
        timeout : int, default=GENTL_INFINITE
            Timeout in milliseconds.
        """
        self.grabber = grabber
        self.gentl = grabber.gentl
        if new_buffer_data is not None:
            self.new_buffer_data = new_buffer_data
        else:
            self.new_buffer_data = grabber.pop(timeout)
        self._box = cE.Eur_Buffer()
        cE.Eur_Buffer_create__from__Eur_NewBufferData(self.new_buffer_data._box, ct.byref(self._box))
        self._ic_in_p = None
        self._pixels = None

    def __del__(self):
        self._unload_buffer()

    def __enter__(self):
        """Return a Buffer within a with block. This Buffer will be pushed to the back
        of the data stream input fifo when exiting with block.
        """
        self.push = self.__nopush_in_with_block
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        """Push Buffer back to the data stream input fifo when exiting a with block."""
        cE.Eur_Buffer_push__from__Eur_EGrabberBase(self._box, self.grabber._box)
        self._unload_buffer()

    def _unload_buffer(self):
        self.new_buffer_data = None
        self._ic_in_p = None
        self._pixels = None
        self.grabber = None
        self.gentl = None
        if hasattr(self, '_box') and self._box is not None:
            cE.Eur_Buffer_destroy(self._box)
        self._box = None

    @property
    def _ic_in(self):
        if self._box and (self._ic_in_p is None):
            self._ic_in_p = egentl.ImageConvertInput(self.get_info(BUFFER_INFO_WIDTH, INFO_DATATYPE_SIZET),
                                              self.get_info(BUFFER_INFO_DELIVERED_IMAGEHEIGHT, INFO_DATATYPE_SIZET),
                                              self.get_info(BUFFER_INFO_BASE, INFO_DATATYPE_PTR),
                                              self.gentl.image_get_pixel_format(self.get_info(BUFFER_INFO_PIXELFORMAT, INFO_DATATYPE_UINT64)),
                                              self.get_info(BUFFER_INFO_DATA_SIZE, INFO_DATATYPE_SIZET),
                                              self.get_info(BUFFER_INFO_CUSTOM_LINE_PITCH, INFO_DATATYPE_SIZET))
        return self._ic_in_p

    @property
    def pixels(self):
        """Byte-array of the buffer."""
        if self._box and (self._pixels is None):
            self._pixels = ct.cast(self.get_info(BUFFER_INFO_BASE, INFO_DATATYPE_PTR), ct.POINTER(ct.c_ubyte * self.get_info(BUFFER_INFO_DATA_SIZE, INFO_DATATYPE_SIZET))).contents
        return self._pixels

    def push(self):
        """Push the GenTL buffer back to the data stream input fifo.

        Parameters
        ----------
        grabber : EGrabber object
            The grabber managing the underlying GenTL buffer to push back.
        """
        cE.Eur_Buffer_push__from__Eur_EGrabberBase(self._box, self.grabber._box)

    def __nopush_in_with_block(self):
        raise AttributeError('Buffer.push is not available in a "with Buffer" block')

    def get_info(self, cmd, info_datatype=None):
        """Get buffer information.

        Parameters
        ----------
        cmd : int (BUFFER_INFO_CMD)
            Command values (cf. GenTL::BUFFER_INFO_CMD_LIST or
            GenTL::EuresysCustomGenTL::BUFFER_INFO_CUSTOM_CMD_LIST).
        info_datatype : int (INFO_DATATYPE), optional
            Type of data to get (cf. GenTL::INFO_DATATYPE_LIST).

        Returns
        -------
        info : int, bool, float or str
        """
        if info_datatype is None:
            box = cE.Eur_InfoCommandInfo()
            cE.Eur_Buffer_getInfo__as__InfoCommandInfo__from__Eur_EGrabberBase__BUFFER_INFO_CMD(
                self._box, self.grabber._box, ct.c_int32(cmd), ct.byref(box))
            dt = ct.c_int()
            cE.Eur_InfoCommandInfo_get_dataType(box, ct.byref(dt))
            info_datatype = dt.value
        with utils.Ctype.from_info_datatype(info_datatype) as info:
            funcname = 'Eur_Buffer_getInfo__as__{}__from__Eur_EGrabberBase__BUFFER_INFO_CMD'.format(info.ctypename)
            getattr(cE, funcname)(self._box, self.grabber._box, ct.c_int32(cmd), ct.byref(info.box))
            return info.box_value

    def get_user_pointer(self):
        """Get the user pointer provided when the GenTL buffer was announced (if any).

        Returns
        -------
        user_pointer : int
        """
        up = ct.c_void_p()
        cE.Eur_Buffer_getUserPointer(self._box, ct.byref(up))
        return up.value

    def save_to_disk(self, filepath, index=None, params=None):
        """Save the buffer content to disk.

        Parameters
        ----------
        filepath : str
            Path to file or path pattern:
            - path of the new image file, the file extension determines the file format;
            - path pattern where a group characters 'N' is replaced by the value of index:
                - if index is 5, N becomes 5;
                - if index is 9, NN becomes 09;
                - if index is 10, NN becomes 10.

                  Examples
                  --------
                  >>> for i in range(20):
                  ...     with Buffer(grabber) as buffer:
                  ...         buffer.save_to_disk("images/buffer.NNN.jpeg", i)
                  ...

        index : int, optional
            - If index >= 0, enable pattern substitution with given index value.
            - If index is None (or < 0), disable pattern substitution.
        params: ImageSaveToDiskParams, optional
            Image saving parameters.

        Pre
        ---
        - The parent directory must exist.

        Notes
        -----
        - Buffer information (address, width, height, format) are automatically queried.
        - No buffer conversion will be applied before writing the image file, please
          use Buffer.convert if needed.
        """
        self.gentl.image_save_to_disk(self._ic_in, filepath, index, params)

    def convert(self, out_fmt, config=IMAGE_CONVERT_OUTPUT_CONFIG_DEFAULT, quality=0, roi=None):
        """Converts a buffer.

        Parameters
        ----------
        out_fmt : str
            Output pixel format.
        config : int, default=IMAGE_CONVERT_OUTPUT_CONFIG_DEFAULT
            Convert configuration (cf. GenTL::EuresysCustomGenTL::IMAGE_CONVERT_OUTPUT_CONFIG).
        quality : int, default=0
            Quality for jpeg format, from 1 (lowest) to 100 (highest), 0 selects the default encoder quality value.
        roi : ImageConvertROI, optional
            Region Of Interest to be converted.

        Returns
        -------
        converted_buffer : ConvertedBuffer
        """
        converted_buffer = ConvertedBuffer(self.gentl, self._ic_in.width,
                                           self._ic_in.height, out_fmt,
                                           self.get_info(BUFFER_INFO_CUSTOM_LINE_PITCH,
                                                         INFO_DATATYPE_SIZET))
        ic_out = egentl.ImageConvertOutput(self._ic_in.width, self._ic_in.height,
                                    converted_buffer.pixels, out_fmt, config,
                                    IMAGE_CONVERT_OUTPUT_OPERATION_COPY, quality)
        self.gentl.image_convert(self._ic_in, ic_out, roi)
        return converted_buffer

class ConvertedBuffer():
    """Converted buffer returned by Buffer.convert.

    Attributes
    ----------
    gentl : EGenTL
    width : int
    height : int
    format : str
        Pixel format.
    line_pitch : int
        Optional line pitch (in pixels) of the buffer.
    pixels : ctypes.c_char_Array_
        Byte-array of the buffer.
    """

    def __init__(self, gentl, width, height, format, line_pitch=None):
        self.gentl = gentl
        self.width = width
        self.height = height
        self.format = format
        self.line_pitch = line_pitch
        self.pixels = (ct.c_ubyte*self.get_buffer_size())()
        self._ic_in_p = None

    @property
    def _ic_in(self):
        if self._ic_in_p is None:
            self._ic_in_p = egentl.ImageConvertInput(self.width, self.height, self.get_address(), self.format, self.get_buffer_size(), self.line_pitch)
        return self._ic_in_p

    def get_address(self):
        """Get address of converted buffer.

        Returns
        -------
        address : int
        """
        return ct.addressof(self.pixels)

    def get_buffer_size(self):
        """Get converted buffer size in bytes.

        Returns
        -------
        size : int
        """
        return (self.width*self.height*self.gentl.image_get_bytes_per_pixel(self.format))

    def save_to_disk(self, filepath, index=None, params=None):
        """Save image to disk.

        Parameters
        ----------
        filepath : str
            Path to file or path pattern:
            - path of the new image file, the file extension determines the file format;
            - path pattern where a group characters 'N' is replaced by the value of index:
                - if index is 5, N becomes 5;
                - if index is 9, NN becomes 09;
                - if index is 10, NN becomes 10.

                  Examples
                  --------
                  >>> for i in range(20):
                  ...     with Buffer(grabber) as buffer:
                  ...         rgb = buffer.convert('RGB8')
                  ...         rgb.save_to_disk("images/rgb.NNN.jpeg", i)
                  ...

        index : int, optional
            - If index >= 0, enable pattern substitution with given index value.
            - If index is None (or < 0), disable pattern substitution.
        params: ImageSaveToDiskParams, optional
            Image saving parameters.

        Pre
        ---
        - The parent directory must exist.
        """
        self.gentl.image_save_to_disk(self._ic_in, filepath, index, params)
