# Copyright Euresys 2020

"""Helper functions to build Euresys GenApi queries."""

from .generated import cEGrabber as cE
from . import utils
import ctypes as ct

def _handler(func, *args):
    with utils.Ctype(cE.Eur_query_GenApiQueryBuilder) as builder:
        func(*(list(args) + [ct.byref(builder.box)]))
        with utils.Ctype.std_string() as query:
            cE.Eur_query_GenApiQueryBuilder_string(builder.box, ct.byref(query.box))
            return query.box_value

def attributes():
    """Create a query to get the list of attributes exposed by a GenApi Module.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_attributes)

def features(available_only=True):
    """Create a query to get the list of features exposed by a GenApi Module.

    Parameters
    ----------
    available_only : bool
        If true: the query will be configured to only include features available at "query" time; 
        if false: the query will be configured to include all the exposed features.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_features__from__bool8_t, ct.c_ubyte(available_only))

def features_of(category, available_only=True):
    """Create a query to get the list of features of a category exposed by a GenApi Module.

    Parameters
    ----------
    category : str
        Name of the category.
    available_only : bool
        If true: the query will be configured to only include features of the category available at "query" time;
        if false: the query will be configured to include all the exposed features of the category.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_featuresOf__from__const_char_p__bool8_t, utils.to_cstr(category), ct.c_ubyte(available_only))

def categories(available_only=True):
    """Create a query to get the list of categories exposed by a GenApi Module.

    Parameters
    ----------
    available_only : bool
        If true: the query will be configured to only include categories available at "query" time;
        if false: the query will be configured to include all the exposed categories.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_categories__from__bool8_t, ct.c_ubyte(available_only))

def categories_of(category, available_only=True):
    """Create a query to get the list of categories of a category exposed by a GenApi Module.

    Parameters
    ----------
    category : str
        Name of the category.
    available_only : bool
        If true: the query will be configured to only include categories of the category available at "query" time;
        if false: the query will be configured to include all the exposed categories of the category.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_categoriesOf__from__const_char_p__bool8_t, utils.to_cstr(category), ct.c_ubyte(available_only))

def enum_entries(feature, available_only=True):
    """Create a query to get the list of entries of a GenApi enumeration.

    Parameters
    ----------
    feature : str
        Name of enumeration feature to query.
    available_only : bool
        If true: the query will be configured to only include enumeration entries available at "query" time;
        if false: the query will be configured to include all enumeration entries of the given feature.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_enumEntries__from__const_char_p__bool8_t, utils.to_cstr(feature), ct.c_ubyte(available_only))

def available(feature):
    """Create a query to check if a feature is available.

    Parameters
    ----------
    feature : str
        Name of the feature to query.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_available__from__const_char_p, utils.to_cstr(feature))

def readable(feature):
    """Create a query to check if a feature is readable.

    Parameters
    ----------
    feature : str
        Name of the feature to query.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_readable__from__const_char_p, utils.to_cstr(feature))

def writeable(feature):
    """Create a query to check if a feature is writeable.

    Parameters
    ----------
    feature : str
        Name of the feature to query.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_writeable__from__const_char_p, utils.to_cstr(feature))

def implemented(feature):
    """Create a query to check if a feature is implemented.

    Parameters
    ----------
    feature : str
        Name of the feature to query.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_implemented__from__const_char_p, utils.to_cstr(feature))

def command(feature):
    """Create a query to check if a feature is a command.

    Parameters
    ----------
    feature : str
        Name of the feature to query.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_command__from__const_char_p, utils.to_cstr(feature))

def done(feature):
    """Create a query to check if execution of a command is done.

    Parameters
    ----------
    feature : str
        Name of the command to query.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_done__from__const_char_p, utils.to_cstr(feature))

def interfaces(feature):
    """Create a query to get the list of interfaces of a feature.

    Parameters
    ----------
    feature : str
        Name of the feature to query.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_interfaces__from__const_char_p, utils.to_cstr(feature))

def source(feature):
    """Create a query to get the XML source of a feature.

    Parameters
    ----------
    feature : str
        Name of the feature to query.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_source__from__const_char_p, utils.to_cstr(feature))

def xml():
    """Create a query to get the register description document of a GenApi Module.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_xml)

def info(feature, what):
    """Create a query to get XML information of a feature node.

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
    return _handler(cE.Eur_query_info__from__const_char_p__const_char_p, utils.to_cstr(feature), utils.to_cstr(what))

def declared():
    """Create a query to get the list of declared virtual user features.

    Returns
    -------
    str
    """
    return _handler(cE.Eur_query_declared)
