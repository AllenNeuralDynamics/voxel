# Copyright Euresys 2021

"""EGrabberDiscovery module."""

import ctypes as ct

import six

from . import utils
from .generated import cEGrabber as cE


class EGrabberInfo(object):

    def __init__(self, gentl, box):
        self.gentl = gentl
        self._box = box

    @classmethod
    def _from_EGrabberDiscovery_egrabbers_at(cls, discovery, ix):
        box = cE.Eur_EGrabberInfo()
        cE.Eur_EGrabberDiscovery_egrabbers__from__int(discovery._box, ct.c_int(ix), ct.byref(box))
        return cls(discovery.gentl, box)

    @classmethod
    def _from_EGrabberDiscovery_inferfaceInfo(cls, discovery, interface_index):
        box = cE.Eur_EGrabberInfo()
        cE.Eur_EGrabberDiscovery_interfaceInfo__from__int(discovery._box, ct.c_int(interface_index), ct.byref(box))
        return cls(discovery.gentl, box)

    @classmethod
    def _from_EGrabberDiscovery_deviceInfo(cls, discovery, interface_index, device_index):
        box = cE.Eur_EGrabberInfo()
        cE.Eur_EGrabberDiscovery_deviceInfo__from__int__int(
            discovery._box, ct.c_int(interface_index), ct.c_int(device_index), ct.byref(box)
        )
        return cls(discovery.gentl, box)

    @classmethod
    def _from_EGrabberDiscovery_streamInfo(cls, discovery, interface_index, device_index, stream_index):
        box = cE.Eur_EGrabberInfo()
        cE.Eur_EGrabberDiscovery_streamInfo__from__int__int__int(
            discovery._box, ct.c_int(interface_index), ct.c_int(device_index), ct.c_int(stream_index), ct.byref(box)
        )
        return cls(discovery.gentl, box)

    @classmethod
    def _from_EGrabberCameraInfo_egrabbers_at(cls, camera_info, index):
        box = cE.Eur_EGrabberInfo()
        cE.Eur_EGrabberCameraInfo_grabber_at__from__size_t(camera_info._box, ct.c_size_t(index), ct.byref(box))
        return cls(camera_info.gentl, box)

    def __del__(self):
        if self._box is not None:
            cE.Eur_EGrabberInfo_destroy(self._box)

    def _get_int_field(self, fn):
        c_value = ct.c_int()
        fn(self._box, ct.byref(c_value))
        return c_value.value

    def _get_bool_field(self, fn):
        c_value = ct.c_ubyte()
        fn(self._box, ct.byref(c_value))
        return bool(c_value.value)

    def _get_str_field(self, fn):
        with utils.Ctype.std_string() as c_string:
            fn(self._box, ct.byref(c_string.box))
            return c_string.box_value

    @property
    def interface_index(self):
        return self._get_int_field(cE.Eur_EGrabberInfo_get_interfaceIndex)

    @property
    def device_index(self):
        return self._get_int_field(cE.Eur_EGrabberInfo_get_deviceIndex)

    @property
    def stream_index(self):
        return self._get_int_field(cE.Eur_EGrabberInfo_get_streamIndex)

    @property
    def interfaceID(self):
        return self._get_str_field(cE.Eur_EGrabberInfo_get_interfaceID)

    @property
    def deviceID(self):
        return self._get_str_field(cE.Eur_EGrabberInfo_get_deviceID)

    @property
    def streamID(self):
        return self._get_str_field(cE.Eur_EGrabberInfo_get_streamID)

    @property
    def deviceVendorName(self):
        return self._get_str_field(cE.Eur_EGrabberInfo_get_deviceVendorName)

    @property
    def deviceModelName(self):
        return self._get_str_field(cE.Eur_EGrabberInfo_get_deviceModelName)

    @property
    def deviceDescription(self):
        return self._get_str_field(cE.Eur_EGrabberInfo_get_deviceDescription)

    @property
    def streamDescription(self):
        return self._get_str_field(cE.Eur_EGrabberInfo_get_streamDescription)

    @property
    def deviceUserID(self):
        return self._get_str_field(cE.Eur_EGrabberInfo_get_deviceUserID)

    @property
    def tlType(self):
        return self._get_str_field(cE.Eur_EGrabberInfo_get_tlType)

    @property
    def firmwareStatus(self):
        return self._get_str_field(cE.Eur_EGrabberInfo_get_firmwareStatus)

    @property
    def fanStatus(self):
        return self._get_str_field(cE.Eur_EGrabberInfo_get_fanStatus)

    @property
    def licenseStatus(self):
        return self._get_str_field(cE.Eur_EGrabberInfo_get_licenseStatus)

    @property
    def isRemoteAvailable(self):
        return self._get_bool_field(cE.Eur_EGrabberInfo_get_isRemoteAvailable)

    @property
    def isDeviceReadOnly(self):
        return self._get_bool_field(cE.Eur_EGrabberInfo_get_isDeviceReadOnly)


class EGrabberCameraInfo:

    def __init__(self, discovery, key):
        self.gentl = discovery.gentl
        self._box = cE.Eur_EGrabberCameraInfo()
        try:
            if type(key) is tuple:
                ktype = type(key[0])
                if ktype in six.integer_types:
                    cE.Eur_EGrabberDiscovery_cameras__from__int__int(
                        discovery._box, ct.c_int(key[0]), ct.c_int(key[1]), ct.byref(self._box)
                    )
                elif ktype in (str, six.text_type):
                    cE.Eur_EGrabberDiscovery_cameras__from__const_char_p__int(
                        discovery._box, utils.to_cstr(key[0]), ct.c_int(key[1]), ct.byref(self._box)
                    )
                else:
                    raise TypeError("key[0] must be int or str.")
            else:
                ktype = type(key)
                if ktype in six.integer_types:
                    cE.Eur_EGrabberDiscovery_cameras__from__int(discovery._box, ct.c_int(key), ct.byref(self._box))
                elif ktype in (str, six.text_type):
                    cE.Eur_EGrabberDiscovery_cameras__from__const_char_p(
                        discovery._box, utils.to_cstr(key), ct.byref(self._box)
                    )
                else:
                    raise TypeError("key must be int or str.")
        except:
            self._box = None
            raise

    def __del__(self):
        if self._box is not None:
            cE.Eur_EGrabberCameraInfo_destroy(self._box)

    class _GetEGrabberInfo(utils._EGrabberIterable):
        def __init__(self, camera_info):
            self.camera_info = camera_info

        def __getitem__(self, ix):
            return EGrabberInfo._from_EGrabberCameraInfo_egrabbers_at(self.camera_info, ix)

        def __len__(self):
            c_count = ct.c_size_t()
            cE.Eur_EGrabberCameraInfo_grabber_count(self.camera_info._box, ct.byref(c_count))
            return int(c_count.value)

    @property
    def grabbers(self):
        return EGrabberCameraInfo._GetEGrabberInfo(self)


@six.add_metaclass(utils.FinalClass)
class EGrabberDiscovery(object):
    """Euresys EGrabber and camera discovery.
    (Discover available grabbers and cameras in the system.)
    """

    def __init__(self, gentl):
        """Create an EGrabberDiscovery object.

        Parameters
        ----------
        gentl : EGenTL

        Notes
        -----
        - It's not recommended to create more than one EGrabberDiscovery
          object for the same system (EGenTL object).
        """
        self.gentl = gentl
        self._box = cE.Eur_EGrabberDiscovery()
        try:
            cE.Eur_EGrabberDiscovery_create__from__Eur_EGenTL(gentl._box, ct.byref(self._box))
        except:
            self._box = None
            raise

    def __del__(self):
        if self._box is not None:
            cE.Eur_EGrabberDiscovery_destroy(self._box)

    def discover(self, find_cameras=True):
        """Perform the discovery.

        Parameters
        ----------
        find_cameras : bool, default=True
            Enable or disable the camera-oriented discovery in addition to the
            grabber-oriented discovery.

        Notes:
        - The camera-oriented discovery (i.e. the default behavior of discover)
          takes more time to complete because it inspects all the grabbers of
          the system to present a list of available cameras; A multi-bank camera
          that exposes several CoaXPress devices (each device providing a part
          of the acquired images) can be detected by the camera-oriented
          discovery as a **single** camera; indeed the discovery is able to
          identify which devices go together and how to reorder them so the
          master device is always in the first position.
        """
        cE.Eur_EGrabberDiscovery_discover__from__bool8_t(self._box, ct.c_ubyte(find_cameras))

    class _GetEGrabberInfo(utils._EGrabberIterable):
        def __init__(self, discovery):
            self.discovery = discovery

        def __getitem__(self, ix):
            return EGrabberInfo._from_EGrabberDiscovery_egrabbers_at(self.discovery, ix)

        def __len__(self):
            c_count = ct.c_int()
            cE.Eur_EGrabberDiscovery_egrabberCount(self.discovery._box, ct.byref(c_count))
            return c_count.value

    @property
    def egrabbers(self):
        """Result of the grabber-oriented discovery (by the last run of discover).
        Information to create an EGrabber object for a discovered grabber.

        Key
        ---
        int
            index of the grabber, must be smaller than len(egrabbers).

        Returns
        -------
        info : EGrabberInfo
            can be passed to EGrabber constructor

        Notes
        -----
        - len(egrabbers) returns the number of discovered egrabbers
        """
        return EGrabberDiscovery._GetEGrabberInfo(self)

    class _GetEGrabberCameraInfo(utils._EGrabberIterable):
        def __init__(self, discovery):
            self.discovery = discovery

        def __getitem__(self, key):
            return EGrabberCameraInfo(self.discovery, key)

        def __len__(self):
            c_count = ct.c_int()
            cE.Eur_EGrabberDiscovery_cameraCount(self.discovery._box, ct.byref(c_count))
            return c_count.value

    @property
    def cameras(self):
        """Result of the camera-oriented discovery (by the last run of discover).
        Information to create an EGrabber object for a discovered camera.

        Key
        ---
        int, int
            first : index of the camera, must be smaller than len(cameras).
            second : optional index of the data stream to select, default=0
        string, int
            first : user-defined name of the camera.
            second : optional index of the data stream to select, default=0

        Returns
        -------
        info : EGrabberCameraInfo
            can be passed to EGrabber constructor

        Notes
        -----
        - len(cameras) returns the number of discovered cameras
        """
        return EGrabberDiscovery._GetEGrabberCameraInfo(self)

    def interface_count(self):
        """How many interfaces were found in the system (by the last run of discover).

        Returns
        -------
        count : int
            number of interfaces found in the system
        """
        c_count = ct.c_int()
        cE.Eur_EGrabberDiscovery_interfaceCount(self._box, ct.byref(c_count))
        return c_count.value

    def interface_info(self, interface_index):
        """Return information about an interface (found by the last run of discover).

        Parameters
        ----------
        interface_index : int

        Returns
        -------
        info : EGrabberInfo
            can be passed to EGrabber constructor
        """
        return EGrabberInfo._from_EGrabberDiscovery_inferfaceInfo(self, interface_index)

    def device_count(self, interface_index):
        """How many devices were found in an interface (by the last run of discover).

        Parameters
        ----------
        interface_index : int

        Returns
        -------
        count : int
            number of devices found in interface #interface_index
        """
        c_count = ct.c_int()
        cE.Eur_EGrabberDiscovery_deviceCount__from__int(self._box, ct.c_int(interface_index), ct.byref(c_count))
        return c_count.value

    def device_info(self, interface_index, device_index):
        """Return information about a device (found by the last run of discover).

        Parameters
        ----------
        interface_index : int
        device_index : int

        Returns
        -------
        info : EGrabberInfo
            can be passed to EGrabber constructor
        """
        return EGrabberInfo._from_EGrabberDiscovery_deviceInfo(self, interface_index, device_index)

    def stream_count(self, interface_index, device_index):
        """How many streams were found in a device (by the last run of discover).

        Parameters
        ----------
        interface_index : int
        device_index : int

        Returns
        -------
        count : int
            number of streams found in device #device_index of interface #interface_index
        """
        c_count = ct.c_int()
        cE.Eur_EGrabberDiscovery_streamCount__from__int__int(
            self._box, ct.c_int(interface_index), ct.c_int(device_index), ct.byref(c_count)
        )
        return c_count.value

    def stream_info(self, interface_index, device_index, stream_index):
        """Return information about a stream (found by the last run of discover).

        Parameters
        ----------
        interface_index : int
        device_index : int
        stream_index : int

        Returns
        -------
        info : EGrabberInfo
            can be passed to EGrabber constructor
        """
        return EGrabberInfo._from_EGrabberDiscovery_streamInfo(self, interface_index, device_index, stream_index)
