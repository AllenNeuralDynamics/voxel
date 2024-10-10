# Copyright Euresys 2020

"""EGenTL module."""

from .generated import *
from .generated import cEGrabber as cE
from . import utils
from threading import Lock, Thread
import ctypes as ct
import six

def Coaxlink():
    """Return cti path to Coaxlink producer.

    Returns
    -------
    cti : str
    """
    with utils.Ctype.std_string() as cti:
        cE.Eur_Coaxlink(ct.byref(cti.box))
        return cti.box_value

def Grablink():
    """Return cti path to Grablink producer.

    Returns
    -------
    cti : str
    """
    with utils.Ctype.std_string() as cti:
        cE.Eur_Grablink(ct.byref(cti.box))
        return cti.box_value

def Gigelink():
    """Return cti path to GigE Vision producer.

    Returns
    -------
    cti : str
    """
    with utils.Ctype.std_string() as cti:
        cE.Eur_Gigelink(ct.byref(cti.box))
        return cti.box_value

# commented out to allow for singleton metaclass!!
# @six.add_metaclass(utils.FinalClass)
class EGenTL():
    """An EGenTL object is a wrapper around EGenTL C++ API."""

    def __init__(self, path=None):
        """Create an EGenTL object and initialize the EGenTL library.

        Parameters
        ----------
        path : str, optional
            Filesystem path to the EGenTL library. 
            If path is None, default path is used.
        """
        self._box = cE.Eur_EGenTL()
        try:
            if path is not None:
                cE.Eur_EGenTL_create__from__char_p(utils.to_cstr(path), ct.byref(self._box))
            else:
                cE.Eur_EGenTL_create(ct.byref(self._box))
        except:
            self._box = None
            raise
        self._wr = utils.WeakRefBox(self, '_box')

    def __del__(self):
        if self._box is not None:
            cE.Eur_EGenTL_destroy(self._box)

    @staticmethod
    def get_default_cti_path():
        """Get default path to the EGenTL library.

        Returns
        -------
        path : str
        """
        with utils.Ctype.std_string() as path:
            cE.Eur_getEuresysCtiPath(ct.byref(path.box))
            return path.box_value

    def gc_get_info(self, cmd, info_datatype=None):
        """Get information for the system module.

        Parameters
        ----------
        cmd : int (TL_INFO_CMD)
            Command values (cf. GenTL::TL_INFO_CMD_LIST).
        info_datatype : int (INFO_DATATYPE), optional
            Type of data to get (cf. GenTL::INFO_DATATYPE_LIST).

        Returns
        -------
        info : int or str
        """
        if info_datatype is None:
            box = cE.Eur_InfoCommandInfo()
            cE.Eur_EGenTL_gcGetInfo__as__InfoCommandInfo__from__TL_INFO_CMD(self._box, ct.c_int32(cmd), ct.byref(box))
            dt = ct.c_int()
            cE.Eur_InfoCommandInfo_get_dataType(box, ct.byref(dt))
            info_datatype = dt.value
        with utils.Ctype.from_info_datatype(info_datatype) as info:
            funcname = 'Eur_EGenTL_gcGetInfo__as__{}__from__TL_INFO_CMD'.format(info.ctypename)
            getattr(cE, funcname)(self._box, ct.c_int32(cmd), ct.byref(info.box))
            return info.box_value

    def image_get_pixel_format(self, format):
        """Get string pixel format.

        Parameters
        ----------
        format : int
            Pixel format.

        Returns
        -------
        pixel_format : str
        """
        with utils.Ctype.std_string() as pf:
            cE.Eur_EGenTL_imageGetPixelFormat__from__uint64_t(self._box, ct.c_uint64(format), ct.byref(pf.box))
            return pf.box_value

    def image_get_pixel_format_value(self, format):
        """Get pixel format value (32-bit PFNC).

        Parameters
        ----------
        format : str
             Pixel format.

        Returns
        -------
        pfnc32 : int
        """
        pfnc32 = ct.c_uint()
        cE.Eur_EGenTL_imageGetPixelFormatValue__from__const_char_p__unsigned_int(
            self._box, utils.to_cstr(format), ct.c_uint(PIXELFORMAT_NAMESPACE_PFNC_32BIT), ct.byref(pfnc32))
        return pfnc32.value

    def image_get_bytes_per_pixel(self, format):
        """Get bytes per pixel.

        Parameters
        ----------
        format : str or int
            Pixel format.

        Returns
        -------
        bpp : int
        """
        if type(format) == int:
            format = self.image_get_pixel_format(format)
        bps = ct.c_uint()
        cE.Eur_EGenTL_imageGetBytesPerPixel__from__const_char_p(
            self._box, utils.to_cstr(format), ct.byref(bps))
        return bps.value

    def image_get_bits_per_pixel(self, format):
        """Get bits per pixel.

        Parameters
        ----------
        format : str or int
            Pixel format.

        Returns
        -------
        bpp : int
        """
        if type(format) == int:
            format = self.image_get_pixel_format(format)
        bps = ct.c_uint()
        cE.Eur_EGenTL_imageGetBitsPerPixel__from__const_char_p(
            self._box, utils.to_cstr(format), ct.byref(bps))
        return bps.value

    def image_convert(self, input, output, roi=None):
        """Convert an image.

        Parameters
        ----------
        input : ImageConvertInput
            Input image details.
        output : ImageConvertOutput
            Output image details.
        roi : ImageConvertROI, optional
            Region of interest. If None, default parameters are used.
        """
        cE.Eur_EGenTL_imageConvert__from__ImageConvertInput_p__ImageConvertOutput_p__ImageConvertROI_p(
            self._box, ct.byref(input), ct.byref(output), roi)

    def image_save_to_disk(self, input, filepath, index=None, params=None):
        """Save an image to disk.

        Parameters
        ----------
        input : ImageConvertInput
            Input image details.
        filepath : str
            Path to file or path pattern:
            - path of the new image file, the file extension determines the file format;
            - path pattern where a group characters 'N' is replaced by the value of index:
                - if index is 5, N becomes 5;
                - if index is 9, NN becomes 09;
                - if index is 10, NN becomes 10.
        index : int, optional
            - If index >= 0, enable pattern substitution with given index value.
            - If index is None (or < 0), disable pattern substitution.
        params : ImageSaveToDiskParams, optional
            Image saving parameters.
        """
        if index is None:
            index = -1
        cE.Eur_EGenTL_imageSaveToDisk__from__ImageConvertInput_p__const_char_p__int64_t__ImageSaveToDiskParams_p(
            self._box, ct.byref(input), utils.to_cstr(filepath), ct.c_int64(index), params)

class ImageConvertInput(ct.Structure):
    """Input details for image conversion.

    Attributes
    ----------
    width : int
        Input buffer width in pixels.
    height : int
        Input buffer height in pixels.
    pixels : ctypes.c_char_Array_ or int (address pointer)
        Input buffer (or address of input buffer).
    format : str
        Input pixel format.
    buffer_size : ctypes.LP_c_size_t
        Optional pointer to input buffer size.
    line_pitch : ctypes.LP_c_size_t
        Optional pointer to input line pitch, mandatory for packed formats.
    preserved0 : NoneType
        Reserved for future use, must be None.
    preserved1 : NoneType
        Reserved for future use, must be None.
    version : int
        ImageConvertInput structure version, must be 1.
    reserved0 : int
        Reserved for future use, must be 0.
    reserved1 : int
        Reserved for future use, must be 0.
    reserved2 : int
        Reserved for future use, must be 0.
    """
    _fields_ = [
        ('width', ct.c_int),
        ('height', ct.c_int),
        ('pixels', ct.c_void_p),
        ('format', ct.c_char_p),
        ('buffer_size', ct.POINTER(ct.c_size_t)),
        ('line_pitch', ct.POINTER(ct.c_size_t)),
        ('preserved0', ct.c_void_p),
        ('preserved1', ct.c_void_p),
        ('version', ct.c_int),
        ('reserved0', ct.c_int),
        ('reserved1', ct.c_int),
        ('reserved2', ct.c_int)
    ]

    def __init__(self, width, height, pixels, format, buffer_size=None, line_pitch=None):
        """Create an ImageConvertInput Object.

        Parameters
        ----------
        width : int
        height : int
        pixels : ctypes.c_char_Array_ or int (address pointer)
        format : str
        buffer_size : int, optional
        line_pitch : int, optional
        """
        if buffer_size is None:
            buffer_size = ct.POINTER(ct.c_size_t)()
        else:
            buffer_size = ct.pointer(ct.c_size_t(buffer_size))
        if line_pitch is None:
            line_pitch = ct.POINTER(ct.c_size_t)()
        else:
            line_pitch = ct.pointer(ct.c_size_t(line_pitch))
        super(ImageConvertInput, self).__init__(
            width, height, pixels, utils.to_cstr(format),
            buffer_size, line_pitch, None, None, 1, 0, 0, 0)

class ImageConvertOutput(ct.Structure):
    """Output details for image conversion.

    Attributes
    ----------
    width : int
        Output buffer width in pixels.
    height : int
        Output buffer height in pixels.
    pixels : ctypes.c_char_Array_ or int (address pointer)
        Output buffer (or address of new image id if IMAGE_CONVERT_OUTPUT_CONFIG_IMAGE_ID).
    format : str
        Output pixel format.
    config : int
        Convert configuration (cf. GenTL::EuresysCustomGenTL::IMAGE_CONVERT_OUTPUT_CONFIG).
    operation : int
        Convert operation (cf. GenTL::EuresysCustomGenTL::IMAGE_CONVERT_OUTPUT_OPERATION).
    version : int
        ImageConvertOutput structure version, must be 1.
    quality : int
        Jpeg encoding quality from 1 (lowest) to 100 (highest), 0 selects the default encoder quality value.
    size : ctypes.LP_c_size_t
        Optional input/output pointer for pixels buffer size.
        - Input: maximum data size.
        - Output: written data size.
    """
    _fields_ = [
        ('width', ct.c_int),
        ('height', ct.c_int),
        ('pixels', ct.c_void_p),
        ('format', ct.c_char_p),
        ('config', ct.c_int),
        ('operation', ct.c_int),
        ('version', ct.c_int),
        ('quality', ct.c_int),
        ('size', ct.POINTER(ct.c_size_t))
    ]

    def __init__(self, width, height, pixels, format, config, operation, quality, size=None):
        """Create an ImageConvertOutput Object.

        Parameters
        ----------
        width : int
        height : int
        pixels : ctypes.c_char_Array_ or int (address pointer)
        format : str
        config : int (IMAGE_CONVERT_OUTPUT_CONFIG)
        operation : int (IMAGE_CONVERT_OUTPUT_OPERATION)
        quality : int
        size : int, optional
        """
        if size is None:
            size = ct.POINTER(ct.c_size_t)()
        else:
            size = ct.pointer(ct.c_size_t(size))
        super(ImageConvertOutput, self).__init__(
            width, height, ct.addressof(pixels), utils.to_cstr(format), 
            config, operation, 1, quality, size)

class ImageConvertROI(ct.Structure):
    """Region Of Interest details for image conversion (optional).

    Attributes
    ----------
    width : int, default=0
        Width of ROI in pixels (default=0 selects buffer parameter width).
    height : int, default=0
        Height of ROI in pixels (default=0 selects buffer parameter height).
    in_offset_x : int, default=0
        X offset (in pixels) in the input buffer.
    in_offset_y : int, default=0
        Y offset (in pixels) in the input buffer.
    out_offset_x : int, default=0
        X offset (in pixels) in the output decoded buffer.
    out_offset_y : int, default=0
        Y offset (in pixels) in the output decoded buffer.

    Notes
    -----
    - Each field can be set to 0 to select its default value.
    """
    _fields_ = [
        ('width', ct.c_int),
        ('height', ct.c_int),
        ('in_offset_x', ct.c_int),
        ('in_offset_y', ct.c_int),
        ('out_offset_x', ct.c_int),
        ('out_offset_y', ct.c_int)
    ]

    def __init__(self, width=0, height=0, in_offset_x=0, in_offset_y=0, out_offset_x=0, out_offset_y=0):
        super(ImageConvertROI, self).__init__(width, height, in_offset_x, in_offset_y, out_offset_x, out_offset_y)

class ImageSaveToDiskParams(ct.Structure):
    """Image Save To Disk Parameters (optional).

    Attributes
    ----------
    config : int
        Convert configuration (cf. GenTL::EuresysCustomGenTL::IMAGE_CONVERT_OUTPUT_CONFIG).
    quality : int
        Quality for jpeg format, from 1 (lowest) to 100 (highest), 0 selects the default encoder quality value.
    reserved : ctypes.c_int_Array_4
        Reserved for future use.
    """
    _fields_ = [
        ('config', ct.c_int),
        ('quality', ct.c_int),
        ('reserved', ct.c_int * 4)
    ]
