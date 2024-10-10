# Copyright Euresys 2020

"""Helpers for internal use."""

from .generated import constants as c
from .generated import cEGrabber as cE
import ctypes as ct
import sys
import weakref
import atexit

class WeakRefBox():

    def __init__(self, that, property, action=None):
        self.property = property
        self.action = action
        self.that = weakref.ref(that)
        atexit.register(self)

    def __call__(self):
        ref = self.that()
        if ref is not None:
            if self.action is not None:
                try:
                    getattr(ref, self.action)()
                except:
                    pass
            try:
                setattr(ref, self.property, None)
            except:
                pass

    def __del__(self):
        if sys.version_info.major > 2:
            atexit.unregister(self)

def to_cstr(string):
    return string.encode()

def from_std_string(std_string):
    c_str = ct.c_char_p()
    cE.std_string_c_str(std_string, ct.byref(c_str))
    return c_str.value.decode()

def from_c_ptr(c_ptr):
    ptr_tmp = ct.cast(c_ptr, ct.c_void_p)
    return ptr_tmp.value

class FinalClass(type):

    def __new__(cls, name, bases, classdict):
        for base in bases:
            if isinstance(base, FinalClass):
                raise TypeError("'{0}' cannot be subclassed".format(base.__name__))
        return type.__new__(cls, name, bases, classdict)

class c_bool8(ct.c_ubyte):
    pass

class c_size_t(ct.c_size_t):
    pass

class Ctype():

    def __init__(self, ctype):
        (self.ctypename, self._getter, self._deleter) = self.to_attr[ctype]
        self.box = ctype()

    @classmethod
    def from_info_datatype(cls, info_datatype):
        ctype = cls.to_ctype[info_datatype]
        return cls(ctype)

    @classmethod
    def std_string(cls):
        return cls(cE.std_string)

    def __del__(self):
        if self._deleter and self.box:
            self._deleter(self.box)
        self.box = None

    def __enter__(self):
        return self

    def __exit__(self, a, b, c):
        self.__del__()

    @property
    def box_value(self):
        if self._getter:
            return self._getter(self.box)
        else:
            return self.box.value

    to_attr = {
        c_size_t                        : ('size_t',      None,            None),
        ct.c_int8                       : ('int8_t',      None,            None),
        ct.c_int16                      : ('int16_t',     None,            None),
        ct.c_int32                      : ('int32_t',     None,            None),
        ct.c_int64                      : ('int64_t',     None,            None),
        ct.c_uint8                      : ('uint8_t',     None,            None),
        ct.c_uint16                     : ('uint16_t',    None,            None),
        ct.c_uint32                     : ('uint32_t',    None,            None),
        ct.c_uint64                     : ('uint64_t',    None,            None),
        c_bool8                         : ('uint8_t',     bool,            None),
        ct.c_float                      : ('float',       None,            None),
        ct.c_double                     : ('double',      None,            None),
        ct.POINTER(ct.c_char)           : ('uint8_t_ptr', from_c_ptr,      None),
        cE.std_string                   : ('std_string',  from_std_string, cE.std_string_destroy),
        cE.Eur_query_GenApiQueryBuilder : (None,          None,            cE.Eur_query_GenApiQueryBuilder_destroy)
    }

    to_ctype = {
        c.INFO_DATATYPE_SIZET   : c_size_t,
        c.INFO_DATATYPE_INT16   : ct.c_int16,
        c.INFO_DATATYPE_INT32   : ct.c_int32,
        c.INFO_DATATYPE_INT64   : ct.c_int64,
        c.INFO_DATATYPE_UINT16  : ct.c_uint16,
        c.INFO_DATATYPE_UINT32  : ct.c_uint32,
        c.INFO_DATATYPE_UINT64  : ct.c_uint64,
        c.INFO_DATATYPE_BOOL8   : c_bool8,
        c.INFO_DATATYPE_FLOAT64 : ct.c_double,
        c.INFO_DATATYPE_PTR     : ct.POINTER(ct.c_char),
        c.INFO_DATATYPE_STRING  : cE.std_string
    }

class _EGrabberIterable():

    def __iter__(self):
        return self._Iterator(self)

    class _Iterator():

        def __init__(self, iterable):
            self._iterable = iterable
            self._i = 0

        def __next__(self):
            if self._i < len(self._iterable):
                item = self._iterable[self._i]
                self._i += 1
                return item
            else:
                raise StopIteration
        def next(self):
            return self.__next__()
