#!/usr/bin/env python
'''Simple utility functions that do not depend on any other part of
peyotl.
'''
from StringIO import StringIO
import logging
import json
import time
import os

from peyotl.utility.io import download, \
                              expand_path, \
                              open_for_group_write, \
                              parse_study_tree_list, \
                              write_to_filepath

def pretty_timestamp(t=None, style=0):
    if t is None:
        t = time.localtime()
    if style == 0:
        return time.strftime("%Y-%m-%d", t)
    return time.strftime("%Y%m%d%H%M%S", t)

_LOGGING_LEVEL_ENVAR = "PEYOTL_LOGGING_LEVEL"
_LOGGING_FORMAT_ENVAR = "PEYOTL_LOGGING_FORMAT"
_LOGGING_FILE_PATH_ENVAR = "PEYOTL_LOG_FILE_PATH"

_LOG = None
_READING_LOGGING_CONF = True
_LOGGING_CONF = {}

def _get_logging_level(s=None):
    if s is None:
        return logging.NOTSET
    supper = s.upper()
    if supper == "NOTSET":
        level = logging.NOTSET
    elif supper == "DEBUG":
        level = logging.DEBUG
    elif supper == "INFO":
        level = logging.INFO
    elif supper == "WARNING":
        level = logging.WARNING
    elif supper == "ERROR":
        level = logging.ERROR
    elif supper == "CRITICAL":
        level = logging.CRITICAL
    else:
        level = logging.NOTSET
    return level

def _get_logging_formatter(s=None):
    if s is None:
        s = 'NONE'
    else:
        s = s.upper()
    logging_formatter = None
    if s == "RICH":
        logging_formatter = logging.Formatter("[%(asctime)s] %(filename)s (%(lineno)d): %(levelname) 8s: %(message)s")
    elif s == "SIMPLE":
        logging_formatter = logging.Formatter("%(levelname) 8s: %(message)s")
    elif s == "RAW":
        logging_formatter = logging.Formatter("%(message)s")
    else:
        logging_formatter = None
    if logging_formatter is not None:
        logging_formatter.datefmt = '%H:%M:%S'
    return logging_formatter


def read_logging_config():
    global _READING_LOGGING_CONF
    level = get_config('logging', 'level', 'WARNING')
    logging_format_name = get_config('logging', 'formatter', 'NONE')
    logging_filepath = get_config('logging', 'filepath', '')
    if logging_filepath == '':
        logging_filepath = None
    _LOGGING_CONF['level_name'] = level
    _LOGGING_CONF['formatter_name'] = logging_format_name
    _LOGGING_CONF['filepath'] = logging_filepath
    _READING_LOGGING_CONF = False
    return _LOGGING_CONF


def get_logger(name="peyotl"):
    """
    Returns a logger with name set as given, and configured
    to the level given by the environment variable _LOGGING_LEVEL_ENVAR.
    """
    logger = logging.getLogger(name)
    if len(logger.handlers) == 0:
        lc = _LOGGING_CONF
        if 'level' not in lc:
            # TODO need some easy way to figure out whether we should use env vars or config
            if _LOGGING_LEVEL_ENVAR in os.environ:
                lc['level_name'] = os.environ.get(_LOGGING_LEVEL_ENVAR)
                lc['formatter_name'] = os.environ.get(_LOGGING_FORMAT_ENVAR)
                lc['filepath'] = os.environ.get(_LOGGING_FILE_PATH_ENVAR)
            else:
                lc = read_logging_config()
            lc['level'] = _get_logging_level(lc['level_name'])
            lc['formatter'] = _get_logging_formatter(lc['formatter_name'])
        logger.setLevel(lc['level'])
        if lc['filepath'] is not None:
            log_dir = os.path.split(lc['filepath'])[0]
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
            ch = logging.FileHandler(lc['filepath'])
        else:
            ch = logging.StreamHandler()
        ch.setLevel(lc['level'])
        ch.setFormatter(lc['formatter'])
        logger.addHandler(ch)
    return logger

def _get_util_logger():
    global _LOG
    if _LOG is not None:
        return _LOG
    if _READING_LOGGING_CONF:
        return None
    _LOG = get_logger("peyotl.utility")
    return _LOG

_CONFIG = None
_CONFIG_FN = None
def get_default_config_filename():
    global _CONFIG_FN
    if _CONFIG_FN is None:
        if 'PEYOTL_CONFIG_FILE' in os.environ:
            _CONFIG_FN = os.environ['PEYOTL_CONFIG_FILE']
        else:
            _CONFIG_FN = os.path.expanduser("~/.peyotl/config")
        if not os.path.exists(_CONFIG_FN):
            from pkg_resources import Requirement, resource_filename
            pr = Requirement.parse('peyotl')
            _CONFIG_FN = resource_filename(pr, 'peyotl/default.conf')
        assert os.path.exists(_CONFIG_FN)
    return _CONFIG_FN
def read_config(filepaths=None):
    global _CONFIG
    from ConfigParser import SafeConfigParser
    if filepaths is None:
        if _CONFIG is None:
            _CONFIG = SafeConfigParser()
            read_files = _CONFIG.read(get_default_config_filename())
        else:
            read_files = [get_default_config_filename()]
        cfg = _CONFIG
    else:
        if isinstance(filepaths, list) and None in filepaths:
            def_fn = get_default_config_filename()
            f = []
            for i in filepaths:
                f.append(def_fn if i is None else i)
            filepaths = f
        cfg = SafeConfigParser()
        read_files = cfg.read(filepaths)
    return cfg, read_files

def get_config(section=None, param=None, default=None, cfg=None):
    '''
    Returns the config object if `section` and `param` are None, or the
        value for the requested parameter.

    If the parameter (or the section) is missing, the exception is logged and
        None is returned.
    '''
    read_filenames = None
    if cfg is None:
        try:
            cfg, read_filenames = read_config()
        except:
            return default
    if section is None and param is None:
        return cfg
    try:
        v = cfg.get(section, param)
        return v
    except:
        if default is None:
            if read_filenames:
                f = '"{}" '.format('", "'.join(read_filenames))
            else:
                f = ''
            mf = 'Config file {f}does not contain option "{o}"" in section "{s}"\n'
            msg = mf.format(f=f, o=param, s=section)
            _ulog = _get_util_logger()
            if _ulog is not None:
                _ulog.error(msg)
        return default
get_config_var = get_config

def doi2url(v):
    if v.startswith('http'):
        return v
    if v.startswith('doi:'):
        v = v[4:] # trim doi:
    return 'http://dx.doi.org/' + v

def pretty_dict_str(d, indent=2):
    '''shows JSON indented representation of d'''
    b = StringIO()
    write_pretty_dict_str(b, d, indent=indent)
    return b.getvalue()
def write_pretty_dict_str(out, obj, indent=2):
    '''writes JSON indented representation of obj to out'''
    json.dump(obj,
              out,
              indent=indent,
              sort_keys=True,
              separators=(',', ': '),
              ensure_ascii=False,
              encoding="utf-8")
def get_unique_filepath(stem):
    '''NOT thread-safe!
    return stems or stem# where # is the smallest
    positive integer for which the path does not exist.
    useful for temp dirs where the client code wants an
    obvious ordering.
    '''
    fp = stem
    if os.path.exists(stem):
        n = 1
        fp = stem + str(n)
        while os.path.exists(fp):
            n += 1
            fp = stem + str(n)
    return fp


